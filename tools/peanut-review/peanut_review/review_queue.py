"""Account-scoped PR discovery and driver handoff tasks.

GitHub polling never changes a checkout or launches reviewers. The driver owns
preparation and review execution. Credentials stay inside gh.account_auth.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from . import gh, review_completion, session as sess
from .models import GitHubAccount


REPO_RE = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+")
SHA_RE = re.compile(r"[0-9a-f]{40,64}")
ACTIVE_JOB_STATES = {"queued", "preparing", "reviewing", "curating"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity_key(account: GitHubAccount, repo: str, number: int) -> str:
    identity = f"{account.hostname}/{account.user_id}/{repo.casefold()}#{number}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def snapshot(pr: dict) -> dict:
    return {name: pr[name] for name in ("head_sha", "base_sha", "base_ref")}


def load_config(path: str | Path) -> dict:
    path = Path(path).expanduser().resolve()
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("accounts"), list) or not raw["accounts"]:
        raise ValueError("queue config requires a nonempty accounts array")
    cfg = copy.deepcopy(raw)
    cfg["pollSeconds"] = raw.get("pollSeconds", 120)
    if type(cfg["pollSeconds"]) is not int or cfg["pollSeconds"] < 30:
        raise ValueError("pollSeconds must be an integer of at least 30")
    seen = set()
    for account in cfg["accounts"]:
        if not isinstance(account, dict):
            raise ValueError("each queue account must be an object")
        account["hostname"] = gh.validate_hostname(account.get("hostname", "github.com"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", account.get("login", "")):
            raise ValueError("queue account requires a valid login")
        key = (account["hostname"], account["login"].casefold())
        if key in seen:
            raise ValueError("duplicate queue account")
        seen.add(key)
        account.setdefault("label", account["login"])
        if not isinstance(account["label"], str):
            raise ValueError("account label must be a string")
        repositories = account.setdefault("repositories", {})
        if not isinstance(repositories, dict):
            raise ValueError("repositories must map owner/repo to checkout configuration")
        for repo, settings in list(repositories.items()):
            if not REPO_RE.fullmatch(repo) or not isinstance(settings, dict):
                raise ValueError("invalid repository configuration")
            if repo != repo.casefold():
                del repositories[repo]
                repositories[repo.casefold()] = settings
        for settings in [account, *repositories.values()]:
            for name in ("cloneRoot", "worktreeRoot", "reviewConfig", "path"):
                if name not in settings:
                    continue
                value = settings[name]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{name} must be a nonempty path")
                resolved = Path(os.path.expandvars(value)).expanduser()
                settings[name] = str((path.parent / resolved).resolve())
            commands = settings.get("prepare", [])
            if not isinstance(commands, list) or any(
                not isinstance(cmd, list) or not cmd or any(not isinstance(arg, str) for arg in cmd)
                for cmd in commands
            ):
                raise ValueError("prepare must be an array of argv arrays")
            timeout = settings.get("prepareTimeoutSeconds", 1800)
            if type(timeout) is not int or timeout <= 0:
                raise ValueError("prepareTimeoutSeconds must be a positive integer")
    return cfg


def search_requests(login: str) -> list[dict]:
    """Fetch every search page; never silently report a truncated queue."""
    items = []
    page = 1
    while True:
        query = urlencode({"q": f"is:pr is:open review-requested:{login}",
                           "per_page": 100, "page": page})
        result = json.loads(gh._api(f"search/issues?{query}"))
        if result.get("incomplete_results") or result["total_count"] > 1000:
            raise RuntimeError("GitHub returned an incomplete review search; refresh to retry (search limit: 1,000 PRs)")
        items.extend(result["items"])
        if len(items) >= result["total_count"]:
            return items
        if not result["items"]:
            raise RuntimeError("GitHub review search ended before all results were returned")
        page += 1


def fetch_pr(repo: str, number: int) -> dict:
    if not REPO_RE.fullmatch(repo) or type(number) is not int or number <= 0:
        raise ValueError("invalid PR target")
    data = json.loads(gh._api(f"repos/{repo}/pulls/{number}"))
    account = gh.current_account()
    returned_repo, returned_number = gh.parse_pr_spec(data["html_url"])
    if (returned_repo.casefold(), returned_number, gh.hostname_for_spec(data["html_url"])) != (
        repo.casefold(), number, account.hostname,
    ):
        raise ValueError("GitHub returned a different PR target")
    head, base = data["head"], data["base"]
    if not SHA_RE.fullmatch(head["sha"]) or not SHA_RE.fullmatch(base["sha"]):
        raise ValueError("GitHub returned an invalid commit SHA")
    direct = any(user["login"].casefold() == account.login.casefold()
                 for user in data.get("requested_reviewers", []))
    return {
        "repo": returned_repo, "number": number, "url": data["html_url"],
        "title": data["title"], "body": data.get("body") or "",
        "author": data["user"]["login"], "draft": bool(data.get("draft")),
        "state": "merged" if data.get("merged") else data["state"],
        "head_sha": head["sha"], "head_ref": head["ref"],
        "base_sha": base["sha"], "base_ref": base["ref"],
        "request_kind": "direct" if direct else None,
        "requested_team_ids": [team["id"] for team in data.get("requested_teams", [])],
        "updated_at": data["updated_at"], "checked_at": now(), "error": "",
    }


def request_history(repo: str, number: int, account: GitHubAccount) -> list[dict]:
    """Keep only account-scoped review activity and team request transitions."""
    events = gh._parse_paginated(gh._api(
        f"repos/{repo}/issues/{number}/timeline?per_page=100", paginate=True))
    history = []
    for event in sorted(events, key=lambda e: e.get("submitted_at") or e.get("created_at") or ""):
        action = event.get("event")
        if action not in {"review_requested", "review_request_removed", "reviewed"}:
            continue
        reviewer = (event.get("user") if action == "reviewed" else event.get("requested_reviewer")) or {}
        matches = (reviewer["id"] == account.user_id if reviewer.get("id") is not None
                   else reviewer.get("login", "").casefold() == account.login.casefold())
        team_id = (event.get("requested_team") or {}).get("id")
        if matches or team_id is not None:
            history.append({"event": action, "team_id": team_id})
    return history


def request_origin(remote: dict, previous: dict, account: GitHubAccount, team_cache: dict) -> dict:
    """Retain review origin after submission, but honor explicit withdrawals.

    A direct request takes precedence over team requests. Team events count only
    when the selected account belongs to that team, never merely because some
    team was requested on the PR. Cache history by the PR's updated timestamp.
    """
    kind = previous.get("request_kind")
    # Older versions unconditionally called every non-direct PR a team request.
    if kind != "direct" and not previous.get("request_kind_verified"):
        kind = None
    result = {"request_kind": kind, "request_kind_verified": True, "request_kind_error": "",
              "request_withdrawn": previous.get("request_withdrawn", False)}
    if remote.get("request_kind") == "direct":
        # A new request restores a withdrawn row. Recheck history on its next
        # disappearance, even if GitHub's updated_at has not advanced yet.
        result.update(request_kind="direct", requested=True, request_withdrawn=False,
                      request_history_updated_at=None)
        return result

    history = previous.get("request_history")
    history_ok = True
    if (history is None or not previous.get("request_history_updated_at")
            or previous["request_history_updated_at"] != remote["updated_at"]
            or set(previous.get("requested_team_ids", [])) != set(remote.get("requested_team_ids", []))):
        try:
            history = request_history(remote["repo"], remote["number"], account)
            result.update(request_history=history,
                          request_history_updated_at=remote["updated_at"])
        except Exception as error:
            history_ok = False
            result["request_kind_error"] = f"Could not check request history: {error}"

    history = history or []
    current_teams = set(remote.get("requested_team_ids", []))
    candidate_teams = {event["team_id"] for event in history if event["team_id"] is not None} | current_teams
    membership_ok = True
    member_teams = set()
    if candidate_teams:
        # One account-scoped membership lookup per poll, including failed lookups.
        if not team_cache:
            try:
                teams = gh._parse_paginated(gh._api("user/teams?per_page=100", paginate=True))
                team_cache["ids"] = {team["id"] for team in teams}
            except Exception as error:
                team_cache["error"] = str(error)
        if "error" in team_cache:
            membership_ok = False
            result["request_kind_error"] = f'Could not check team membership: {team_cache["error"]}'
        else:
            member_teams = team_cache["ids"]
    relevant = [event for event in history if event["team_id"] is None or event["team_id"] in member_teams]
    if any(event["event"] == "review_requested" and event["team_id"] is None for event in relevant):
        result["request_kind"] = "direct"
    elif result["request_kind"] != "direct" and (current_teams & member_teams or any(
            event["event"] == "review_requested" and event["team_id"] is not None for event in relevant)):
        result["request_kind"] = "team"

    if membership_ok or not current_teams:
        # PR metadata is authoritative even while GitHub search is catching up.
        result["requested"] = bool(current_teams & member_teams)
    if result.get("requested"):
        result["request_withdrawn"] = False
    elif history_ok and membership_ok:
        result["request_withdrawn"] = bool(relevant and relevant[-1]["event"] == "review_request_removed")
    return result


class ReviewQueue:
    def __init__(self, root: Path, config: dict, registry) -> None:
        self.root = Path(root).resolve()
        self.directory = self.root / ".queue"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._owner = (self.directory / "service.lock").open("a")
        try:
            fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._owner.close()
            raise ValueError("a review queue is already serving this session root") from None
        self.config = config
        self.registry = registry
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.wakeup = threading.Event()
        self.refreshing = False
        self._threads: list[threading.Thread] = []
        self.path = self.directory / "state.json"
        try:
            self.state = json.loads(self.path.read_text()) if self.path.exists() else {"version": 1, "items": {}, "accounts": {}}
            if self.state.get("version") != 1:
                raise ValueError("unsupported review queue state version")
            for item in self.state["items"].values():
                if item.get("request_kind") == "team" and not item.get("request_kind_verified"):
                    item["request_kind"] = None
                job = item.get("job", {})
                if job.get("status") in ACTIVE_JOB_STATES:
                    job.update(status="interrupted", error="Queue execution retired. Inspect the session with the driver.", finished_at=now())
            self._save()
        except Exception:
            self._owner.close()
            raise

    def _save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(self.state, output, indent=2)
            output.write("\n")
        temporary.replace(self.path)

    def start(self) -> None:
        def poll() -> None:
            while not self.stopping.is_set():
                self.refresh()
                self.wakeup.wait(self.config["pollSeconds"])
                self.wakeup.clear()

        thread = threading.Thread(target=poll, daemon=True)
        self._threads.append(thread)
        thread.start()

    def close(self) -> None:
        self.stopping.set()
        self.wakeup.set()
        for thread in self._threads:
            thread.join(timeout=2)
        # In serve(), process exit ends any remaining I/O. Do not relinquish
        # ownership while an old worker could still update persisted state.
        if not any(thread.is_alive() for thread in self._threads):
            self._owner.close()

    def account_config(self, identity: dict) -> dict:
        for account in self.config["accounts"]:
            if (account["hostname"], account["login"].casefold()) == (
                identity["hostname"], identity["login"].casefold(),
            ):
                return account
        raise ValueError("account is no longer configured")

    def repository_config(self, item: dict) -> dict:
        account = self.account_config(item["account"])
        settings = {**account, **account.get("repositories", {}).get(item["repo"].casefold(), {})}
        if not settings.get("path") and settings.get("cloneRoot"):
            settings["path"] = str(Path(settings["cloneRoot"]) / item["repo"])
            if settings.get("worktreeRoot"):
                settings["worktreeRoot"] = str(Path(settings["worktreeRoot"]) / item["repo"])
        return settings

    def _attach_sessions(self, account: GitHubAccount) -> None:
        self.registry.rescan()
        seen = set()
        # Include every stored session, not just the first index page.
        for summary in self.registry.list_sessions():
            path = self.registry.get(summary["id"])
            try:
                session = sess.load_session(path)
            except (OSError, ValueError):
                continue
            pr = session.github
            if not pr or pr.account != account:
                continue
            key = identity_key(account, pr.repo, pr.number)
            receipt = review_completion.completed_review(path, session)
            with self.lock:
                item = self.state["items"].setdefault(key, {
                    "key": key, "account": asdict(account), "repo": pr.repo,
                    "number": pr.number, "requested": False,
                })
                if key not in seen:
                    item["session_id"] = session.id
                    seen.add(key)
                # Completion is independent of the session chosen for further work.
                if receipt and receipt["completed_at"] >= item.get("completed_at", ""):
                    item.update(completed_snapshot=receipt["snapshot"],
                                completed_at=receipt["completed_at"])

    def refresh(self) -> None:
        with self.lock:
            if self.refreshing:
                return
            self.refreshing = True
        try:
            for configured in self.config["accounts"]:
                if self.stopping.is_set():
                    return
                account_key = f'{configured["hostname"]}/{configured["login"].casefold()}'
                try:
                    with self.lock:
                        previous = self.state["accounts"].get(account_key, {}).get("identity")
                    expected = GitHubAccount(**previous) if previous else None
                    with gh.account_auth(configured["hostname"], configured["login"], expected=expected) as account:
                        team_cache = {}
                        self._attach_sessions(account)
                        requests = search_requests(account.login)
                        requested = {}
                        for result in requests:
                            repo, number = gh.parse_pr_spec(result["html_url"])
                            if gh.hostname_for_spec(result["html_url"]) != account.hostname:
                                raise ValueError("review search returned a different GitHub host")
                            requested[identity_key(account, repo, number)] = (repo, number)
                        with self.lock:
                            for key, (repo, number) in requested.items():
                                self.state["items"].setdefault(key, {"key": key, "account": asdict(account), "repo": repo, "number": number})
                            tracked = [copy.deepcopy(item) for item in self.state["items"].values() if item["account"] == asdict(account)]
                        for old in tracked:
                            if self.stopping.is_set():
                                return
                            key = old["key"]
                            try:
                                remote = fetch_pr(old["repo"], old["number"])
                                remote.update(request_origin(remote, old, account, team_cache))
                            except Exception as error:
                                remote = {"error": str(error)}
                            with self.lock:
                                self.state["items"][key].update(
                                    remote, requested=remote.get("requested", key in requested))
                        with self.lock:
                            self.state["accounts"][account_key] = {"identity": asdict(account), "checked_at": now(), "error": ""}
                except Exception as error:
                    with self.lock:
                        status = self.state["accounts"].setdefault(account_key, {})
                        status["error"] = str(error)
                finally:
                    with self.lock:
                        self._save()
        finally:
            with self.lock:
                self.refreshing = False

    def refresh_async(self) -> None:
        self.wakeup.set()

    def driver_task(self, item: dict, directory: Path | None, session) -> str:
        settings = self.repository_config(item)
        context = {
            "pr_url": f'https://{item["account"]["hostname"]}/{item["repo"]}/pull/{item["number"]}',
            "github_account": item["account"],
            "peanut_review_cli": str(Path(__file__).resolve().parent.parent / "bin" / "peanut-review"),
            "review_config": settings.get("reviewConfig"),
            "session_root": str(self.root),
            "session": str(directory) if directory else None,
            "workspace": session.workspace if session else None,
            "repository": sess.repo_path(session) if session else settings.get("path"),
            "worktree_root": settings.get("worktreeRoot"),
            "observed_head": item.get("head_sha"),
            "observed_base": item.get("base_sha"),
            "base_branch": item.get("base_ref"),
            "prepare_commands": settings.get("prepare", []),
        }
        action = "Refresh and re-review" if session else "Review"
        return (
            f"{action} {item['repo']}#{item['number']} using the peanut-review skill as the driver.\n\n"
            "Use the account and local context below. Fetch the latest PR metadata; the observed "
            "revision may have changed. Inspect any existing session and live agents first. "
            "Reuse the existing session's workspace for this PR. If it is missing or no session exists, "
            "inspect git worktree list --porcelain in the matching repository for an existing PR "
            "worktree before creating one. Keep the existing directory and branch name. Local edits, "
            "force pushes, and divergent branches are reasons to reconcile that worktree, not to "
            "create another. Create a worktree only when no suitable existing PR worktree exists "
            "or the user explicitly requests a separate one. If another task or live agent owns "
            "the checkout, wait or report the conflict before changing it. "
            "Reuse its saved reviewer/curator lineup, or use the configured lineup for a new session. "
            "Preserve local edits, commits, build artifacts, and prior review history. Before moving "
            "a divergent branch, save its old HEAD on a named local backup branch. Save any local "
            "edits with a recorded stash or other recoverable backup, and protect untracked or ignored "
            "files that would collide with the fetched revision. With a clean tracked checkout, "
            "fast-forward when possible; after a force push, use git reset --keep to the verified "
            "fetched PR head in the same worktree. Do not use reset --hard or git clean. If safe "
            "synchronization fails, investigate the conflict without discarding work. Keep saved "
            "edits separate from the exact PR snapshot during review and report recovery references. "
            "Follow project build/test instructions before launching through peanut-review. Verify "
            "checkout HEAD matches the latest PR head, then sync-pr the existing session, or "
            "create one under the specified session root. Run reviewers and then the configured curator, "
            "monitor failures, and finish with gh-push --dry-run and a summary. "
            "Do not publish to GitHub. Discover missing configuration before proceeding.\n\n"
            "Context (JSON data):\n" + json.dumps(context, indent=2) + "\n"
        )

    def payload(self) -> dict:
        # Observe CLI-created sessions on local UI polls, without waiting for GitHub.
        for cfg in self.config["accounts"]:
            key = f'{cfg["hostname"]}/{cfg["login"].casefold()}'
            with self.lock:
                identity = self.state["accounts"].get(key, {}).get("identity")
            if identity:
                self._attach_sessions(GitHubAccount(**identity))
        with self.lock:
            items = copy.deepcopy(list(self.state["items"].values()))
            statuses = copy.deepcopy(self.state["accounts"])
            refreshing = self.refreshing
        accounts = []
        active_accounts = set()
        for cfg in self.config["accounts"]:
            key = f'{cfg["hostname"]}/{cfg["login"].casefold()}'
            active_accounts.add(key)
            accounts.append({"key": key, "label": cfg["label"], "login": cfg["login"], "hostname": cfg["hostname"], **statuses.get(key, {})})
        rows = []
        for item in items:
            key = f'{item["account"]["hostname"]}/{item["account"]["login"].casefold()}'
            if key not in active_accounts or item.get("request_withdrawn"):
                continue
            item["account_key"] = key
            item.pop("body", None)
            item.pop("requested_team_ids", None)
            item.pop("request_history_team_ids", None)
            item.pop("request_history", None)
            # Old queue jobs remain on disk as history, not as current driver status.
            item.pop("job", None)
            directory = None
            session = None
            completed = item.get("completed_snapshot")
            session_id = item.get("session_id")
            if session_id:
                directory = self.registry.get(session_id)
                if directory is None:
                    item["session_id"] = None
                else:
                    try:
                        session = sess.load_session(directory)
                        expected = {"account": item["account"], "repo": item["repo"].casefold(), "number": item["number"]}
                        if review_completion.target(session) != expected:
                            raise ValueError("Session target does not match this queue item")
                        item["session_progress"] = (self.registry._summary(session_id, directory) or {}).get("progress", {})
                    except (OSError, ValueError, AttributeError):
                        directory = None
                        session = None
                        item["session_id"] = None
                        item["session_progress"] = {"label": "Session unavailable", "status": "failed"}
            status = statuses.get(key, {})
            item["error"] = item.get("error") or status.get("error", "")
            checked = item.get("checked_at")
            expired = not checked or (datetime.now(timezone.utc) - datetime.fromisoformat(checked)).total_seconds() > self.config["pollSeconds"] * 3
            current = snapshot(item) if item.get("head_sha") else None
            item["freshness"] = "unknown" if item["error"] or expired else (
                "current" if completed and completed == current else "stale" if completed else "unreviewed"
            )
            if not completed and session and (session.current_head != item.get("head_sha") or session.base_ref != item.get("base_sha")):
                if item["freshness"] != "unknown":
                    item["freshness"] = "stale"
            item["driver_task"] = self.driver_task(item, directory, session)
            rows.append(item)
        rows.sort(key=lambda item: (item.get("state") != "open", item["freshness"] != "stale", not item.get("requested"), item.get("repo", ""), item["number"]))
        return {"items": rows, "accounts": accounts, "refreshing": refreshing, "poll_seconds": self.config["pollSeconds"]}

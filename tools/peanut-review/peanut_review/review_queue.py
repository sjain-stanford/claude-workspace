"""Account-scoped PR discovery and persistent local review jobs.

GitHub polling never changes a checkout or launches reviewers. Only an explicit
start action does that. Credentials remain inside gh.account_auth operations.
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

from . import gh, runtime, session as sess
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
        "request_kind": "direct" if direct else "team",
        "updated_at": data["updated_at"], "checked_at": now(), "error": "",
    }


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
                job = item.get("job", {})
                if job.get("status") in ACTIVE_JOB_STATES:
                    job.update(status="interrupted", error="Server stopped during this job. Inspect the session before retrying.", finished_at=now())
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
        from .queue_jobs import run_job

        def poll() -> None:
            while not self.stopping.is_set():
                self.refresh()
                self.wakeup.wait(self.config["pollSeconds"])
                self.wakeup.clear()

        def work() -> None:
            while not self.stopping.is_set():
                selected = None
                with self.lock:
                    for key, item in self.state["items"].items():
                        if item.get("job", {}).get("status") == "queued":
                            item["job"]["status"] = "preparing"
                            self._save()
                            selected = key
                            break
                if selected:
                    try:
                        run_job(self, selected)
                    except Exception as error:
                        self.update_job(selected, status="failed", error=str(error), finished_at=now())
                else:
                    self.stopping.wait(0.5)

        for target in (poll, work):
            thread = threading.Thread(target=target, daemon=True)
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
        if not settings.get("reviewConfig") or not settings.get("worktreeRoot"):
            raise ValueError("Configure reviewConfig and worktreeRoot for this account or repository, then restart the server")
        if not settings.get("path"):
            if not settings.get("cloneRoot"):
                raise ValueError("Configure a checkout path or cloneRoot, then restart the server")
            settings["path"] = str(Path(settings["cloneRoot"]) / item["repo"])
            settings["worktreeRoot"] = str(Path(settings["worktreeRoot"]) / item["repo"])
        return settings

    def _attach_sessions(self, account: GitHubAccount) -> None:
        self.registry.rescan(force=True)
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
            with self.lock:
                item = self.state["items"].setdefault(key, {
                    "key": key, "account": asdict(account), "repo": pr.repo,
                    "number": pr.number, "requested": False,
                })
                if not item.get("session_id"):
                    item["session_id"] = session.id

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
                            except Exception as error:
                                remote = {"error": str(error)}
                            with self.lock:
                                self.state["items"][key].update(remote, requested=key in requested)
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

    def update_job(self, key: str, **updates) -> None:
        with self.lock:
            self.state["items"][key]["job"].update(updates)
            self._save()

    def item(self, key: str) -> dict:
        with self.lock:
            return copy.deepcopy(self.state["items"][key])

    def session_busy(self, session_id: str) -> bool:
        directory = self.registry.get(session_id)
        try:
            workspace = str(Path(sess.repo_path(sess.load_session(directory))).resolve()) if directory else None
        except (OSError, ValueError):
            workspace = None
        with self.lock:
            return any((item.get("session_id") == session_id or (workspace and item.get("job", {}).get("workspace") == workspace)) and item.get("job", {}).get("status") in ACTIVE_JOB_STATES
                       for item in self.state["items"].values())

    def enqueue(self, key: str) -> dict:
        with self.lock:
            if key not in self.state["items"]:
                raise ValueError("unknown queue item")
            item = self.state["items"][key]
            self.repository_config(item)
            if item.get("state") != "open":
                raise ValueError("Only open PRs can be reviewed; refresh the queue first")
            if item.get("job", {}).get("status") in ACTIVE_JOB_STATES:
                return copy.deepcopy(item["job"])
            if runtime.is_process_live(item.get("job", {}).get("prepare_pid")):
                raise ValueError("The previous preparation process is still running; wait for it to finish before retrying")
            if item.get("session_id") and self.registry.get(item["session_id"]) is None:
                item.pop("session_id")
            item["job"] = {"id": os.urandom(12).hex(), "status": "queued", "started_at": now(), "error": ""}
            self._save()
            return copy.deepcopy(item["job"])

    def payload(self) -> dict:
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
            if key not in active_accounts:
                continue
            item["account_key"] = key
            item.pop("body", None)
            try:
                self.repository_config(item)
                item["setup_error"] = ""
            except ValueError as error:
                item["setup_error"] = str(error)
            status = statuses.get(key, {})
            item["error"] = item.get("error") or status.get("error", "")
            checked = item.get("checked_at")
            expired = not checked or (datetime.now(timezone.utc) - datetime.fromisoformat(checked)).total_seconds() > self.config["pollSeconds"] * 3
            completed = item.get("completed_snapshot")
            current = snapshot(item) if item.get("head_sha") else None
            item["freshness"] = "unknown" if item["error"] or expired else (
                "current" if completed and completed == current else "stale" if completed else "unreviewed"
            )
            session_id = item.get("session_id")
            if session_id:
                path = self.registry.get(session_id)
                if path is None:
                    item["session_id"] = None
                else:
                    try:
                        session = sess.load_session(path)
                        if not completed and session.github and (session.current_head != item.get("head_sha") or session.base_ref != item.get("base_sha")):
                            if item["freshness"] != "unknown":
                                item["freshness"] = "stale"
                        item["session_progress"] = self.registry._summary(session_id, path).get("progress", {})
                    except (OSError, ValueError, AttributeError):
                        item["session_progress"] = {"label": "Session unavailable", "status": "failed"}
            rows.append(item)
        rows.sort(key=lambda item: (item.get("state") != "open", item["freshness"] != "stale", not item.get("requested"), item.get("repo", ""), item["number"]))
        return {"items": rows, "accounts": accounts, "refreshing": refreshing, "poll_seconds": self.config["pollSeconds"]}

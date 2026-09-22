"""GitHub PR integration via the `gh` CLI.

Every call shells out to `gh` (or `$PEANUT_REVIEW_GH_BIN` for tests). The
selected account's stored token is scoped to each operation. Push/pull
primitives pass JSON bodies via stdin (`gh api --input -`) so multi-line
bodies, backticks, and shell metacharacters travel verbatim.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

from .models import GitHubAccount, GitHubPR


GH_BIN_ENV = "PEANUT_REVIEW_GH_BIN"
REPO_ACCOUNT_CONFIG = "peanut-review.githubAccount"
GITHUB_HOST = "github.com"
@dataclass(frozen=True)
class _Credentials:
    hostname: str
    token: str = field(repr=False)
    account: GitHubAccount | None = None


_CREDENTIALS: ContextVar[_Credentials | None] = ContextVar(
    "peanut_review_gh_credentials", default=None,
)
_TOKEN_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")


# Spec parser: accepts `owner/repo#123`, `owner/repo/pull/123`, and
# `https://github.com/owner/repo/pull/123` (plus `http://` and trailing /).
_SPEC_RE = re.compile(
    r"^(?:https?://(?P<host>[^/]+)/)?"
    r"(?P<owner>[^/\s#]+)/(?P<repo>[^/\s#]+?)"
    r"(?:#|/pull/|/pulls/)(?P<num>\d+)/?$"
)


def _gh_bin() -> str:
    return os.environ.get(GH_BIN_ENV) or shutil.which("gh") or "gh"


class GhError(RuntimeError):
    """Raised when a `gh` invocation fails. Carries stderr + stdout for
    diagnosis — `gh api` writes the structured GitHub error body to stdout
    (e.g. the `errors[]` array on a 422), so dropping it would hide the
    most actionable signal.
    """

    def __init__(self, cmd: list[str], rc: int,
                 stderr: str, stdout: str = "") -> None:
        detail = stderr.strip()
        body = stdout.strip()
        if body:
            # Parse and pretty-print the GitHub error body when it's JSON,
            # otherwise include it raw. The errors[] array is what tells the
            # caller which field / code triggered the validation failure.
            try:
                parsed = json.loads(body)
                msg = parsed.get("message") if isinstance(parsed, dict) else None
                errors = parsed.get("errors") if isinstance(parsed, dict) else None
                if msg or errors:
                    extras = [msg] if msg else []
                    if errors:
                        extras.append(json.dumps(errors, separators=(",", ":")))
                    body = " ".join(extras)
            except (ValueError, TypeError):
                pass
            detail = f"{detail} | body: {body}" if detail else body
        super().__init__(
            f"{' '.join(cmd[:3])}... failed (rc={rc}): {detail}"
        )
        self.cmd = cmd
        self.rc = rc
        self.stderr = stderr
        self.stdout = stdout


class RepoAccountError(RuntimeError):
    """Raised when a selected GitHub identity cannot be verified."""


def _clean_env() -> dict[str, str]:
    # Never mutate os.environ: web requests execute concurrently.
    env = os.environ.copy()
    for key in (*_TOKEN_ENV, "GH_HOST", "GH_REPO", "GH_DEBUG", "DEBUG"):
        env.pop(key, None)
    env["GH_PROMPT_DISABLED"] = "1"
    return env


def validate_hostname(hostname: str) -> str:
    if not isinstance(hostname, str) or not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", hostname,
    ):
        raise ValueError("GitHub hostname must be a DNS name without a scheme or port")
    return hostname.lower()


def repo_account(repo_path: str | Path) -> str:
    """Read an explicit default from git config, including includeIf rules."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", REPO_ACCOUNT_CONFIG],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RepoAccountError(
            "cannot read the GitHub account from git config; use --gh-account <login>"
        ) from None
    account = result.stdout.strip() if result.returncode == 0 else ""
    if not account:
        raise RepoAccountError(
            "select a GitHub account with --gh-account <login> or configure "
            f"`git config --local {REPO_ACCOUNT_CONFIG} <login>`"
        )
    return account


def hostname_for_spec(spec: str, *, workspace: str | None = None,
                      default: str | None = None) -> str:
    """Resolve the host before authentication, without contacting GitHub."""
    if "://" in spec:
        parsed = urlsplit(spec)
        if parsed.scheme not in {"https", "http"} or parsed.netloc.casefold() != (parsed.hostname or "").casefold():
            raise ValueError("invalid GitHub PR URL")
        return validate_hostname(parsed.hostname or "")
    if default or not spec.strip().isdigit():
        return validate_hostname(default or GITHUB_HOST)
    return workspace_repository(workspace)[0]


def workspace_repository(workspace: str | None) -> tuple[str, str]:
    """Resolve origin locally so gh never chooses a host using ambient config."""
    try:
        result = subprocess.run(
            ["git", "-C", workspace or ".", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RepoAccountError(
            "cannot read the GitHub repository from origin; use a full PR URL"
        ) from None
    remote = result.stdout.strip()
    if result.returncode == 0:
        if "://" in remote:
            parsed = urlsplit(remote)
            host, path = parsed.hostname, parsed.path.lstrip("/")
        else:
            match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", remote)
            host, path = (match[1], match[2]) if match else (None, "")
        path = path.rstrip("/").removesuffix(".git")
        if host and re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", path):
            return validate_hostname(host), path
    raise RepoAccountError("cannot determine GitHub repository from origin; use a full PR URL")


def _stored_token(hostname: str, login: str) -> str:
    def read_token(stored_login: str) -> str:
        result = subprocess.run(
            [_gh_bin(), "auth", "token", "--hostname", hostname, "--user", stored_login],
            capture_output=True, text=True, timeout=15, env=_clean_env(),
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    try:
        token = read_token(login)
        if not token:
            # gh's credential keys are case-sensitive, unlike GitHub logins.
            # Keep the normal lookup fast; resolve stored spelling only on a miss.
            result = subprocess.run(
                [_gh_bin(), "auth", "status", "--hostname", hostname, "--json", "hosts"],
                capture_output=True, text=True, timeout=30, env=_clean_env(),
            )
            if result.returncode == 0:
                accounts = json.loads(result.stdout)["hosts"].get(hostname, [])
                matches = {a["login"] for a in accounts
                           if a["login"].casefold() == login.casefold()}
                if len(matches) == 1:
                    stored_login = matches.pop()
                    if stored_login != login:
                        token = read_token(stored_login)
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, AttributeError):
        # Token command output and exception payloads may contain credentials.
        raise RepoAccountError("cannot run gh to retrieve the selected account's credentials") from None
    if not token or any(c.isspace() for c in token):
        raise RepoAccountError(
            f"no stored credentials for {hostname}/@{login}; "
            f"run `gh auth login --hostname {hostname}` for that account"
        )
    return token


@contextmanager
def account_auth(hostname: str, login: str, *,
                 expected: GitHubAccount | None = None) -> Iterator[GitHubAccount]:
    """Select and verify a stored token once; retain it for the entire operation.

    ContextVar scopes the immutable credentials to the current request. Nested
    operations restore their caller's context, and other threads cannot see it.
    """
    hostname = validate_hostname(hostname)
    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", login):
        raise RepoAccountError("invalid GitHub account login")
    if expected and (expected.hostname != hostname or expected.login.casefold() != login.casefold()):
        raise RepoAccountError("GitHub account binding does not match the requested account")
    token = _stored_token(hostname, login)
    marker = _CREDENTIALS.set(_Credentials(hostname, token))
    try:
        try:
            user = json.loads(_run(["api", "user", "--hostname", hostname]))
            actual_login, user_id = user["login"], user["id"]
            if not isinstance(actual_login, str) or type(user_id) is not int or user_id <= 0:
                raise ValueError("invalid account response")
        except (GhError, ValueError, KeyError, TypeError):
            raise RepoAccountError(f"cannot verify GitHub account {hostname}/@{login}") from None
        if actual_login.casefold() != login.casefold() or (expected and expected.user_id != user_id):
            raise RepoAccountError(f"GitHub credentials do not match the bound account {hostname}/@{login}")
        account = expected or GitHubAccount(hostname, actual_login, user_id)
        _CREDENTIALS.set(_Credentials(hostname, token, account))
        yield account
    finally:
        _CREDENTIALS.reset(marker)


def current_account() -> GitHubAccount:
    credentials = _CREDENTIALS.get()
    if credentials is None or credentials.account is None:
        raise RepoAccountError("GitHub operation requires an explicitly selected account")
    return credentials.account


def publish_identity(pr: GitHubPR) -> dict:
    if pr.account is None:
        raise RepoAccountError(
            "session has no GitHub account binding; run "
            "`peanut-review --session <path> gh-auth --account <login>`"
        )
    try:
        host = validate_hostname(pr.hostname)
        if pr.url:
            repo, number = parse_pr_spec(pr.url)
            if hostname_for_spec(pr.url) != host or (repo.casefold(), number) != (pr.repo.casefold(), pr.number):
                raise ValueError("PR URL does not match its target")
    except ValueError as e:
        raise RepoAccountError(f"invalid session GitHub target: {e}") from None
    if pr.account.hostname != host:
        raise RepoAccountError("session account and PR host do not match")
    return {"hostname": host, "repo": pr.repo.casefold(), "number": pr.number,
            "account": asdict(pr.account)}


@contextmanager
def pr_auth(pr: GitHubPR) -> Iterator[GitHubAccount]:
    publish_identity(pr)
    with account_auth(pr.hostname, pr.account.login, expected=pr.account) as account:
        yield account


def parse_pr_spec(spec: str) -> tuple[str, int]:
    """Return (`owner/repo`, pr_number). Raises ValueError on bad input."""
    m = _SPEC_RE.match(spec.strip())
    if not m:
        raise ValueError(
            f"invalid PR spec: {spec!r} "
            f"(expected owner/repo#N, owner/repo/pull/N, or a github.com URL)"
        )
    if m["host"] is not None:
        hostname_for_spec(spec)
    return f"{m['owner']}/{m['repo']}", int(m["num"])


def _run(args: list[str], *, input: str | None = None,
         timeout: int = 60, cwd: str | None = None) -> str:
    """Invoke `gh` and return stdout. Raises GhError on non-zero exit."""
    cmd = [_gh_bin(), *args]
    credentials = _CREDENTIALS.get()
    if credentials is None:
        raise RepoAccountError("GitHub operation requires an explicitly selected account")
    gh_env = _clean_env()
    gh_env["GH_HOST"] = credentials.hostname
    token_key = (
        "GH_TOKEN" if credentials.hostname == GITHUB_HOST or credentials.hostname.endswith(".ghe.com")
        else "GH_ENTERPRISE_TOKEN"
    )
    gh_env[token_key] = credentials.token
    try:
        res = subprocess.run(
            cmd, input=input, capture_output=True, text=True, timeout=timeout,
            cwd=cwd, env=gh_env,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise GhError(cmd, 1, "could not complete GitHub command") from None
    if res.returncode != 0:
        raise GhError(cmd, res.returncode,
                      res.stderr.replace(credentials.token, "[redacted]"),
                      res.stdout.replace(credentials.token, "[redacted]"))
    return res.stdout


def git_read(args: list[str], *, cwd: str | Path | None = None) -> str:
    """Run a clone/fetch with the operation's identity, without switching gh.

    The helper receives the token only through its environment. Disable other
    credential helpers so a second account on the same host cannot take over.
    Callers supply a validated HTTPS repository URL and literal argv entries.
    """
    credentials = _CREDENTIALS.get()
    if credentials is None or credentials.account is None:
        raise RepoAccountError("Git fetch requires an explicitly selected account")
    import shlex
    env = _clean_env()
    env["GH_HOST"] = credentials.hostname
    key = "GH_TOKEN" if credentials.hostname == GITHUB_HOST or credentials.hostname.endswith(".ghe.com") else "GH_ENTERPRISE_TOKEN"
    env[key] = credentials.token
    env["GIT_TERMINAL_PROMPT"] = "0"
    cmd = ["git", "-c", "credential.helper=", "-c",
           f"credential.helper=!{shlex.quote(_gh_bin())} auth git-credential", *args]
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                                text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        raise RepoAccountError("Git clone/fetch did not complete; check connectivity and repository access") from None
    if result.returncode:
        raise RepoAccountError(result.stderr.replace(credentials.token, "[redacted]").strip())
    return result.stdout


def resolve_pr_spec(spec: str, *, workspace: str | None = None) -> tuple[str, int]:
    """Resolve a PR spec locally; bare numbers use the checkout's origin."""
    stripped = spec.strip()
    if stripped.isdigit():
        _, repo = workspace_repository(workspace)
        return repo, int(stripped)
    return parse_pr_spec(stripped)


def _api(endpoint: str, *, method: str = "GET",
         payload: dict | None = None,
         paginate: bool = False) -> str:
    args = ["api", endpoint]
    if method != "GET":
        args += ["-X", method]
    if paginate:
        args.append("--paginate")
    args += ["--hostname", current_account().hostname]
    if payload is not None:
        args += ["--input", "-"]
        return _run(args, input=json.dumps(payload))
    return _run(args)


def _graphql(query: str, variables: dict) -> dict:
    out = _run(
        [
            "api", "graphql", "--hostname", current_account().hostname,
            "-X", "POST", "--input", "-",
        ],
        input=json.dumps({"query": query, "variables": variables}),
    )
    parsed = json.loads(out)
    if isinstance(parsed, dict) and parsed.get("errors"):
        raise GhError([_gh_bin(), "api", "graphql"], 1, "", json.dumps(parsed))
    return parsed


@dataclass
class PRInfo:
    repo: str
    number: int
    url: str
    title: str
    head_sha: str
    base_sha: str
    head_ref_name: str = ""
    hostname: str = GITHUB_HOST
    account: GitHubAccount | None = None
    body: str = ""


def fetch_pr_info(repo: str, number: int) -> PRInfo:
    out = _run([
        "pr", "view", str(number),
        "--repo", f"{current_account().hostname}/{repo}",
        "--json", "number,headRefOid,baseRefOid,headRefName,url,title,body",
    ])
    d = json.loads(out)
    returned_repo, returned_number = parse_pr_spec(d["url"])
    if (hostname_for_spec(d["url"]) != current_account().hostname
            or (returned_repo.casefold(), returned_number) != (repo.casefold(), number)):
        raise RepoAccountError("GitHub returned a PR outside the selected target")
    return PRInfo(
        repo=repo,
        number=int(d["number"]),
        url=d["url"],
        title=d["title"],
        body=d.get("body") or "",
        head_sha=d["headRefOid"],
        base_sha=d["baseRefOid"],
        head_ref_name=d.get("headRefName") or "",
        hostname=current_account().hostname,
        account=current_account(),
    )


def fetch_review_comments(repo: str, number: int) -> list[dict]:
    """Inline (line-anchored) review comments. Paginated."""
    raw = _api(f"repos/{repo}/pulls/{number}/comments", paginate=True)
    return _parse_paginated(raw)


def fetch_issue_comments(repo: str, number: int) -> list[dict]:
    """PR-level (issue) comments. Paginated."""
    raw = _api(f"repos/{repo}/issues/{number}/comments", paginate=True)
    return _parse_paginated(raw)


def fetch_pr_reviews(repo: str, number: int) -> list[dict]:
    """Submitted PR reviews. Non-empty bodies are review summaries."""
    raw = _api(f"repos/{repo}/pulls/{number}/reviews", paginate=True)
    return _parse_paginated(raw)


def fetch_pr_review_comments(repo: str, number: int, review_id: str) -> list[dict]:
    """Inline comments belonging to one submitted PR review."""
    raw = _api(
        f"repos/{repo}/pulls/{number}/reviews/{review_id}/comments",
        paginate=True,
    )
    return _parse_paginated(raw)


_REVIEW_THREAD_RESOLUTIONS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $cursor) {
        nodes {
          isResolved
          resolvedBy { login }
          comments(first: 100) {
            nodes { databaseId }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


def fetch_review_thread_resolutions(repo: str, number: int) -> list[dict]:
    """Review-thread resolution state from GraphQL.

    GitHub REST review comments do not include thread resolution state. The
    GraphQL thread connection does, keyed back to REST comments by
    PullRequestReviewComment.databaseId, which matches the REST `id`.
    """
    owner, name = repo.split("/", 1)
    cursor = None
    threads: list[dict] = []

    while True:
        payload = _graphql(_REVIEW_THREAD_RESOLUTIONS_QUERY, {
            "owner": owner,
            "name": name,
            "number": int(number),
            "cursor": cursor,
        })
        connection = (
            payload.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewThreads", {})
        )
        for node in connection.get("nodes", []) or []:
            comment_ids = [
                str(c["databaseId"])
                for c in (node.get("comments", {}).get("nodes", []) or [])
                if c.get("databaseId") is not None
            ]
            resolved_by = node.get("resolvedBy") or {}
            threads.append({
                "comment_ids": comment_ids,
                "resolved": bool(node.get("isResolved")),
                "resolved_by": resolved_by.get("login"),
            })

        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return threads


def _parse_paginated(raw: str) -> list[dict]:
    """`gh api --paginate` concatenates JSON arrays back-to-back as
    `][`. Split and merge. Empty result returns []."""
    raw = raw.strip()
    if not raw:
        return []
    # Sequential JSON arrays from paginate: `[...][...]` → `[...,...]`.
    merged = "[" + raw[1:-1].replace("][", ",") + "]" if raw.startswith("[") else raw
    parsed = json.loads(merged)
    return parsed if isinstance(parsed, list) else [parsed]


def post_review_comment(
    repo: str,
    number: int,
    *,
    body: str,
    commit_id: str,
    path: str,
    line: int,
    side: str = "RIGHT",
    start_line: int | None = None,
) -> dict:
    """POST an inline review comment. Returns the created comment dict
    (id, html_url, etc.). `commit_id` must be a SHA the PR knows about
    — usually `Session.current_head`.
    """
    payload: dict = {
        "body": body,
        "commit_id": commit_id,
        "path": path,
        "line": line,
        "side": side,
    }
    if start_line is not None and start_line != line:
        payload["start_line"] = start_line
        payload["start_side"] = side
    out = _api(
        f"repos/{repo}/pulls/{number}/comments",
        method="POST", payload=payload,
    )
    return json.loads(out)


def post_issue_comment(repo: str, number: int, *, body: str) -> dict:
    """POST a PR-level (top-of-PR) comment. Returns the created comment dict."""
    out = _api(
        f"repos/{repo}/issues/{number}/comments",
        method="POST", payload={"body": body},
    )
    return json.loads(out)


def post_review_reply(repo: str, number: int, parent_id: str, *,
                      body: str) -> dict:
    """POST a reply to an existing review comment. The reply auto-inherits
    path/line/commit from the parent — only `body` is needed.
    """
    out = _api(
        f"repos/{repo}/pulls/{number}/comments/{parent_id}/replies",
        method="POST", payload={"body": body},
    )
    return json.loads(out)


def patch_review_comment(repo: str, ext_id: str, *, body: str) -> dict:
    """PATCH an existing review comment's body. Note the endpoint omits the
    PR number — review comments are addressed globally by id within a repo.
    """
    out = _api(
        f"repos/{repo}/pulls/comments/{ext_id}",
        method="PATCH", payload={"body": body},
    )
    return json.loads(out)


def patch_issue_comment(repo: str, ext_id: str, *, body: str) -> dict:
    """PATCH an existing issue/PR-level comment's body. Endpoint omits the
    issue number — issue comments are addressed globally by id within a repo.
    """
    out = _api(
        f"repos/{repo}/issues/comments/{ext_id}",
        method="PATCH", payload={"body": body},
    )
    return json.loads(out)


def post_pr_review(
    repo: str,
    number: int,
    *,
    event: str,
    body: str = "",
    commit_id: str | None = None,
    comments: list[dict] | None = None,
) -> dict:
    """Submit a PR review (verdict). `event` must be one of APPROVE,
    REQUEST_CHANGES, COMMENT (GitHub's enum). `body` is optional except
    REQUEST_CHANGES which requires it. `comments` batches inline review
    comments into the same submitted review.
    """
    if event not in {"APPROVE", "REQUEST_CHANGES", "COMMENT"}:
        raise ValueError(f"event must be APPROVE/REQUEST_CHANGES/COMMENT, got {event!r}")
    payload: dict = {"event": event}
    if body:
        payload["body"] = body
    if commit_id:
        payload["commit_id"] = commit_id
    if comments:
        payload["comments"] = comments
    out = _api(
        f"repos/{repo}/pulls/{number}/reviews",
        method="POST", payload=payload,
    )
    return json.loads(out)

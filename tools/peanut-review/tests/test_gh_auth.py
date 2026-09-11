"""Account selection and fail-closed publishing through the CLI and one web server."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from peanut_review import gh, gh_push, models, session, store
from peanut_review.cli import main
from peanut_review.web import app
from .test_gh import _stage_workspace
from .test_web import _get, _post


PUBLIC = models.GitHubAccount("github.com", "public-login", 101)
WORK = models.GitHubAccount("github.com", "work-login", 202)


@pytest.fixture
def fake_gh(monkeypatch):
    """Replace gh only; preserve real git and HTTP execution."""
    original_run = subprocess.run
    state = SimpleNamespace(
        calls=[],
        tokens={"public-login": "public-test-token", "work-login": "work-test-token"},
        users={
            "public-test-token": {"login": PUBLIC.login, "id": PUBLIC.user_id},
            "work-test-token": {"login": WORK.login, "id": WORK.user_id},
        },
        on_write=None,
        token_failure=None,
        status_failure=None,
        api_failure=None,
        pr_url=None,
        head_sha="abc",
        base_sha="def",
    )
    monkeypatch.setenv(gh.GH_BIN_ENV, "test-gh-auth")

    def run(cmd, **kwargs):
        if cmd[0] != "test-gh-auth":
            return original_run(cmd, **kwargs)
        args, env = cmd[1:], kwargs["env"]
        state.calls.append(
            {"args": args, "env": env.copy(), "input": kwargs.get("input")}
        )
        if args[:2] == ["auth", "status"]:
            assert all(key not in env for key in gh._TOKEN_ENV)
            assert "GH_HOST" not in env and "GH_REPO" not in env
            if state.status_failure:
                if isinstance(state.status_failure, BaseException):
                    raise state.status_failure
                return subprocess.CompletedProcess(cmd, 0, state.status_failure, "")
            host = args[args.index("--hostname") + 1]
            output = json.dumps({"hosts": {host: [
                {"login": login} for login in state.tokens
            ]}})
        elif args[:2] == ["auth", "token"]:
            assert all(key not in env for key in gh._TOKEN_ENV)
            assert "GH_HOST" not in env and "GH_REPO" not in env
            if state.token_failure:
                if isinstance(state.token_failure, BaseException):
                    raise state.token_failure
                return subprocess.CompletedProcess(
                    cmd, 1, state.token_failure, state.token_failure
                )
            login = args[args.index("--user") + 1]
            output = state.tokens.get(login, "")
        else:
            assert env["GH_PROMPT_DISABLED"] == "1"
            assert "GH_DEBUG" not in env and "GH_REPO" not in env
            token = env.get("GH_TOKEN") or env.get("GH_ENTERPRISE_TOKEN")
            assert token in state.users
            if state.api_failure:
                return subprocess.CompletedProcess(cmd, 1, token, token)
            if args[:2] == ["api", "user"]:
                output = json.dumps(state.users[token])
            elif args[:2] == ["pr", "view"]:
                host, repo = args[args.index("--repo") + 1].split("/", 1)
                output = json.dumps(
                    {
                        "number": int(args[2]),
                        "headRefOid": state.head_sha,
                        "baseRefOid": state.base_sha,
                        "url": state.pr_url or f"https://{host}/{repo.lower()}/pull/{args[2]}",
                        "title": "Review",
                    }
                )
            elif (
                "-X" in args
                and args[args.index("-X") + 1] in {"POST", "PATCH"}
                and "graphql" not in args
            ):
                if state.on_write:
                    state.on_write()
                output = json.dumps(
                    {
                        "id": state.users[token]["id"],
                        "html_url": "https://github.com/review",
                    }
                )
            elif "graphql" in args:
                output = json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [],
                                        "pageInfo": {"hasNextPage": False},
                                    }
                                }
                            }
                        }
                    }
                )
            else:
                output = "[]"
        return subprocess.CompletedProcess(cmd, 0, output, "")

    monkeypatch.setattr(gh.subprocess, "run", run)
    return state


def make_session(root: Path, account=PUBLIC, *, name="public", hostname="github.com"):
    directory = root / name
    directory.mkdir(parents=True)
    s = models.Session(
        id=name,
        workspace=str(root),
        base_ref="def",
        topic_ref="abc",
        current_head="abc",
        github=models.GitHubPR(
            repo=f"example/{name}",
            number=42,
            url=f"https://{hostname}/example/{name}/pull/42",
            hostname=hostname,
            account=account,
        ),
    )
    session.save_session(directory, s)
    store.append_comment(
        directory, models.Comment(author="human", body=f"Feedback for {name}")
    )
    return directory, s


def writes(fake):
    return [
        c
        for c in fake.calls
        if "-X" in c["args"]
        and c["args"][c["args"].index("-X") + 1] in {"POST", "PATCH"}
        and "graphql" not in c["args"]
    ]


def test_one_server_publishes_two_accounts_concurrently(tmp_path, fake_gh, monkeypatch):
    for key in gh._TOKEN_ENV:
        monkeypatch.setenv(key, "wrong-ambient-token")
    monkeypatch.setenv("GH_HOST", "wrong.example")
    monkeypatch.setenv("GH_REPO", "wrong/repo")
    monkeypatch.setenv("GH_DEBUG", "api")
    directories = [
        make_session(tmp_path, PUBLIC),
        make_session(tmp_path, WORK, name="work"),
    ]
    registry = app.SessionRegistry()
    for directory, _ in directories:
        registry.bind(directory)
    server = app.make_server(host="127.0.0.1", port=0, registry=registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    barrier = threading.Barrier(2)
    fake_gh.on_write = lambda: barrier.wait(timeout=10)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        previews = {}
        for directory, s in directories:
            code, raw = _get(f"{base}/{s.id}/api/gh/preview")
            assert code == 200
            preview = json.loads(raw)
            assert preview["github_account"] == s.github.account.login
            assert preview["github_account_error"] is None
            assert "test-token" not in raw.decode()
            previews[s.id] = preview

        def publish(item):
            directory, s = item
            return _post(
                f"{base}/{s.id}/api/gh/push",
                {
                    "github_identity": previews[s.id]["github_identity"],
                    "comment_ids": [store.read_all_comments(directory)[0].id],
                },
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(publish, directories))
        assert all(code == 200 and result["pushed"] == 1 for code, result in results)
        assert len(writes(fake_gh)) == 2
        for call in writes(fake_gh):
            name = (
                "work"
                if "repos/example/work/pulls/42/reviews" in call["args"]
                else "public"
            )
            assert call["env"]["GH_TOKEN"] == f"{name}-test-token"
            assert call["env"]["GH_HOST"] == "github.com"
            assert all(
                key not in call["env"] for key in gh._TOKEN_ENV if key != "GH_TOKEN"
            )
        assert (
            len([c for c in fake_gh.calls if c["args"][:2] == ["auth", "token"]]) == 4
        )
        for directory, s in directories:
            saved = session.load_session(directory)
            assert saved.last_github_push_at
            assert saved.github.account == s.github.account
            assert "test-token" not in (directory / "session.json").read_text()
        assert gh._CREDENTIALS.get() is None
        assert os.environ["GH_TOKEN"] == "wrong-ambient-token"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "user", [{"login": "other", "id": 101}, {"login": PUBLIC.login, "id": 999}]
)
def test_wrong_login_or_reused_username_blocks_entire_push(tmp_path, fake_gh, user):
    directory, s = make_session(tmp_path)
    fake_gh.users["public-test-token"] = user
    with pytest.raises(gh.RepoAccountError, match="do not match"):
        gh_push.execute_push(
            directory,
            s,
            s.github,
            gh_push.plan_push(store.read_all_comments(directory)),
        )
    assert writes(fake_gh) == []
    assert gh._CREDENTIALS.get() is None


@pytest.mark.parametrize(
    "failure",
    [
        "secret-token-output",
        subprocess.TimeoutExpired("gh", 15, output="secret-token-output"),
        FileNotFoundError("secret-token-output"),
    ],
)
def test_credential_errors_do_not_expose_output(fake_gh, failure):
    fake_gh.token_failure = failure
    with pytest.raises(gh.RepoAccountError) as error:
        with gh.account_auth(PUBLIC.hostname, PUBLIC.login):
            pytest.fail("must not authenticate")
    assert "secret-token-output" not in str(error.value)
    assert all(c["args"][0] == "auth" for c in fake_gh.calls)


def test_missing_selected_token_never_falls_back(fake_gh, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ambient-secret")
    del fake_gh.tokens[PUBLIC.login]
    with pytest.raises(gh.RepoAccountError, match="no stored credentials"):
        with gh.account_auth(PUBLIC.hostname, PUBLIC.login):
            pytest.fail("must not authenticate")
    assert all(c["args"][0] == "auth" for c in fake_gh.calls)
    assert [c["args"][-1] for c in fake_gh.calls
            if c["args"][:2] == ["auth", "token"]] == [PUBLIC.login]


@pytest.mark.parametrize("stored_login, requested_login", [
    ("public-login", "PUBLIC-LOGIN"),
    ("Public-Login", "public-login"),
])
@pytest.mark.parametrize("expected", [None, PUBLIC])
def test_mixed_case_login_selects_stored_account(
    fake_gh, stored_login, requested_login, expected,
):
    fake_gh.tokens[stored_login] = fake_gh.tokens.pop(PUBLIC.login)
    with gh.account_auth("github.com", requested_login, expected=expected) as account:
        assert account == PUBLIC
        gh.post_pr_review("example/repo", 42, event="COMMENT", body="feedback")
    assert [c["args"][-1] for c in fake_gh.calls
            if c["args"][:2] == ["auth", "token"]] == [requested_login, stored_login]
    assert writes(fake_gh)[0]["env"]["GH_TOKEN"] == "public-test-token"
    assert gh._CREDENTIALS.get() is None


@pytest.mark.parametrize("failure", [
    "secret-status-output",
    '{"hosts": null}',
    subprocess.TimeoutExpired("gh", 30, output="secret-status-output"),
])
def test_account_discovery_errors_do_not_expose_output(fake_gh, failure):
    fake_gh.status_failure = failure
    with pytest.raises(gh.RepoAccountError) as error:
        with gh.account_auth("github.com", PUBLIC.login.upper()):
            pytest.fail("must not authenticate")
    assert "secret-status-output" not in str(error.value)
    assert all(c["args"][0] == "auth" for c in fake_gh.calls)


def test_host_specific_token_and_graphql_routing(fake_gh):
    for host, token_key in [
        ("enterprise.example", "GH_ENTERPRISE_TOKEN"),
        ("company.ghe.com", "GH_TOKEN"),
    ]:
        with gh.account_auth(host, PUBLIC.login):
            gh.fetch_review_thread_resolutions("example/repo", 42)
            gh.post_pr_review("example/repo", 42, event="COMMENT", body="feedback")
        for call in fake_gh.calls[-3:]:
            assert call["env"][token_key] == "public-test-token"
            assert call["args"][call["args"].index("--hostname") + 1] == host


def test_one_token_is_reused_for_review_replies_and_edits(tmp_path, fake_gh):
    directory, s = make_session(tmp_path)
    parent = store.append_comment(
        directory,
        models.Comment(
            author="human",
            file="file.py",
            line=1,
            body="parent",
            external_id="1",
            external_source="github",
            external_synced_body="parent",
        ),
    )
    store.append_comment(
        directory,
        models.Comment(
            author="human", file="file.py", line=1, body="reply", reply_to=parent.id
        ),
    )
    store.append_comment(
        directory,
        models.Comment(
            author="human",
            file="file.py",
            line=1,
            body="edited",
            external_id="2",
            external_source="github",
            external_synced_body="old",
        ),
    )

    def rotate():
        fake_gh.tokens[PUBLIC.login] = "new-unverified-token"

    fake_gh.on_write = rotate
    result = gh_push.execute_push(
        directory, s, s.github, gh_push.plan_push(store.read_all_comments(directory))
    )
    assert result.failed == 0 and result.pushed == 3
    assert len([c for c in fake_gh.calls if c["args"][:2] == ["auth", "token"]]) == 1
    assert len(writes(fake_gh)) == 3
    assert all(c["env"]["GH_TOKEN"] == "public-test-token" for c in writes(fake_gh))


@pytest.mark.parametrize(
    "command",
    [
        ["gh-push"],
        ["gh-push", "--dry-run"],
        ["gh-push-verdict"],
        ["gh-pull"],
        ["gh-auth"],
    ],
)
def test_legacy_session_requires_explicit_binding(tmp_path, fake_gh, command):
    directory, _ = make_session(tmp_path, None)
    (directory / "result.json").write_text(models.Verdict(decision="approve").to_json())
    assert main(["--session", str(directory), *command]) == 1
    assert fake_gh.calls == []


def test_bind_legacy_session_then_publish_verdict(tmp_path, fake_gh):
    directory, _ = make_session(tmp_path, None)
    assert (
        main(["--session", str(directory), "gh-auth", "--account", PUBLIC.login]) == 0
    )
    assert session.load_session(directory).github.account == PUBLIC
    assert writes(fake_gh) == []
    assert "test-token" not in (directory / "session.json").read_text()
    assert main(["--session", str(directory), "gh-auth", "--account", WORK.login]) == 1
    (directory / "result.json").write_text(models.Verdict(decision="approve").to_json())
    assert main(["--session", str(directory), "gh-push-verdict", "--dry-run"]) == 0
    assert writes(fake_gh) == []
    assert main(["--session", str(directory), "gh-push-verdict"]) == 0
    assert writes(fake_gh)[0]["env"]["GH_TOKEN"] == "public-test-token"


def test_stale_preview_identity_is_rejected(tmp_path, fake_gh):
    directory, s = make_session(tmp_path)
    stale = gh.publish_identity(s.github)
    s.github.account = WORK
    session.save_session(directory, s)
    registry = app.SessionRegistry()
    registry.bind(directory)
    server = app.make_server(host="127.0.0.1", port=0, registry=registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        code, data = _post(
            f"http://127.0.0.1:{server.server_port}/{s.id}/api/gh/push",
            {
                "github_identity": stale,
                "comment_ids": [store.read_all_comments(directory)[0].id],
            },
        )
        assert code == 409 and "reload" in data["error"]
        assert fake_gh.calls == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_read_helpers_require_authentication(fake_gh):
    with pytest.raises(gh.RepoAccountError):
        gh.fetch_pr_info("example/repo", 42)
    assert fake_gh.calls == []


def test_api_error_redacts_selected_token(fake_gh):
    with gh.account_auth(PUBLIC.hostname, PUBLIC.login):
        fake_gh.api_failure = True
        with pytest.raises(gh.GhError) as error:
            gh.post_pr_review("example/repo", 42, event="COMMENT", body="feedback")
        assert "public-test-token" not in str(error.value)
        assert "public-test-token" not in error.value.stdout
        assert "public-test-token" not in error.value.stderr


def test_pr_host_is_preserved_when_loading_legacy_metadata():
    pr = models.GitHubPR.from_dict(
        {
            "repo": "example/repo",
            "number": 42,
            "url": "https://enterprise.example/example/repo/pull/42",
        }
    )
    assert pr.hostname == "enterprise.example"
    assert pr.account is None
    assert gh.hostname_for_spec(pr.url) == "enterprise.example"
    assert models.GitHubPR.from_dict(pr.to_dict()) == pr


def test_explicit_account_overrides_repository_default(tmp_path, fake_gh, monkeypatch):
    from peanut_review.cli import _read_github_pr

    monkeypatch.setattr(gh, "repo_account", lambda _: PUBLIC.login)
    info = _read_github_pr("example/repo#42", workspace=str(tmp_path), login=WORK.login)
    assert info.account == WORK
    assert all(
        c["env"]["GH_TOKEN"] == "work-test-token"
        for c in fake_gh.calls
        if c["args"][:2] != ["auth", "token"]
    )


def test_saved_binding_ignores_changed_repository_default(
    tmp_path, fake_gh, monkeypatch
):
    from peanut_review.cli import _read_github_pr

    _, s = make_session(tmp_path, PUBLIC)
    monkeypatch.setattr(gh, "repo_account", lambda _: WORK.login)
    info = _read_github_pr(s.github.url, workspace=str(tmp_path), existing=s.github)
    assert info.account == PUBLIC
    assert all(
        c["env"]["GH_TOKEN"] == "public-test-token"
        for c in fake_gh.calls
        if c["args"][:2] != ["auth", "token"]
    )


def test_repository_casing_matches_canonical_url_and_saved_binding(tmp_path, fake_gh):
    from peanut_review.cli import _read_github_pr

    _, s = make_session(tmp_path)
    original_identity = gh.publish_identity(s.github)
    s.github.repo = "EXAMPLE/Public"
    assert gh.publish_identity(s.github) == original_identity
    info = _read_github_pr(
        "example/PUBLIC#42", workspace=str(tmp_path), existing=s.github,
    )
    assert info.url == "https://github.com/example/public/pull/42"
    assert info.account == PUBLIC
    assert writes(fake_gh) == []


@pytest.mark.parametrize("url", [
    "https://elsewhere.example/example/public/pull/42",
    "https://github.com/other/public/pull/42",
    "https://github.com/example/other/pull/42",
    "https://github.com/example/public/pull/43",
])
def test_repository_case_normalization_still_rejects_different_targets(
    tmp_path, fake_gh, url,
):
    _, s = make_session(tmp_path)
    fake_gh.pr_url = url
    with gh.account_auth(PUBLIC.hostname, PUBLIC.login):
        with pytest.raises(gh.RepoAccountError, match="outside the selected target"):
            gh.fetch_pr_info("EXAMPLE/Public", 42)
    s.github.url = url
    with pytest.raises(gh.RepoAccountError, match="does not match"):
        gh.publish_identity(s.github)
    assert writes(fake_gh) == []


@pytest.mark.parametrize("origin_host, host_override", [
    ("github.com", None),
    ("public-ssh-alias", "github.com"),
])
def test_bare_number_reuse_matches_origin_before_selecting_account(
    tmp_path, fake_gh, origin_host, host_override,
):
    from peanut_review.cli import _reused_pr_session

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run([
        "git", "-C", str(tmp_path), "remote", "add", "origin",
        f"git@{origin_host}:example/public.git",
    ], check=True)
    enterprise = models.GitHubAccount("enterprise.example", WORK.login, WORK.user_id)
    old_dir, old = make_session(
        tmp_path, enterprise, name="old-host", hostname=enterprise.hostname,
    )
    old.github.repo = "example/public"
    old.github.url = "https://enterprise.example/example/public/pull/42"
    session.save_session(old_dir, old)
    args = SimpleNamespace(
        reuse=True, session=None, id=None, pr="42", gh_host=host_override,
    )
    cfg = {"reviewRoot": str(tmp_path), "repoPath": str(tmp_path)}
    assert _reused_pr_session(args, cfg) == (None, None)
    assert fake_gh.calls == []

    public_dir, public = make_session(tmp_path)
    assert _reused_pr_session(args, cfg)[0] == public_dir
    config = tmp_path / ".peanut-review.json"
    config.write_text(json.dumps({
        "reviewRoot": str(tmp_path), "workspaceRoot": str(tmp_path),
        "repoRelative": ".", "agents": [
            {"name": "Vera", "model": "test", "persona": "vera.md"},
            {"name": "Curator", "model": "test", "role": "curator"},
        ],
    }))
    command = ["start", "42", "--reuse", "--no-launch", "--config", str(config)]
    if host_override:
        command += ["--gh-host", host_override]
    assert main(command) == 0
    assert session.load_session(public_dir).github.account == public.github.account
    assert session.load_session(old_dir).github == old.github
    assert all(c["env"].get("GH_ENTERPRISE_TOKEN") is None for c in fake_gh.calls)
    assert writes(fake_gh) == []


def test_explicit_session_cannot_override_bare_number_origin(tmp_path, fake_gh):
    from peanut_review.cli import _read_github_pr

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run([
        "git", "-C", str(tmp_path), "remote", "add", "origin",
        "https://github.com/example/public.git",
    ], check=True)
    enterprise = models.GitHubAccount("enterprise.example", WORK.login, WORK.user_id)
    _, saved = make_session(tmp_path, enterprise, hostname=enterprise.hostname)
    with pytest.raises(ValueError, match="PR host does not match"):
        _read_github_pr("42", workspace=str(tmp_path), existing=saved.github)
    assert fake_gh.calls == []


@pytest.mark.parametrize("spec, account_args, recovery", [
    ("42", ["--gh-account", PUBLIC.login], "full PR URL"),
    ("example/public#42", [], "--gh-account"),
])
@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired("git", 10, output="private-git-output"),
    FileNotFoundError("private-git-output"),
])
def test_local_git_lookup_failures_return_cli_errors(
    tmp_path, fake_gh, monkeypatch, capsys, spec, account_args, recovery, failure,
):
    original_run = subprocess.run

    def fail_git(cmd, **kwargs):
        if cmd[0] == "git":
            raise failure
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(gh.subprocess, "run", fail_git)
    directory = tmp_path / "session"
    assert main([
        "--session", str(directory), "init", "--workspace", str(tmp_path),
        "--gh-pr", spec, *account_args,
    ]) == 1
    error = capsys.readouterr().err
    assert "Error:" in error and recovery in error
    assert "Traceback" not in error and "private-git-output" not in error
    assert not directory.exists()
    assert fake_gh.calls == []


@pytest.mark.parametrize("second_account, second_url, conflict", [
    (WORK, "https://github.com/example/repo/pull/42", True),
    (PUBLIC, "https://enterprise.example/example/repo/pull/42", True),
    (PUBLIC, "https://github.com/example/other/pull/42", True),
    (PUBLIC, "https://github.com/example/repo/pull/43", True),
    (PUBLIC, "https://github.com/example/repo/pull/42", False),
    (PUBLIC, "https://github.com/EXAMPLE/Repo/pull/42", False),
])
def test_concurrent_initial_links_preserve_account_and_target(
    tmp_path, fake_gh, monkeypatch, capsys, second_account, second_url, conflict,
):
    workspace = _stage_workspace(tmp_path)
    fake_gh.head_sha = subprocess.check_output(
        ["git", "-C", workspace, "rev-parse", "HEAD"], text=True,
    ).strip()
    fake_gh.base_sha = subprocess.check_output(
        ["git", "-C", workspace, "rev-parse", "HEAD~"], text=True,
    ).strip()
    directory = tmp_path / "session"
    session.create_session(
        workspace=workspace, base_ref=fake_gh.base_sha,
        topic_ref=fake_gh.head_sha, session_dir=str(directory),
    )
    barrier = threading.Barrier(2)
    real_sync = session.sync_session_snapshot

    def sync(*args, **kwargs):
        # Both CLI calls have read the initially local session before either
        # enters the real locked update.
        barrier.wait(timeout=10)
        return real_sync(*args, **kwargs)

    monkeypatch.setattr(session, "sync_session_snapshot", sync)
    attempts = [
        (PUBLIC, "https://github.com/example/repo/pull/42"),
        (second_account, second_url),
    ]

    def link(attempt):
        account, url = attempt
        return main([
            "--session", str(directory), "sync-pr", url,
            "--gh-account", account.login,
        ])

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(link, attempts))

    assert sorted(results) == ([0, 1] if conflict else [0, 0])
    saved = session.load_session(directory)
    for result, (account, url) in zip(results, attempts):
        if result != 0:
            continue
        hostname = gh.hostname_for_spec(url)
        repo, number = gh.parse_pr_spec(url)
        assert gh.publish_identity(saved.github) == {
            "hostname": hostname, "repo": repo.casefold(), "number": number,
            "account": {
                "hostname": hostname, "login": account.login,
                "user_id": account.user_id,
            },
        }
    error = capsys.readouterr().err
    if conflict:
        assert "different GitHub target or account" in error
    else:
        assert error == ""
    assert writes(fake_gh) == []


def test_binding_preserves_concurrent_session_updates(tmp_path):
    directory, s = make_session(tmp_path, None)
    updated = session.load_session(directory)
    updated.last_github_push_at = "concurrent-update"
    session.save_session(directory, updated)
    session.bind_github_account(directory, s.github, PUBLIC)
    saved = session.load_session(directory)
    assert saved.last_github_push_at == "concurrent-update"
    assert saved.github.account == PUBLIC
    with pytest.raises(ValueError, match="session changed"):
        session.bind_github_account(directory, s.github, WORK)
    assert session.load_session(directory).github.account == PUBLIC


def test_nested_account_operation_restores_outer_credentials(fake_gh):
    with gh.account_auth(PUBLIC.hostname, PUBLIC.login):
        with gh.account_auth(WORK.hostname, WORK.login):
            assert gh.current_account() == WORK
        assert gh.current_account() == PUBLIC
        gh.post_pr_review("example/repo", 42, event="COMMENT", body="feedback")
    assert writes(fake_gh)[0]["env"]["GH_TOKEN"] == "public-test-token"
    assert gh._CREDENTIALS.get() is None

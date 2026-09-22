"""Queue discovery, revision accounting and real Git worktree lifecycle tests."""
from __future__ import annotations

import copy
import json
import subprocess
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import pytest

from peanut_review import gh, queue_jobs, review_queue, session as sess, store
from peanut_review.models import GitHubAccount, GitHubPR
from peanut_review.web.app import SessionRegistry


ACCOUNT = GitHubAccount("github.com", "alice", 10)
OTHER = GitHubAccount("github.com", "bob", 20)


def remote(**updates):
    result = {
        "repo": "acme/widget", "number": 1, "url": "https://github.com/acme/widget/pull/1",
        "title": "Make widgets", "body": "The requested change", "author": "carol",
        "head_sha": "a" * 40, "base_sha": "b" * 40, "head_ref": "feature/widget",
        "base_ref": "main", "state": "open", "draft": False, "request_kind": "direct",
        "updated_at": review_queue.now(), "checked_at": review_queue.now(), "error": "",
    }
    result.update(updates)
    return result


def config(tmp_path):
    return {"pollSeconds": 120, "accounts": [{
        "hostname": "github.com", "login": "alice", "label": "Work",
        "cloneRoot": str(tmp_path / "clones"), "worktreeRoot": str(tmp_path / "worktrees"),
        "reviewConfig": str(tmp_path / "review.json"), "repositories": {},
    }]}


@pytest.fixture
def queue(tmp_path):
    root = tmp_path / "sessions"
    registry = SessionRegistry([root])
    q = review_queue.ReviewQueue(root, config(tmp_path), registry)
    yield q
    q.close()


def add_item(q, account=ACCOUNT, **updates):
    item = {**remote(), "account": asdict(account), "requested": True, **updates}
    key = review_queue.identity_key(account, item["repo"], item["number"])
    item["key"] = key
    q.state["items"][key] = item
    q._save()
    return key


@contextmanager
def authenticate(host, login, expected=None):
    account = ACCOUNT if login == "alice" else OTHER
    assert host == account.hostname
    if expected:
        assert expected == account
    yield account


def test_search_paginates_and_rejects_incomplete(monkeypatch):
    calls = []
    def api(endpoint):
        calls.append(endpoint)
        return json.dumps({"total_count": 101, "items": [{"number": n} for n in (range(100) if "&page=1" in endpoint else [100])]})
    monkeypatch.setattr(gh, "_api", api)
    assert len(review_queue.search_requests("alice")) == 101
    assert len(calls) == 2
    assert "review-requested%3Aalice" in calls[0]
    for result in ({"incomplete_results": True}, {"total_count": 1001}):
        monkeypatch.setattr(gh, "_api", lambda endpoint: json.dumps(result))
        with pytest.raises(RuntimeError, match="incomplete"):
            review_queue.search_requests("alice")


def test_fetch_validates_target_and_request_kind(monkeypatch):
    data = {"html_url": "https://github.com/acme/widget/pull/1", "head": {"sha": "a" * 40, "ref": "feature"},
            "base": {"sha": "b" * 40, "ref": "main"}, "title": "Widgets", "user": {"login": "carol"},
            "state": "open", "updated_at": review_queue.now(), "requested_reviewers": [{"login": "ALICE"}]}
    monkeypatch.setattr(gh, "current_account", lambda: ACCOUNT)
    monkeypatch.setattr(gh, "_api", lambda endpoint: json.dumps(data))
    assert review_queue.fetch_pr("acme/widget", 1)["request_kind"] == "direct"
    data["requested_reviewers"] = []
    assert review_queue.fetch_pr("acme/widget", 1)["request_kind"] == "team"
    data["html_url"] = "https://elsewhere.example/acme/widget/pull/1"
    with pytest.raises(ValueError, match="different PR"):
        review_queue.fetch_pr("acme/widget", 1)


def test_multi_account_discovery_retains_followed_and_partial_failures(queue, monkeypatch):
    second = {**queue.config["accounts"][0], "login": "bob", "label": "Other"}
    queue.config["accounts"].append(second)
    monkeypatch.setattr(gh, "account_auth", authenticate)
    monkeypatch.setattr(review_queue, "search_requests", lambda login: [{"html_url": remote()["url"]}])
    monkeypatch.setattr(review_queue, "fetch_pr", lambda repo, number: remote())
    queue.refresh()
    rows = queue.payload()["items"]
    assert len(rows) == 2 and rows[0]["key"] != rows[1]["key"]
    assert {r["account"]["user_id"] for r in rows} == {10, 20}
    def next_search(login):
        if login == "bob":
            raise gh.RepoAccountError("Credentials expired")
        return []
    monkeypatch.setattr(review_queue, "search_requests", next_search)
    queue.refresh()
    rows = {r["account"]["login"]: r for r in queue.payload()["items"]}
    assert not rows["alice"]["requested"]
    assert rows["bob"]["requested"]
    assert rows["bob"]["freshness"] == "unknown"
    assert "expired" in rows["bob"]["error"]
    assert len(queue.state["items"]) == 2


def test_freshness_is_completed_snapshot_not_updated_time(queue):
    key = add_item(queue)
    item = queue.state["items"][key]
    assert queue.payload()["items"][0]["freshness"] == "unreviewed"
    item["completed_snapshot"] = review_queue.snapshot(item)
    assert queue.payload()["items"][0]["freshness"] == "current"
    item["updated_at"] = "2099-01-01T00:00:00+00:00"
    assert queue.payload()["items"][0]["freshness"] == "current"
    item["head_sha"] = "c" * 40
    assert queue.payload()["items"][0]["freshness"] == "stale"
    item["head_sha"] = "a" * 40
    item["base_sha"] = "d" * 40
    assert queue.payload()["items"][0]["freshness"] == "stale"
    item["base_sha"] = "b" * 40
    item["base_ref"] = "release"
    assert queue.payload()["items"][0]["freshness"] == "stale"
    item["error"] = "Network unavailable"
    assert queue.payload()["items"][0]["freshness"] == "unknown"
    assert "body" not in queue.payload()["items"][0]


def test_expired_cache_does_not_claim_current(queue):
    key = add_item(queue, checked_at="2000-01-01T00:00:00+00:00")
    queue.state["items"][key]["completed_snapshot"] = review_queue.snapshot(queue.state["items"][key])
    assert queue.payload()["items"][0]["freshness"] == "unknown"


def test_duplicate_start_restart_and_service_ownership(queue):
    key = add_item(queue)
    first = queue.enqueue(key)
    assert queue.enqueue(key) == first
    assert first["status"] == "queued"
    with pytest.raises(ValueError, match="already serving"):
        review_queue.ReviewQueue(queue.root, queue.config, queue.registry)
    queue.close()
    replacement = review_queue.ReviewQueue(queue.root, queue.config, queue.registry)
    try:
        assert replacement.item(key)["job"]["status"] == "interrupted"
        assert replacement.enqueue(key)["id"] != first["id"]
    finally:
        replacement.close()


def test_removed_account_is_not_exposed(queue):
    add_item(queue, account=OTHER)
    assert queue.payload()["items"] == []


def test_invalid_setup_is_visible_and_cannot_start(queue):
    queue.config["accounts"][0].pop("reviewConfig")
    key = add_item(queue)
    assert "reviewConfig" in queue.payload()["items"][0]["setup_error"]
    with pytest.raises(ValueError, match="reviewConfig"):
        queue.enqueue(key)


def test_closed_pr_cannot_start(queue):
    key = add_item(queue, state="merged")
    with pytest.raises(ValueError, match="open PR"):
        queue.enqueue(key)


def test_config_paths_and_argv_validation(tmp_path):
    raw = config(tmp_path)
    raw["accounts"][0]["cloneRoot"] = "clones"
    raw["accounts"][0]["repositories"] = {"Acme/Widget": {"path": "repo", "prepare": [["cmake", "--build", "build"]]}}
    path = tmp_path / "queue.json"
    path.write_text(json.dumps(raw))
    parsed = review_queue.load_config(path)
    assert parsed["accounts"][0]["cloneRoot"] == str(tmp_path / "clones")
    assert parsed["accounts"][0]["repositories"]["acme/widget"]["path"] == str(tmp_path / "repo")
    raw["accounts"][0]["prepare"] = ["echo unsafe-shell-string"]
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="argv"):
        review_queue.load_config(path)


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    queue_jobs.git(path, "init", "-b", "main")
    queue_jobs.git(path, "config", "user.name", "Test")
    queue_jobs.git(path, "config", "user.email", "test@example.invalid")
    (path / "file").write_text("base\n")
    queue_jobs.git(path, "add", "file")
    queue_jobs.git(path, "commit", "-m", "base")
    base = queue_jobs.git(path, "rev-parse", "HEAD")
    (path / "file").write_text("feature\n")
    queue_jobs.git(path, "commit", "-am", "feature")
    head = queue_jobs.git(path, "rev-parse", "HEAD")
    return path, base, head


def configure_job(queue, repository, monkeypatch):
    path, base, head = repository
    cfg = queue.config["accounts"][0]
    cfg["repositories"] = {"acme/widget": {"path": str(path)}}
    Path(cfg["reviewConfig"]).write_text(json.dumps({
        "agents": [{"name": "Vera", "model": "test", "runner": "codex", "persona": "vera.md"},
                   {"name": "Curator", "model": "test", "runner": "codex", "role": "curator"}],
    }))
    monkeypatch.setattr(gh, "account_auth", authenticate)
    monkeypatch.setattr(gh, "git_read", lambda *args, **kwargs: "")
    monkeypatch.setattr(review_queue, "fetch_pr", lambda repo, number: remote(head_sha=head, base_sha=base))
    monkeypatch.setattr(queue_jobs.gh_pull, "pull_comments", Mock())
    def launch_fake(directory, **kwargs):
        session = sess.load_session(directory)
        for agent in sess.reviewer_agents(session):
            (Path(directory) / "signals" / f"{agent.name}.round-done").touch()
        return []
    def curate_fake(directory):
        (Path(directory) / "signals" / "Curator.round-done").touch()
        return []
    monkeypatch.setattr(queue_jobs.launch, "launch_agents", launch_fake)
    monkeypatch.setattr(queue_jobs.launch, "rerun_agents", launch_fake)
    monkeypatch.setattr(queue_jobs.launch, "launch_curator", curate_fake)
    key = add_item(queue, head_sha=head, base_sha=base)
    queue.enqueue(key)
    return key


def test_full_start_and_refresh_preserves_history_and_lineup(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    queue_jobs.run_job(queue, key)
    item = queue.item(key)
    directory = queue.registry.get(item["session_id"])
    session = sess.load_session(directory)
    workspace = Path(session.workspace)
    assert workspace.is_relative_to(Path(queue.config["accounts"][0]["worktreeRoot"]))
    assert workspace != repository[0]
    assert queue_jobs.git(workspace, "symbolic-ref", "--short", "HEAD").startswith("users/sambhav/")
    assert item["job"]["status"] == "done"
    assert queue.payload()["items"][0]["freshness"] == "current"
    (directory / "result.json").write_text('{"decision":"approve"}')
    (directory / "log" / "Vera.log").write_text("prior run")
    first_lineup = [a.to_dict() for a in session.agents]
    # A later configuration change must not replace an existing session lineup.
    Path(queue.config["accounts"][0]["reviewConfig"]).write_text('{"agents":[]}')
    queue.enqueue(key)
    # Existing sessions should not need the current lineup to remain valid.
    queue_jobs.run_job(queue, key)
    job_id = queue.item(key)["job"]["id"]
    assert (directory / "rounds" / job_id / "result.json").exists()
    assert (directory / "rounds" / job_id / "log" / "Vera.log").read_text() == "prior run"
    assert not (directory / "result.json").exists()
    assert [a.to_dict() for a in sess.load_session(directory).agents] == first_lineup


def test_old_review_finishing_after_push_stays_stale(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    def curate_and_push(directory):
        (Path(directory) / "signals" / "Curator.round-done").touch()
        queue.state["items"][key]["head_sha"] = "f" * 40
    monkeypatch.setattr(queue_jobs.launch, "launch_curator", curate_and_push)
    queue_jobs.run_job(queue, key)
    assert queue.item(key)["job"]["status"] == "done"
    assert queue.payload()["items"][0]["freshness"] == "stale"


def test_dirty_worktree_is_preserved(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    queue_jobs.run_job(queue, key)
    directory = queue.registry.get(queue.item(key)["session_id"])
    workspace = Path(sess.load_session(directory).workspace)
    (workspace / "file").write_text("user edits\n")
    queue.enqueue(key)
    with pytest.raises(ValueError, match="local changes"):
        queue_jobs.run_job(queue, key)
    assert (workspace / "file").read_text() == "user edits\n"


def test_fast_forward_refresh_and_divergence(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    queue_jobs.run_job(queue, key)
    directory = queue.registry.get(queue.item(key)["session_id"])
    workspace = Path(sess.load_session(directory).workspace)
    path, base, original = repository
    (path / "file").write_text("remote update\n")
    queue_jobs.git(path, "commit", "-am", "update")
    latest = queue_jobs.git(path, "rev-parse", "HEAD")
    monkeypatch.setattr(review_queue, "fetch_pr", lambda repo, number: remote(head_sha=latest, base_sha=base))
    queue.enqueue(key)
    queue_jobs.run_job(queue, key)
    assert queue_jobs.git(workspace, "rev-parse", "HEAD") == latest
    monkeypatch.setattr(review_queue, "fetch_pr", lambda repo, number: remote(head_sha=original, base_sha=base))
    queue.enqueue(key)
    with pytest.raises(ValueError, match="diverged"):
        queue_jobs.run_job(queue, key)
    assert queue_jobs.git(workspace, "rev-parse", "HEAD") == latest


def test_running_agent_blocks_checkout_change(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    queue_jobs.run_job(queue, key)
    monkeypatch.setattr(queue_jobs.runtime, "inspect_agent_runtime", lambda *args: {"reviewer_live": True, "supervisor_live": True})
    queue.enqueue(key)
    with pytest.raises(ValueError, match="still using"):
        queue_jobs.run_job(queue, key)


def test_session_discovery_includes_unrequested_existing_reviews(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    queue_jobs.run_job(queue, key)
    session_id = queue.item(key)["session_id"]
    queue.state["items"].clear()
    monkeypatch.setattr(review_queue, "search_requests", lambda login: [])
    queue.refresh()
    assert queue.item(key)["session_id"] == session_id
    assert not queue.item(key)["requested"]
    # Legacy round-done files alone are not evidence of a reviewed revision.
    assert queue.payload()["items"][0]["freshness"] == "unreviewed"


def test_preparation_failure_stops_before_launch(queue, repository, monkeypatch):
    import sys
    key = configure_job(queue, repository, monkeypatch)
    queue.config["accounts"][0]["prepare"] = [[sys.executable, "-c", "raise SystemExit(2)"]]
    launch = Mock()
    monkeypatch.setattr(queue_jobs.launch, "launch_agents", launch)
    with pytest.raises(ValueError, match="Preparation failed"):
        queue_jobs.run_job(queue, key)
    launch.assert_not_called()


def test_git_fetch_uses_scoped_credentials_and_redacts_failure(monkeypatch):
    import os
    monkeypatch.setenv("GH_TOKEN", "ambient-token")
    monkeypatch.setenv("GH_HOST", "ambient.example")
    marker = gh._CREDENTIALS.set(gh._Credentials("github.com", "selected-token", ACCOUNT))
    recorded = []
    def run(argv, **kwargs):
        recorded.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="fetched", stderr="")
    monkeypatch.setattr(gh.subprocess, "run", run)
    try:
        assert gh.git_read(["fetch", "https://github.com/acme/widget.git"]) == "fetched"
        argv, options = recorded[0]
        assert options["env"]["GH_TOKEN"] == "selected-token"
        assert options["env"]["GH_HOST"] == "github.com"
        assert "selected-token" not in " ".join(argv)
        assert "credential.helper=" in argv
        assert os.environ["GH_TOKEN"] == "ambient-token"
        monkeypatch.setattr(gh.subprocess, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, stdout="", stderr="denied selected-token"))
        with pytest.raises(gh.RepoAccountError, match=r"denied \[redacted\]"):
            gh.git_read(["fetch"])
    finally:
        gh._CREDENTIALS.reset(marker)


def test_canonical_checkout_is_never_updated(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    path, base, head = repository
    directory = queue.root / "legacy"
    pr = GitHubPR(repo="acme/widget", number=1, account=ACCOUNT, head_sha=head, base_sha=base)
    sess.create_session(workspace=str(path), base_ref=base, topic_ref=head, github=pr,
                        session_id="legacy", session_dir=str(directory), agents=[
                            {"name": "Vera", "model": "test", "persona": "vera.md", "runner": "codex"},
                            {"name": "Curator", "model": "test", "runner": "codex", "role": "curator"}])
    queue.registry.bind(directory)
    queue.state["items"][key]["session_id"] = "legacy"
    queue.config["accounts"][0]["worktreeRoot"] = str(path.parent)
    with pytest.raises(ValueError, match="canonical checkout"):
        queue_jobs.run_job(queue, key)
    assert queue_jobs.git(path, "rev-parse", "HEAD") == head


def test_setup_failure_can_reuse_created_worktree(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    create = sess.create_session
    monkeypatch.setattr(sess, "create_session", Mock(side_effect=ValueError("transient setup failure")))
    with pytest.raises(ValueError, match="transient"):
        queue_jobs.run_job(queue, key)
    monkeypatch.setattr(sess, "create_session", create)
    queue_jobs.run_job(queue, key)
    assert queue.item(key)["job"]["status"] == "done"
    assert len(queue_jobs.worktrees(repository[0])) == 2


def test_removed_session_can_be_started_again(queue, repository, monkeypatch):
    import shutil
    key = configure_job(queue, repository, monkeypatch)
    queue_jobs.run_job(queue, key)
    directory = queue.registry.get(queue.item(key)["session_id"])
    shutil.rmtree(directory)
    queue.registry.rescan(force=True)
    queue.enqueue(key)
    queue_jobs.run_job(queue, key)
    assert directory.exists()
    assert queue.item(key)["job"]["status"] == "done"


def test_incomplete_curator_never_marks_review_current(queue, repository, monkeypatch):
    key = configure_job(queue, repository, monkeypatch)
    monkeypatch.setattr(queue_jobs.launch, "launch_curator", Mock(side_effect=ValueError("Curator unavailable")))
    with pytest.raises(ValueError, match="Curator unavailable"):
        queue_jobs.run_job(queue, key)
    assert "completed_snapshot" not in queue.item(key)
    assert queue.payload()["items"][0]["freshness"] != "current"


def test_preparation_timeout_cleans_up_process(queue, repository, monkeypatch):
    import sys
    key = configure_job(queue, repository, monkeypatch)
    queue.config["accounts"][0].update(prepare=[[sys.executable, "-c", "import time; time.sleep(30)"]], prepareTimeoutSeconds=1)
    with pytest.raises(ValueError, match="timed out"):
        queue_jobs.run_job(queue, key)
    assert queue.item(key)["job"]["prepare_pid"] is None
    assert "completed_snapshot" not in queue.item(key)

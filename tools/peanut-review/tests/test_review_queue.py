"""Queue discovery, driver handoffs and revision accounting tests."""
from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import pytest

from peanut_review import gh, review_queue
from peanut_review.models import GitHubAccount
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


def test_service_ownership_and_legacy_job_recovery(queue):
    key = add_item(queue, job={"status": "queued"})
    with pytest.raises(ValueError, match="already serving"):
        review_queue.ReviewQueue(queue.root, queue.config, queue.registry)
    queue.close()
    replacement = review_queue.ReviewQueue(queue.root, queue.config, queue.registry)
    try:
        assert replacement.state["items"][key]["job"]["status"] == "interrupted"
        assert "job" not in replacement.payload()["items"][0]
    finally:
        replacement.close()


def test_removed_account_is_not_exposed(queue):
    add_item(queue, account=OTHER)
    assert queue.payload()["items"] == []


def test_handoff_works_with_incomplete_checkout_configuration(queue):
    queue.config["accounts"][0].pop("reviewConfig")
    add_item(queue)
    item = queue.payload()["items"][0]
    assert '"review_config": null' in item["driver_task"]
    assert "Discover missing configuration" in item["driver_task"]


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


def test_driver_task_contains_account_config_and_exact_context(queue):
    add_item(queue)
    item = queue.payload()["items"][0]
    task = item["driver_task"]
    context = json.loads(task.split("Context (JSON data):\n", 1)[1])
    assert context["github_account"] == asdict(ACCOUNT)
    assert context["pr_url"] == remote()["url"]
    assert context["review_config"] == queue.config["accounts"][0]["reviewConfig"]
    assert context["session_root"] == str(queue.root)
    assert context["session"] is None
    assert context["observed_head"] == remote()["head_sha"]
    assert context["worktree_root"].endswith("worktrees/acme/widget")
    assert "force pushes" in task and "Do not publish" in task
    assert "The requested change" not in task  # PR bodies are not driver instructions.

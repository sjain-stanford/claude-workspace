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
    data["requested_teams"] = [{"id": 101}]
    result = review_queue.fetch_pr("acme/widget", 1)
    assert result["request_kind"] is None
    assert result["requested_team_ids"] == [101]
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
    monkeypatch.setattr(review_queue, "fetch_pr", lambda repo, number: remote(request_kind=None))
    monkeypatch.setattr(gh, "_api", lambda *args, **kwargs: '[{"event":"reviewed","user":{"id":10}}]')
    queue.refresh()
    rows = {r["account"]["login"]: r for r in queue.payload()["items"]}
    assert not rows["alice"]["requested"]
    assert rows["bob"]["requested"]
    assert rows["bob"]["freshness"] == "unknown"
    assert "expired" in rows["bob"]["error"]
    assert len(queue.state["items"]) == 2


def test_direct_origin_survives_submission(queue, monkeypatch):
    monkeypatch.setattr(gh, "account_auth", authenticate)
    monkeypatch.setattr(review_queue, "search_requests", lambda login: [{"html_url": remote()["url"]}])
    monkeypatch.setattr(review_queue, "fetch_pr", lambda repo, number: remote())
    def unexpected_api(*args, **kwargs):
        pytest.fail("A pending direct request should not need a history or team lookup")
    monkeypatch.setattr(gh, "_api", unexpected_api)
    queue.refresh()
    monkeypatch.setattr(gh, "_api", lambda *args, **kwargs: '[{"event":"reviewed","user":{"id":10}}]')
    monkeypatch.setattr(review_queue, "search_requests", lambda login: [])
    monkeypatch.setattr(review_queue, "fetch_pr", lambda repo, number: remote(request_kind=None))
    queue.refresh()
    row = queue.payload()["items"][0]
    assert row["request_kind"] == "direct"
    assert row["requested"] is False
    assert row["request_withdrawn"] is False


@pytest.mark.parametrize("legacy", [False, True])
def test_withdrawal_hides_cached_row_despite_stale_search_and_rerequest_restores_it(queue, monkeypatch, legacy):
    key = add_item(queue, request_kind_verified=True)
    if legacy:
        # Origin-only caches never checked for removal events.
        queue.state["items"][key].update(request_history_updated_at="unchanged", request_history_team_ids=[])
    metadata = remote(request_kind=None, updated_at="unchanged")
    events = [
        {"event": "review_requested", "requested_reviewer": {"id": 10}},
        {"event": "review_request_removed", "requested_reviewer": {"id": 10}},
    ]
    monkeypatch.setattr(gh, "account_auth", authenticate)
    # Search may still return the removed request; the live reviewer list wins.
    monkeypatch.setattr(review_queue, "search_requests", lambda login: [{"html_url": metadata["url"]}])
    monkeypatch.setattr(review_queue, "fetch_pr", lambda *args: metadata.copy())
    monkeypatch.setattr(gh, "_api", lambda *args, **kwargs: json.dumps(events))
    queue.refresh()
    assert queue.payload()["items"] == []
    assert not queue.state["items"][key]["requested"]
    queue.close()
    replacement = review_queue.ReviewQueue(queue.root, queue.config, queue.registry)
    try:
        assert replacement.payload()["items"] == []
        # Live requests restore the row even before search or updated_at catches up.
        monkeypatch.setattr(review_queue, "search_requests", lambda login: [])
        metadata["request_kind"] = "direct"
        replacement.refresh()
        row = replacement.payload()["items"][0]
        assert row["requested"] and row["request_kind"] == "direct"
        # A second removal in the same timestamp must recheck history.
        metadata["request_kind"] = None
        replacement.refresh()
        assert replacement.payload()["items"] == []
    finally:
        replacement.close()


@pytest.mark.parametrize("last_event,withdrawn", [
    ({"event": "review_request_removed", "requested_reviewer": {"id": 10}}, True),
    ({"event": "review_request_removed", "requested_reviewer": {"id": 20, "login": "alice"}}, False),
    ({"event": "reviewed", "user": {"id": 10}}, False),
    ({"event": "review_requested", "requested_reviewer": {"id": 10}}, False),
])
def test_withdrawal_uses_latest_account_activity(monkeypatch, last_event, withdrawn):
    events = [{"event": "review_requested", "requested_reviewer": {"id": 10}}]
    if last_event["event"] != "review_request_removed":
        events.append({"event": "review_request_removed", "requested_reviewer": {"id": 10}})
    events.append(last_event)
    for index, event in enumerate(events):
        event["submitted_at" if event["event"] == "reviewed" else "created_at"] = f"2026-01-01T00:00:0{index}Z"
    monkeypatch.setattr(gh, "_api", lambda *args, **kwargs: json.dumps(list(reversed(events))))
    result = review_queue.request_origin(remote(request_kind=None), {}, ACCOUNT, {})
    assert result["request_withdrawn"] is withdrawn
    assert result["request_kind"] == "direct"
    assert not result["requested"]


@pytest.mark.parametrize("current_teams,member_teams,withdrawn", [
    ([], {101}, True),
    ([], {202}, False),
    ([101], {101}, False),
    ([202], {101}, True),
    ([202], {101, 202}, False),
])
def test_team_withdrawal_only_applies_to_selected_accounts_teams(monkeypatch, current_teams, member_teams, withdrawn):
    events = [{"event": action, "requested_team": {"id": 101}}
              for action in ("review_requested", "review_request_removed")]
    monkeypatch.setattr(gh, "_api", lambda *args, **kwargs: json.dumps(events))
    result = review_queue.request_origin(remote(request_kind=None, requested_team_ids=current_teams),
                                        {}, ACCOUNT, {"ids": member_teams})
    assert result["request_withdrawn"] is withdrawn
    assert result["requested"] is bool(set(current_teams) & member_teams)


def test_current_team_request_keeps_direct_withdrawal_visible(monkeypatch):
    monkeypatch.setattr(gh, "_api", lambda *args, **kwargs: json.dumps([
        {"event": "review_requested", "requested_reviewer": {"id": 10}},
        {"event": "review_request_removed", "requested_reviewer": {"id": 10}},
    ]))
    result = review_queue.request_origin(remote(request_kind=None, requested_team_ids=[101]),
                                        {}, ACCOUNT, {"ids": {101}})
    assert result["requested"] and not result["request_withdrawn"]
    assert result["request_kind"] == "direct"


def test_team_removal_rechecks_history_even_if_updated_at_is_unchanged(monkeypatch):
    events = [{"event": "review_requested", "requested_team": {"id": 101}}]
    monkeypatch.setattr(gh, "_api", lambda *args, **kwargs: json.dumps(events))
    metadata = remote(request_kind=None, requested_team_ids=[101])
    previous = {**metadata, **review_queue.request_origin(metadata, {}, ACCOUNT, {"ids": {101}})}
    events.append({"event": "review_request_removed", "requested_team": {"id": 101}})
    result = review_queue.request_origin({**metadata, "requested_team_ids": []}, previous, ACCOUNT, {"ids": {101}})
    assert result["request_withdrawn"] and not result["requested"]


@pytest.mark.parametrize("withdrawn", [False, True])
def test_failed_history_lookup_preserves_visibility_and_retries(monkeypatch, withdrawn):
    def fail(*args, **kwargs):
        raise RuntimeError("Unavailable")
    monkeypatch.setattr(gh, "_api", fail)
    metadata = remote(request_kind=None)
    previous = {"request_kind": "direct", "request_withdrawn": withdrawn}
    result = review_queue.request_origin(metadata, previous, ACCOUNT, {})
    assert result["request_withdrawn"] is withdrawn
    assert "Unavailable" in result["request_kind_error"]
    monkeypatch.setattr(gh, "_api", lambda *args, **kwargs:
                        '[{"event":"review_request_removed","requested_reviewer":{"id":10}}]')
    result = review_queue.request_origin(metadata, result, ACCOUNT, {})
    assert result["request_withdrawn"] and not result["request_kind_error"]


def test_history_recovers_direct_request_from_paginated_legacy_data(monkeypatch):
    calls = []
    def api(endpoint, **kwargs):
        calls.append((endpoint, kwargs))
        return json.dumps([{"event": "review_requested", "requested_reviewer": {"id": 20, "login": "bob"}}]) + json.dumps([
            {"event": "review_requested", "requested_reviewer": {"id": 10, "login": "ALICE"}},
            {"event": "reviewed"}, {"event": "review_request_removed"},
        ])
    monkeypatch.setattr(gh, "_api", api)
    result = review_queue.request_origin(remote(request_kind=None), {"request_kind": "team", "requested": False}, ACCOUNT, {})
    assert result["request_kind"] == "direct"
    assert result["request_kind_verified"]
    assert calls == [("repos/acme/widget/issues/1/timeline?per_page=100", {"paginate": True})]


def test_team_origin_is_account_scoped_cached_and_retained(monkeypatch):
    calls = []
    def api(endpoint, **kwargs):
        calls.append(endpoint)
        assert kwargs == {"paginate": True}
        if endpoint.startswith("user/teams"):
            return '[{"id": 101}]'
        return json.dumps([{"event": "review_requested", "requested_team": {"id": 101}}])
    monkeypatch.setattr(gh, "_api", api)
    metadata = remote(request_kind=None)
    teams = {}
    first = review_queue.request_origin(metadata, {}, ACCOUNT, teams)
    assert first["request_kind"] == "team"
    again = review_queue.request_origin(metadata, first, ACCOUNT, teams)
    assert again["request_kind"] == "team"
    assert len(calls) == 2
    review_queue.request_origin({**metadata, "number": 2}, {}, ACCOUNT, teams)
    assert calls.count("user/teams?per_page=100") == 1
    other = review_queue.request_origin(metadata, {}, OTHER, {"ids": {202}})
    assert other["request_kind"] is None


def test_unrelated_requests_do_not_turn_following_into_direct_or_team(monkeypatch):
    monkeypatch.setattr(gh, "_api", lambda endpoint, **kwargs: json.dumps([
        {"event": "review_requested", "requested_reviewer": {"id": 20, "login": "alice"}},
        {"event": "review_requested", "requested_team": {"id": 999}},
    ]))
    result = review_queue.request_origin(remote(request_kind=None), {"request_kind": "team"}, ACCOUNT, {"ids": {101}})
    assert result["request_kind"] is None


def test_direct_history_overrides_known_team_despite_membership_failure(monkeypatch):
    def api(endpoint, **kwargs):
        if endpoint.startswith("user/teams"):
            raise RuntimeError("Membership unavailable")
        return json.dumps([
            {"event": "review_requested", "requested_team": {"id": 101}},
            {"event": "review_requested", "requested_reviewer": {"id": 10}},
        ])
    monkeypatch.setattr(gh, "_api", api)
    result = review_queue.request_origin(remote(request_kind=None), {"request_kind": "team", "request_kind_verified": True}, ACCOUNT, {})
    assert result["request_kind"] == "direct"
    assert not result["request_withdrawn"]
    assert "Membership unavailable" in result["request_kind_error"]


def test_history_failure_preserves_known_origin_and_retries(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Temporarily unavailable")
    monkeypatch.setattr(gh, "_api", fail)
    metadata = remote(request_kind=None)
    previous = {"request_kind": "team", "request_kind_verified": True}
    result = review_queue.request_origin(metadata, previous, ACCOUNT, {})
    assert result["request_kind"] == "team"
    assert "Temporarily unavailable" in result["request_kind_error"]
    assert "request_history_updated_at" not in result
    monkeypatch.setattr(gh, "_api", lambda endpoint, **kwargs: '[{"event":"review_requested","requested_reviewer":{"id":10}}]')
    retried = review_queue.request_origin(metadata, result, ACCOUNT, {})
    assert retried["request_kind"] == "direct" and not retried["request_kind_error"]


def test_membership_failure_retries_without_refetching_history(monkeypatch):
    calls = []
    def api(endpoint, **kwargs):
        calls.append(endpoint)
        if endpoint.startswith("user/teams"):
            raise RuntimeError("Membership unavailable")
        return '[{"event":"review_requested","requested_team":{"id":101}}]'
    monkeypatch.setattr(gh, "_api", api)
    metadata = remote(request_kind=None)
    cache = {}
    previous = review_queue.request_origin(metadata, {}, ACCOUNT, cache)
    assert previous["request_kind"] is None
    assert "Membership unavailable" in previous["request_kind_error"]
    review_queue.request_origin({**metadata, "number": 2}, {}, ACCOUNT, cache)
    assert calls.count("user/teams?per_page=100") == 1
    def recovered(endpoint, **kwargs):
        assert endpoint == "user/teams?per_page=100"
        return '[{"id":101}]'
    monkeypatch.setattr(gh, "_api", recovered)
    result = review_queue.request_origin(metadata, previous, ACCOUNT, {})
    assert result["request_kind"] == "team" and not result["request_kind_error"]


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

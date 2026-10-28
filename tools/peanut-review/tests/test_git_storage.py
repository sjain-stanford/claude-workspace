"""Saved reviews survive linked-worktree recycling and Git garbage collection."""

import json
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from peanut_review import launch
from peanut_review import session as sess
from peanut_review.cli import main
from peanut_review.models import AgentConfig, GitHubPR, Session
from peanut_review.web import app, diff


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def review(tmp_path):
    repo = tmp_path / "main"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "source.py").write_text("".join(f"x{i} = {i}\n" for i in range(200)))
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    workspace = tmp_path / "queue" / "pr-1"
    checkout = workspace / "source"
    git(repo, "worktree", "add", "-b", "users/sambhav/review-test", str(checkout), base)
    source = checkout / "source.py"
    source.write_text(source.read_text().replace("x100 = 100", "x100 = 999"))
    git(checkout, "commit", "-am", "reviewed change")
    sd = tmp_path / "reviews" / "saved"
    s, _ = sess.create_session(
        workspace=str(workspace),
        repo_relative="source",
        base_ref=base,
        session_dir=str(sd),
        session_id="saved",
        github=GitHubPR(repo="test/repo", number=1),
    )
    return repo, checkout, sd, s


def remove_and_prune(repo, checkout, *, delete_branch=False):
    branch = git(checkout, "branch", "--show-current")
    git(repo, "worktree", "remove", str(checkout))
    if delete_branch and branch:
        git(repo, "branch", "-D", branch)
    git(repo, "reflog", "expire", "--expire=now", "--all")
    git(repo, "gc", "--prune=now")


def test_saved_review_survives_recycling_and_gc(review):
    repo, checkout, sd, s = review
    assert s.git_common_dir == str(repo / ".git")
    before = diff.parse_diff(sess.review_repo_path(s), s.base_ref, s.topic_ref)
    # Only the retained review refs protect this commit after branch removal.
    remove_and_prune(repo, checkout, delete_branch=True)
    diff.clear_diff_cache()
    loaded = sess.load_session(sd)
    assert sess.repo_path(loaded) == str(checkout)
    assert sess.workspace_head(loaded) is None
    assert (
        diff.parse_diff(sess.review_repo_path(loaded), s.base_ref, s.topic_ref)
        == before
    )
    assert git(repo, "cat-file", "-t", s.current_head) == "commit"


def test_repair_legacy_metadata_preserves_review_identity(review):
    repo, checkout, sd, _ = review
    raw = json.loads((sd / "session.json").read_text())
    raw.pop("git_common_dir")
    (sd / "session.json").write_text(json.dumps(raw))
    git(repo, "worktree", "remove", str(checkout))
    assert main(["--session", str(sd), "retain-git", "--repo", str(repo)]) == 0
    repaired = json.loads((sd / "session.json").read_text())
    assert repaired.pop("git_common_dir") == str(repo / ".git")
    assert repaired == raw
    assert main(["--session", str(sd), "retain-git"]) == 0


def test_repair_missing_commit_leaves_metadata_unchanged(review):
    repo, _, sd, s = review
    s.topic_ref = "f" * 40
    sess.save_session(sd, s)
    before = (sd / "session.json").read_bytes()
    assert main(["--session", str(sd), "retain-git", "--repo", str(repo)]) == 1
    assert (sd / "session.json").read_bytes() == before


def test_sync_retains_previous_and_new_snapshots(review):
    repo, checkout, sd, old = review
    (checkout / "source.py").write_text("new revision\n")
    git(checkout, "commit", "-am", "next revision")
    head = git(checkout, "rev-parse", "HEAD")
    current, changed, _ = sess.sync_session_snapshot(
        sd,
        base_ref=old.base_ref,
        topic_ref=head,
        workspace=str(checkout.parent),
        repo_relative="source",
    )
    assert changed
    remove_and_prune(repo, checkout)
    for oid in (old.base_ref, old.current_head, current.current_head):
        assert git(repo, "cat-file", "-t", oid) == "commit"
    refs = git(
        repo, "for-each-ref", "--format=%(objectname)", "refs/peanut-review/"
    ).splitlines()
    assert set(refs) == {old.base_ref, old.current_head, current.current_head}


def test_legacy_sessions_fall_back_to_execution_repo():
    s = Session(workspace="/workspace", repo_relative="repo")
    assert sess.review_repo_path(s) == "/workspace/repo"


def test_sync_to_replacement_repo_updates_git_storage(review, tmp_path):
    repo, _, sd, old = review
    replacement = tmp_path / "replacement"
    git(repo, "clone", "--no-hardlinks", str(repo), str(replacement))
    git(replacement, "checkout", "--detach", old.current_head)
    current, changed, metadata_changed = sess.sync_session_snapshot(
        sd,
        base_ref=old.base_ref,
        topic_ref=old.current_head,
        workspace=str(replacement),
        repo_relative="",
    )
    assert not changed
    assert metadata_changed
    assert current.git_common_dir == str(replacement / ".git")
    assert sess.repo_path(current) == str(replacement)


def test_retained_git_does_not_allow_launch_in_missing_workspace(review):
    repo, checkout, sd, _ = review
    remove_and_prune(repo, checkout)
    with pytest.raises(ValueError, match="cannot resolve workspace HEAD"):
        launch.launch_agents(str(sd), dry_run=True)


def test_curator_restores_missing_branch_worktree_without_changing_review(review):
    repo, checkout, sd, original = review
    remove_and_prune(repo, checkout)
    before = (sd / "session.json").read_text()
    restored = sess.prepare_curator_workspace(sd)
    assert sess.repo_path(restored) == str(checkout)
    assert restored.workspace == original.workspace
    assert git(checkout, "rev-parse", "HEAD") == original.current_head
    assert git(checkout, "branch", "--show-current") == original.workspace_branch
    assert (sd / "session.json").read_text() == before
    assert sess.prepare_curator_workspace(sd).workspace == restored.workspace
    assert not (sd / "curator-workspaces").exists()


def test_curator_preserves_checkout_at_another_revision(review):
    repo, checkout, sd, original = review
    git(checkout, "checkout", "--detach", original.base_ref)
    (checkout / "notes.txt").write_text("keep local work\n")
    before = (sd / "session.json").read_text()
    with pytest.raises(ValueError, match="synchronize the existing PR worktree"):
        sess.prepare_curator_workspace(sd)
    assert git(checkout, "rev-parse", "HEAD") == original.base_ref
    assert (checkout / "notes.txt").read_text() == "keep local work\n"
    assert (sd / "session.json").read_text() == before


@pytest.mark.parametrize("dirty", [False, True])
def test_curator_reuses_moved_branch_worktree_only_when_clean(review, dirty):
    repo, checkout, sd, original = review
    moved = checkout.parent.parent / "relocated" / checkout.name
    moved.parent.mkdir()
    git(repo, "worktree", "move", str(checkout), str(moved))
    if dirty:
        (moved / "notes.txt").write_text("keep local work\n")
        with pytest.raises(ValueError, match="not clean at the pinned commit"):
            sess.prepare_curator_workspace(sd)
        assert (moved / "notes.txt").read_text() == "keep local work\n"
        assert sess.load_session(sd).workspace == original.workspace
    else:
        restored = sess.prepare_curator_workspace(sd)
        assert sess.repo_path(restored) == str(moved)
        assert restored.current_head == original.current_head
        assert restored.github == original.github
        assert restored.workspace_branch == original.workspace_branch
    assert not checkout.exists()


def test_curator_does_not_reset_branch_after_worktree_removal(review):
    repo, checkout, sd, original = review
    remove_and_prune(repo, checkout)
    git(repo, "branch", "-f", original.workspace_branch, original.base_ref)
    with pytest.raises(ValueError, match="saved branch .* has moved"):
        sess.prepare_curator_workspace(sd)
    assert git(repo, "rev-parse", original.workspace_branch) == original.base_ref
    assert not checkout.exists()


def test_curator_can_recreate_deleted_saved_branch(review):
    repo, checkout, sd, original = review
    remove_and_prune(repo, checkout)
    git(repo, "branch", "-D", original.workspace_branch)
    restored = sess.prepare_curator_workspace(sd)
    assert git(checkout, "branch", "--show-current") == original.workspace_branch
    assert restored.current_head == original.current_head


def test_curator_restore_refuses_live_reviewers(review):
    from peanut_review import runtime

    repo, checkout, sd, s = review
    s.agents = [AgentConfig(name="Busy", model="test", pid=os.getpid())]
    sess.save_session(sd, s)
    runtime.update_agent_meta(sd, "Busy", {"pid": os.getpid()})
    remove_and_prune(repo, checkout)
    with pytest.raises(ValueError, match="agents are live"):
        sess.prepare_curator_workspace(sd)
    assert sess.load_session(sd).workspace == s.workspace


def test_web_curate_restores_recycled_workspace_and_launches_only_curator(review):
    repo, checkout, sd, s = review
    s.agents = [
        AgentConfig(name="Reviewer", model="test", runner="codex"),
        AgentConfig(name="Curator", model="test", runner="codex", role="curator"),
    ]
    sess.save_session(sd, s)
    remove_and_prune(repo, checkout)
    registry = app.SessionRegistry()
    sid = registry.bind(sd)
    server = app.make_server("127.0.0.1", 0, registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/{sid}/api/curator/launch",
            data=b"{}", headers={"Content-Type": "application/json"},
        )
        # Only the model process is stubbed; HTTP, Git recovery, prompts and launch validation run.
        with patch("peanut_review.launch.subprocess", wraps=subprocess) as process_module:
            spawn = process_module.Popen
            spawn.return_value = SimpleNamespace(pid=2147483647)
            with urllib.request.urlopen(request) as response:
                payload = json.load(response)
                assert response.status == 202
            assert [item["name"] for item in payload["results"]] == ["Curator"]
            spawn.assert_called_once()
            restored = sess.load_session(sd)
            assert spawn.call_args.kwargs["cwd"] == restored.workspace
        assert git(sess.repo_path(restored), "rev-parse", "HEAD") == s.current_head
        assert sess.repo_path(restored) in (sd / "prompts/Curator.md").read_text()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("github_backed", [True, False])
def test_web_diff_fold_comments_and_preview_after_recycling(review, github_backed):
    repo, checkout, sd, s = review
    if not github_backed:
        s.github = None
        sess.save_session(sd, s)
    remove_and_prune(repo, checkout)
    registry = app.SessionRegistry()
    sid = registry.bind(sd)
    server = app.make_server("127.0.0.1", 0, registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/{sid}"
    try:
        with urllib.request.urlopen(url + "/") as response:
            assert response.status == 200
            assert b"source.py" in response.read()
        with urllib.request.urlopen(
            url + "/api/diff/fold?file=source.py&start=0&end=5"
        ) as response:
            lines = json.load(response)["lines"]
            assert len(lines) == 5
            assert lines[0]["content"] == "x0 = 0"
        request = urllib.request.Request(
            url + "/api/comments",
            data=json.dumps(
                {
                    "author": "Human",
                    "file": "source.py",
                    "line": 101,
                    "body": "Check this value",
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 201
        if github_backed:
            with urllib.request.urlopen(url + "/api/gh/preview") as response:
                preview = json.load(response)
                assert response.status == 200
                assert "Check this value" in json.dumps(preview)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

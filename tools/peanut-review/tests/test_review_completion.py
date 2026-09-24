"""Completion evidence survives CLI rounds and never certifies unreviewed revisions."""
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from peanut_review import cli, launch, review_completion as completion, review_queue, session as sess
from peanut_review.models import GitHubAccount, GitHubPR
from peanut_review.supervisor import supervise_agent
from peanut_review.web.app import SessionRegistry


@pytest.fixture
def review(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (repo / "file").write_text("base\n")
    git("add", "file")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    (repo / "file").write_text("change\n")
    git("commit", "-am", "change")
    head = git("rev-parse", "HEAD")
    directory = tmp_path / "sessions" / "widget-pr-1-test"
    pr = GitHubPR(repo="acme/widget", number=1, url="https://github.com/acme/widget/pull/1",
                  account=GitHubAccount("github.com", "alice", 10), head_sha=head,
                  base_sha=base, base_ref_name="main")
    session, _ = sess.create_session(
        workspace=str(repo), base_ref=base, topic_ref=head, github=pr,
        session_id=directory.name, session_dir=str(directory), agents=[
            {"name": "Vera", "runner": "codex", "model": "test", "persona": "vera.md"},
            {"name": "Irene", "runner": "codex", "model": "test", "persona": "irene.md"},
            {"name": "Curator", "runner": "codex", "model": "test", "role": "curator"},
        ])
    return directory, session, git


def finish(directory, ids, successful=True):
    for name, run_id in ids.items():
        completion.finish_run(directory, name, run_id, successful=successful)


def complete_round(directory, session):
    finish(directory, completion.begin_launch(directory, session, sess.reviewer_agents(session)))
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)))


def test_completion_requires_all_reviewers_and_curator_for_same_runs(review):
    directory, session, git = review
    ids = completion.begin_launch(directory, session, sess.reviewer_agents(session))
    finish(directory, {"Vera": ids["Vera"]})
    assert completion.completed_review(directory, session) is None
    # Curating before the other reviewer reports cannot certify the full round.
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)))
    finish(directory, {"Irene": ids["Irene"]})
    assert completion.completed_review(directory, session) is None
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)))
    assert completion.completed_review(directory, session)["snapshot"] == completion.snapshot(session)


def test_failed_reviewer_or_curator_never_completes_round(review):
    directory, session, git = review
    ids = completion.begin_launch(directory, session, sess.reviewer_agents(session))
    finish(directory, {"Vera": ids["Vera"]})
    finish(directory, {"Irene": ids["Irene"]}, successful=False)
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)))
    assert completion.completed_review(directory, session) is None
    finish(directory, completion.begin_launch(directory, session, [session.agents[1]]))
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)), successful=False)
    assert completion.completed_review(directory, session) is None


def test_sync_and_partial_rerun_cannot_certify_new_snapshot(review):
    directory, session, git = review
    complete_round(directory, session)
    original = completion.completed_review(directory, session)
    (Path(session.workspace) / "file").write_text("new revision\n")
    git("commit", "-am", "updated PR")
    head = git("rev-parse", "HEAD")
    session, _, _ = sess.sync_session_snapshot(directory, base_ref=session.base_ref,
        topic_ref=head, github=replace(session.github, head_sha=head))
    assert completion.completed_review(directory, session) == original
    finish(directory, completion.begin_launch(directory, session, [session.agents[0]]))
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)))
    assert completion.completed_review(directory, session) == original
    # Rerunning the remaining reviewer invalidates the premature curator.
    finish(directory, completion.begin_launch(directory, session, [session.agents[1]]))
    assert completion.completed_review(directory, session) == original
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)))
    assert completion.completed_review(directory, session)["snapshot"]["head_sha"] == head


def test_late_completion_cannot_finish_replacement_launch(review):
    directory, session, git = review
    old = completion.begin_launch(directory, session, sess.reviewer_agents(session))
    completion.begin_launch(directory, session, sess.reviewer_agents(session))
    finish(directory, old)
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)))
    assert completion.completed_review(directory, session) is None


@pytest.mark.parametrize("change", ["head", "sync", "dirty"])
def test_checkout_or_session_changes_during_round_do_not_certify_it(review, change):
    directory, session, git = review
    finish(directory, completion.begin_launch(directory, session, sess.reviewer_agents(session)))
    ids = completion.begin_launch(directory, session, sess.curator_agents(session))
    (Path(session.workspace) / "file").write_text("changed during review\n")
    if change != "dirty":
        git("commit", "-am", "changed during review")
    if change == "sync":
        head = git("rev-parse", "HEAD")
        session, _, _ = sess.sync_session_snapshot(directory, base_ref=session.base_ref,
            topic_ref=head, github=replace(session.github, head_sha=head))
    finish(directory, ids)
    assert completion.completed_review(directory, session) is None


def test_dirty_launch_cannot_be_certified_by_later_cleanup(review):
    directory, session, git = review
    path = Path(session.workspace) / "file"
    original = path.read_text()
    path.write_text("uncommitted change\n")
    ids = completion.begin_launch(directory, session, sess.reviewer_agents(session))
    path.write_text(original)
    finish(directory, ids)
    finish(directory, completion.begin_launch(directory, session, sess.curator_agents(session)))
    assert completion.completed_review(directory, session) is None


@pytest.mark.parametrize("signal,exit_code", [(False, 0), (True, 1), (True, 0)])
def test_supervisor_records_only_successful_current_signals(review, signal, exit_code):
    directory, session, git = review
    reviewer_ids = completion.begin_launch(directory, session, sess.reviewer_agents(session))
    finish(directory, reviewer_ids)
    # Stale signals must not count as completion of a newly launched curator.
    path = directory / "signals" / "Curator.round-done"
    path.write_text("previous round")
    ids = completion.begin_launch(directory, session, sess.curator_agents(session))
    script = f"from pathlib import Path; import sys; p=Path({str(path)!r}); "
    script += ("p.write_text('finished'); " if signal else "") + f"sys.exit({exit_code})"
    env = {**os.environ, "PEANUT_REVIEW_RUN_ID": ids["Curator"]}
    supervise_agent(session_dir=directory, agent_name="Curator", timeout=5,
                    command=[sys.executable, "-c", script], env=env)
    assert bool(completion.completed_review(directory, session)) == (signal and exit_code == 0)


def test_cli_launch_and_wait_all_record_completion_without_queue_worker(review, monkeypatch, tmp_path):
    directory, session, git = review
    wrapper = tmp_path / "fake-runner"
    wrapper.write_text("#!/usr/bin/env python3\nimport os, sys\nfrom pathlib import Path\n"
        "name=sys.argv[sys.argv.index('--name')+1]\n"
        "(Path(os.environ['PEANUT_SESSION'])/'signals'/f'{name}.round-done').write_text('done')\n")
    wrapper.chmod(0o755)
    monkeypatch.setattr(launch, "_find_launcher_script", lambda runner: str(wrapper))
    monkeypatch.setattr(launch, "validate_launch_prerequisites", lambda **kwargs: None)
    monkeypatch.setenv("PYTHONPATH", str(Path(review_queue.__file__).parent.parent))
    assert cli.main(["--session", str(directory), "launch"]) == 0
    assert cli.main(["--session", str(directory), "wait-all", "round-done", "--timeout", "5", "--poll", "0.01"]) == 0
    # wait-all observes signals; supervisors persist evidence as wrappers exit.
    deadline = time.monotonic() + 5
    while completion.completed_review(directory, session) is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert completion.completed_review(directory, session)["snapshot"] == completion.snapshot(session)


def test_queue_discovers_cli_session_and_tracks_completed_revision(review, monkeypatch):
    directory, session, git = review
    registry = SessionRegistry([directory.parent])
    account = session.github.account
    cfg = {"pollSeconds": 120, "accounts": [{"hostname": account.hostname, "login": account.login,
        "label": "Work", "reviewConfig": "/example/review.json", "repositories": {}}]}
    q = review_queue.ReviewQueue(directory.parent, cfg, registry)
    try:
        q.state["accounts"]["github.com/alice"] = {"identity": asdict(account)}
        q.payload()  # Local discovery includes the session without a GitHub request.
        key = review_queue.identity_key(account, session.github.repo, 1)
        q.state["items"][key].update(completion.snapshot(session), state="open", checked_at=review_queue.now(),
            job={"status": "failed", "error": "Old checkout divergence"})
        row = q.payload()["items"][0]
        assert row["freshness"] == "unreviewed"
        assert "job" not in row
        context = json.loads(row["driver_task"].split("Context (JSON data):\n")[1])
        assert context["session"] == str(directory)
        assert context["workspace"] == session.workspace
        assert "Refresh and re-review" in row["driver_task"]
        complete_round(directory, session)
        assert q.payload()["items"][0]["freshness"] == "current"
        q.state["items"][key]["head_sha"] = "f" * 40
        assert q.payload()["items"][0]["freshness"] == "stale"
        q.state["items"][key].update(completion.snapshot(session), base_ref="release")
        assert q.payload()["items"][0]["freshness"] == "stale"
        q.state["items"][key].update(completion.snapshot(session), base_sha="f" * 40)
        assert q.payload()["items"][0]["freshness"] == "stale"
        monkeypatch.setattr(review_queue.gh, "_api", lambda *args, **kwargs:
                            '[{"event":"review_request_removed","requested_reviewer":{"id":10}}]')
        item = q.state["items"][key]
        item.update(review_queue.request_origin(
            {**item, "request_kind": None, "updated_at": review_queue.now()}, item, account, {}))
        assert q.payload()["items"] == []  # Rediscovering sessions must not undo withdrawal.
        assert registry.get(session.id) == directory
        assert completion.completed_review(directory, sess.load_session(directory)) is not None
        q._save()
        q.close()
        q = review_queue.ReviewQueue(directory.parent, cfg, registry)
        assert q.payload()["items"] == []
        assert q.state["items"][key]["session_id"] == session.id
        q.state["items"][key].update(review_queue.request_origin({"request_kind": "direct"}, item, account, {}))
        assert q.payload()["items"][0]["session_id"] == session.id
    finally:
        q.close()


@pytest.mark.parametrize("other_completed", [False, True])
@pytest.mark.parametrize("remote_base,expected", [("main", "current"), ("release", "stale")])
def test_queue_uses_latest_completion_across_sessions(review, other_completed, remote_base, expected):
    directory, session, git = review
    other_directory = directory.parent / "widget-pr-1-other"
    other, _ = sess.create_session(
        workspace=session.workspace, base_ref=session.base_ref, topic_ref=session.current_head,
        github=replace(session.github, base_ref_name="older-base" if other_completed else "main"),
        session_id=other_directory.name, session_dir=str(other_directory),
        agents=[agent.to_dict() for agent in session.agents])
    if other_completed:
        complete_round(other_directory, other)
    complete_round(directory, session)
    receipt = completion.completed_review(directory, session)
    # Session activity selects the link, not the most recent completed round.
    future = time.time_ns() + 1_000_000_000
    os.utime(other_directory / "session.json", ns=(future, future))

    registry = SessionRegistry([directory.parent])
    account = session.github.account
    cfg = {"pollSeconds": 120, "accounts": [{"hostname": account.hostname, "login": account.login,
        "label": "Work", "repositories": {}}]}
    q = review_queue.ReviewQueue(directory.parent, cfg, registry)
    try:
        q.state["accounts"]["github.com/alice"] = {"identity": asdict(account)}
        key = review_queue.identity_key(account, session.github.repo, 1)
        q.state["items"][key] = {
            "key": key, "account": asdict(account), "repo": session.github.repo, "number": 1,
            **completion.snapshot(session), "base_ref": remote_base,
            "state": "open", "checked_at": review_queue.now(),
        }
        # Both sessions predate the first poll, so no queue cache can mask the bug.
        row = q.payload()["items"][0]
        assert row["session_id"] == other.id
        assert row["completed_snapshot"] == receipt["snapshot"]
        assert row["completed_at"] == receipt["completed_at"]
        assert row["freshness"] == expected
        context = json.loads(row["driver_task"].split("Context (JSON data):\n")[1])
        assert context["session"] == str(other_directory)
    finally:
        q.close()


def test_completion_is_bound_to_account_and_pr(review):
    directory, session, git = review
    complete_round(directory, session)
    session.github = replace(session.github, account=GitHubAccount("github.com", "bob", 20))
    assert completion.completed_review(directory, session) is None

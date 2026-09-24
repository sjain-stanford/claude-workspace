"""Session-local evidence of completed reviewer and curator runs.

Launch IDs bind completion to a pinned revision, independently of queue jobs.
Signals from older rounds and a subsequent sync cannot certify a new snapshot.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path

from . import session as sess
from .models import _now_iso


def target(session) -> dict | None:
    pr = session.github
    if not pr or not pr.account:
        return None
    return {"account": asdict(pr.account), "repo": pr.repo.casefold(), "number": pr.number}


def snapshot(session) -> dict:
    return {"head_sha": session.current_head, "base_sha": session.base_ref,
            "base_ref": session.github.base_ref_name}


def _read(directory: Path) -> dict:
    try:
        data = json.loads((directory / "review-completion.json").read_text())
        return data if isinstance(data, dict) and data.get("version") == 1 else {}
    except (OSError, ValueError):
        return {}


def _save(directory: Path, data: dict) -> None:
    # Callers hold the session lock, including across concurrent supervisors.
    tmp = directory / "review-completion.json.tmp"
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(directory / "review-completion.json")


def _signal_time(directory: Path, name: str) -> int | None:
    try:
        return (directory / "signals" / f"{name}.round-done").stat().st_mtime_ns
    except FileNotFoundError:
        return None


def _workspace_matches(session) -> bool:
    if sess.workspace_head(session) != session.current_head:
        return False
    try:
        return not sess._run_git(sess.repo_path(session), "status", "--porcelain", "--untracked-files=no")
    except RuntimeError:
        return False


def begin_launch(directory, session, agents) -> dict[str, str]:
    """Register all selected runs before any supervisor can finish."""
    directory = Path(directory)
    if target(session) is None:
        return {}
    with sess._session_lock(directory):
        latest = sess.load_session(directory)
        if target(latest) != target(session) or snapshot(latest) != snapshot(session):
            raise ValueError("Session changed before launch; retry at the intended snapshot")
        data = _read(directory)
        data.setdefault("version", 1)
        runs = data.setdefault("runs", {})
        reviewers = sess.reviewer_agents(session)
        curators = sess.curator_agents(session)
        if any(a in reviewers for a in agents):
            # A curator from before this reviewer run cannot cover its findings.
            for agent in curators:
                runs.pop(agent.name, None)
        ids = {}
        workspace_matches = _workspace_matches(session)
        for agent in agents:
            ids[agent.name] = uuid.uuid4().hex
            runs[agent.name] = {"id": ids[agent.name], "target": target(session),
                                "snapshot": snapshot(session), "started_at": _now_iso(),
                                "workspace_matches": workspace_matches,
                                "initial_signal": _signal_time(directory, agent.name)}
        for agent in agents:
            if agent in curators:
                runs[agent.name]["reviewer_runs"] = {
                    a.name: runs.get(a.name, {}).get("id") for a in reviewers
                    if runs.get(a.name, {}).get("successful") or (
                        _signal_time(directory, a.name) is not None
                        and _signal_time(directory, a.name) != runs.get(a.name, {}).get("initial_signal"))
                }
        _save(directory, data)
        return ids


def finish_run(directory, agent_name: str, run_id: str | None, *, successful: bool) -> None:
    """Record a supervisor's result and certify only a complete, matching round."""
    if not run_id:
        return
    directory = Path(directory)
    with sess._session_lock(directory):
        session = sess.load_session(directory)
        data = _read(directory)
        runs = data.get("runs", {})
        run = runs.get(agent_name, {})
        if run.get("id") != run_id:
            return  # A late exit from a replaced launch must not finish its successor.
        run["finished_at"] = _now_iso()
        run["successful"] = successful and run.get("workspace_matches", False)
        reviewers = sess.reviewer_agents(session)
        curators = sess.curator_agents(session)
        expected_target = target(session)
        expected_snapshot = snapshot(session) if expected_target else None
        complete = bool(reviewers) and len(curators) == 1 and expected_target is not None
        if complete:
            curator_run = runs.get(curators[0].name, {})
            complete = all(
                runs.get(a.name, {}).get("successful") is True
                and runs[a.name].get("snapshot") == expected_snapshot
                and runs[a.name].get("target") == expected_target
                for a in [*reviewers, *curators]
            ) and curator_run.get("reviewer_runs") == {
                a.name: runs.get(a.name, {}).get("id") for a in reviewers
            }
        if complete and _workspace_matches(session):
            data["completed"] = {"target": expected_target, "snapshot": expected_snapshot,
                                 "completed_at": _now_iso()}
        _save(directory, data)


def completed_review(directory, session) -> dict | None:
    completed = _read(Path(directory)).get("completed")
    if isinstance(completed, dict) and completed.get("target") == target(session):
        return completed
    return None

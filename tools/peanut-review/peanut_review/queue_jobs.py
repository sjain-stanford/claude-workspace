"""Checkout preparation and review lifecycle for explicit dashboard actions."""
from __future__ import annotations

import fcntl
import json
import shutil
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from . import curator, gh, gh_pull, launch, runtime, session as sess, store, validation
from .models import AgentConfig, GitHubAccount, GitHubPR
from .review_queue import now, snapshot


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                            text=True, timeout=120)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git operation failed")
    return result.stdout.strip()


def worktrees(repository: Path) -> list[dict]:
    result = []
    for record in git(repository, "worktree", "list", "--porcelain", "-z").split("\0\0"):
        fields = {}
        for line in record.split("\0"):
            key, _, value = line.partition(" ")
            if key:
                fields[key] = value
        if fields:
            result.append(fields)
    return result


def require_clean(path: Path) -> None:
    if git(path, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError(f"Worktree has local changes: {path}. Commit or move them before refreshing.")


def require_idle(directory: Path) -> None:
    session = sess.load_session(directory)
    for agent in session.agents:
        state = runtime.inspect_agent_runtime(directory, agent)
        if state["reviewer_live"] or state["supervisor_live"]:
            raise ValueError(f"Review agents are still using {session.workspace}; wait for them to finish or stop them in the session")


def prepare_worktree(queue, item: dict, settings: dict, remote: dict, existing: Path | None) -> Path:
    repository = Path(settings["path"]).resolve()
    root = Path(settings["worktreeRoot"]).resolve()
    url = f'https://{item["account"]["hostname"]}/{item["repo"]}.git'
    if not repository.exists():
        repository.parent.mkdir(parents=True, exist_ok=True)
        gh.git_read(["clone", "--no-checkout", "--", url, str(repository)])
    git(repository, "rev-parse", "--git-common-dir")
    # Never use origin for credentials or target selection. PR heads (including
    # fork heads) are exposed by the base repository's pull refs.
    gh.git_read(["fetch", "--no-tags", "--", url,
                 f'refs/pull/{item["number"]}/head', remote["base_sha"]], cwd=repository)
    for sha in (remote["head_sha"], remote["base_sha"]):
        if git(repository, "rev-parse", "--verify", f"{sha}^{{commit}}") != sha:
            raise ValueError("PR changed during fetch; refresh and retry")
    registered = worktrees(repository)
    by_path = {Path(entry["worktree"]).resolve(): entry for entry in registered}
    slug = re_slug(remote["head_ref"] or remote["title"])[:60]
    leaf = f'pr-{item["number"]}-{slug}-{item["key"][:8]}'
    branch = f"users/sambhav/review-{leaf}"
    chosen = None
    if existing:
        chosen = Path(sess.repo_path(sess.load_session(existing))).resolve()
        if chosen not in by_path or not chosen.is_relative_to(root):
            raise ValueError("The session checkout is outside the configured worktree root; configure its existing task worktree before refreshing")
    else:
        branch_ref = f'refs/heads/{remote["head_ref"]}'
        matches = [path for path, entry in by_path.items()
                   if path != repository and path.is_relative_to(root) and entry.get("branch") == branch_ref]
        if len(matches) == 1:
            chosen = matches[0]
        elif root / leaf in by_path and by_path[root / leaf].get("branch") == f"refs/heads/{branch}":
            # Resume a failed setup that created its worktree before a session.
            chosen = root / leaf
    if chosen:
        if chosen == repository:
            raise ValueError("The canonical checkout cannot be used as a review worktree")
        if not by_path[chosen].get("branch"):
            raise ValueError("Review requires a branch-backed task worktree")
        for summary in queue.registry.list_sessions():
            directory = queue.registry.get(summary["id"])
            session = sess.load_session(directory)
            if Path(sess.repo_path(session)).resolve() == chosen:
                require_idle(directory)
        require_clean(chosen)
        head = git(chosen, "rev-parse", "HEAD")
        if head != remote["head_sha"]:
            result = subprocess.run(["git", "-C", str(chosen), "merge-base", "--is-ancestor", head, remote["head_sha"]], capture_output=True)
            if result.returncode:
                raise ValueError(f"Worktree branch diverged at {chosen}; reconcile it with the PR before refreshing. Local commits were preserved.")
            git(chosen, "merge", "--ff-only", remote["head_sha"])
        return chosen
    chosen = root / leaf
    if chosen in by_path:
        raise ValueError(f"Existing worktree needs attention: {chosen}")
    if chosen.exists():
        raise ValueError(f"Worktree destination already exists: {chosen}")
    root.mkdir(parents=True, exist_ok=True)
    git(repository, "worktree", "add", "-b", branch, str(chosen), remote["head_sha"])
    return chosen


def re_slug(value: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower() or "review"


@contextmanager
def repository_lock(queue, repository: Path):
    # Keep the same lock before and after cloning. A second server may have a
    # different session root but must still serialize work on this checkout.
    repository = repository.resolve()
    repository.parent.mkdir(parents=True, exist_ok=True)
    path = repository.parent / ("." + repository.name + ".peanut-queue.lock")
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another review queue job is using this repository; retry after it finishes") from None
        yield


def review_config(settings: dict, workspace: Path, root: Path) -> dict:
    path = Path(settings["reviewConfig"])
    raw = json.loads(path.read_text())
    # Never chdir or change PWD in a multithreaded web server. The queue supplies
    # its selected worktree and session root explicitly, preserving the lineup.
    raw.update(workspaceRoot=str(workspace), repoRelative=".", reviewRoot=str(root))
    cfg = validation.validate_project_config(
        raw, config_path=path,
        default_personas_dir=Path(__file__).parent / "personas",
    )
    agents = [AgentConfig.from_dict(agent) for agent in cfg["agents"]]
    curator.ensure_curator_agent(agents)
    if len(curator.curators(agents)) != 1:
        raise ValueError("Queue reviews require exactly one configured curator")
    if not curator.reviewers(agents):
        raise ValueError("Configure at least one review agent")
    return cfg


def archive_round(directory: Path, job_id: str) -> None:
    destination = directory / "rounds" / job_id
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("session.json", "result.json", "comments", "notes", "signals", "prompts", "log"):
        source = directory / name
        if source.is_dir():
            shutil.copytree(source, destination / name)
        elif source.is_file():
            shutil.copy2(source, destination / name)
    # A verdict from the prior snapshot must not be publishable as this round.
    (directory / "result.json").unlink(missing_ok=True)


def wait_agents(queue, directory: Path, names: list[str], timeout: int) -> None:
    deadline = time.monotonic() + timeout + 30
    grace = time.monotonic() + 15
    while time.monotonic() < deadline:
        if queue.stopping.is_set():
            raise ValueError("Server stopped monitoring this review; inspect the session before retrying")
        session = sess.load_session(directory)
        agents = [agent for agent in session.agents if agent.name in names]
        if len(agents) != len(names):
            raise ValueError("Review lineup changed during the job")
        states = [runtime.inspect_agent_runtime(directory, agent) for agent in agents]
        if all(state["signal"] and not state["reviewer_live"] and not state["supervisor_live"] for state in states):
            sess.refresh_agent_statuses(directory, session)
            return
        for agent, state in zip(agents, states):
            if time.monotonic() > grace and not state["signal"] and state["process_state"] in {"failed", "timeout", "killed", "exited", "stopped"}:
                raise ValueError(f"{agent.name} stopped before completing the review; inspect its session log")
        queue.stopping.wait(1)
    raise ValueError("Timed out waiting for reviewers; inspect the session before retrying")


def run_preparation(queue, key: str, directory: Path, workspace: Path,
                    command: list[str], timeout: int) -> None:
    if queue.stopping.is_set():
        raise ValueError("Server stopped during preparation")
    with (directory / "log" / "queue-prepare.log").open("ab") as output:
        process = subprocess.Popen(command, cwd=workspace, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        queue.update_job(key, prepare_pid=process.pid)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if queue.stopping.is_set() or time.monotonic() > deadline:
                    raise ValueError("Preparation stopped or timed out; see log/queue-prepare.log")
                queue.stopping.wait(0.25)
            if process.returncode:
                raise ValueError("Preparation failed; see log/queue-prepare.log in the session")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            queue.update_job(key, prepare_pid=None)


def run_job(queue, key: str) -> None:
    item = queue.item(key)
    settings = queue.repository_config(item)
    existing = queue.registry.get(item["session_id"]) if item.get("session_id") else None
    if existing:
        require_idle(existing)
        lineup = sess.load_session(existing).agents
        if len(curator.curators(lineup)) != 1 or not curator.reviewers(lineup):
            raise ValueError("Session must have reviewers and exactly one curator")
    if not existing:
        review_config(settings, queue.root, queue.root)  # Validate before clone/worktree mutations.
    account = GitHubAccount(**item["account"])
    with repository_lock(queue, Path(settings["path"])):
        from .review_queue import fetch_pr
        with gh.account_auth(account.hostname, account.login, expected=account):
            remote = fetch_pr(item["repo"], item["number"])
            if remote["state"] != "open":
                raise ValueError("PR is no longer open")
            with queue.lock:
                queue.state["items"][key].update(remote)
                queue._save()
            workspace = prepare_worktree(queue, item, settings, remote, existing)
        if queue.stopping.is_set():
            raise ValueError("Server stopped before reviewer launch")
        cfg = review_config(settings, workspace, queue.root) if not existing else None
        pr = GitHubPR(repo=item["repo"], number=item["number"], url=remote["url"],
                      title=remote["title"], body=remote["body"], hostname=account.hostname,
                      account=account, head_sha=remote["head_sha"], base_sha=remote["base_sha"],
                      head_ref_name=remote["head_ref"])
        if existing:
            directory = existing
            session = sess.load_session(directory)
            if not session.github or gh.publish_identity(session.github) != gh.publish_identity(pr):
                raise ValueError("Session account or PR target changed")
            require_idle(directory)
            archive_round(directory, item["job"]["id"])
            changed = session.current_head != remote["head_sha"] or session.base_ref != remote["base_sha"]
            session, _, _ = sess.sync_session_snapshot(directory, base_ref=remote["base_sha"], topic_ref=remote["head_sha"], github=pr)
            if changed:
                store.mark_stale(directory)
        else:
            session_id = f'{re_slug(item["repo"].split("/")[-1])}-pr-{item["number"]}-{re_slug(remote["head_ref"])[:50]}-{key[:8]}'
            directory = queue.root / session_id
            if directory.exists():
                raise ValueError("Session directory already exists; rescan the queue before retrying")
            session, _ = sess.create_session(
                workspace=str(workspace), base_ref=remote["base_sha"], topic_ref=remote["head_sha"],
                agents=cfg["agents"], ssh_targets=cfg.get("sshTargets"), personas_dir=cfg.get("personasDir"),
                timeout=cfg["reviewAgentTimeoutSeconds"], session_dir=str(directory), session_id=session_id,
                github=pr, include_curator=True,
            )
        queue.registry.bind(directory)
        with queue.lock:
            queue.state["items"][key]["session_id"] = session.id
            queue.state["items"][key]["job"].update(snapshot=snapshot(remote), workspace=str(workspace))
            queue._save()
        # Only locally configured literal argv commands are executed; PR text
        # cannot supply commands, paths or shell expansions.
        for command in settings.get("prepare", []):
            run_preparation(queue, key, directory, workspace, command,
                            settings.get("prepareTimeoutSeconds", 1800))
        require_clean(workspace)
        if git(workspace, "rev-parse", "HEAD") != remote["head_sha"]:
            raise ValueError("Worktree moved during preparation; retry at the intended PR revision")
        gh_pull.pull_comments(directory, session)
        if queue.stopping.is_set():
            raise ValueError("Server stopped before reviewer launch")
        queue.update_job(key, status="reviewing")
        if existing:
            launch.rerun_agents(directory, agent_names=[a.name for a in sess.reviewer_agents(session)])
        else:
            launch.launch_agents(directory)
        wait_agents(queue, directory, [a.name for a in sess.reviewer_agents(session)], session.timeout)
        queue.update_job(key, status="curating")
        curators = curator.curators(session.agents)
        if len(curators) != 1:
            raise ValueError("Queue reviews require exactly one configured curator")
        launch.launch_curator(directory)
        wait_agents(queue, directory, [curators[0].name], session.timeout)
        final = sess.load_session(directory)
        require_clean(workspace)
        if (final.current_head, final.base_ref, git(workspace, "rev-parse", "HEAD")) != (
            remote["head_sha"], remote["base_sha"], remote["head_sha"],
        ):
            raise ValueError("Review snapshot changed while reviewers were running")
        with queue.lock:
            current = queue.state["items"][key]
            current["completed_snapshot"] = snapshot(remote)
            current["completed_at"] = now()
            current["job"].update(status="done", finished_at=now(), error="")
            queue._save()
        queue.refresh_async()

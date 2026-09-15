"""Optional workspace context reaches local launches without worktree mutations."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from peanut_review import launch, review_context
from peanut_review.session import create_session


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def context_workspace(tmp_path):
    root = tmp_path / "workspace with spaces"
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "-q", "--allow-empty", "-m", "base")
    source = root / "LOCAL_CONTEXT.md"
    source.write_text("Private routing instructions stay in this file.\n")
    return root, repo, source


def test_linked_worktree_inherits_original_path_without_mutation(context_workspace):
    root, repo, source = context_workspace
    worktree = root / "worktrees" / "review"
    git(repo, "worktree", "add", "-q", "-b", "review", str(worktree), "HEAD")
    exclude = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    before = exclude.read_bytes()
    context = review_context.discover(worktree)
    assert context.root == root
    assert context.source == source
    assert str(source) in context.prompt()
    assert "Private routing instructions" not in context.prompt()
    assert not (worktree / ".review-context").exists()
    assert git(worktree, "status", "--porcelain") == ""
    assert exclude.read_bytes() == before


def test_context_is_discovered_directly_without_a_setting(context_workspace, monkeypatch):
    root, repo, source = context_workspace
    assert review_context.discover(root).source == source
    assert review_context.discover(repo).source == source
    monkeypatch.chdir(root)
    assert review_context.discover("repo").source == source


def test_symlink_context_preserves_original_location(context_workspace):
    root, repo, source = context_workspace
    original = root / "references" / "context.md"
    original.parent.mkdir()
    source.rename(original)
    source.symlink_to(original)
    context = review_context.discover(repo)
    assert context.root == root
    assert context.source == original


@pytest.mark.parametrize("kind", ["empty", "unreadable"])
def test_nearest_file_can_disable_inherited_context(context_workspace, monkeypatch, kind):
    _, repo, _ = context_workspace
    local = repo / "LOCAL_CONTEXT.md"
    local.write_text("Local instructions override the parent context.\n")
    context = review_context.discover(repo)
    assert context.root == repo
    assert context.source == local
    if kind == "empty":
        local.write_text("")
    else:
        original_open = Path.open

        def denied_open(path, *args, **kwargs):
            if path == local:
                raise PermissionError("test access denied")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", denied_open)
    assert review_context.discover(repo) is None


@pytest.mark.parametrize("kind", ["empty", "missing", "directory", "fifo", "broken_link", "symlink_loop", "unreadable_file"])
def test_unavailable_context_does_not_block_rendering(context_workspace, tmp_path, monkeypatch, kind):
    root, repo, source = context_workspace
    if kind == "empty":
        source.write_text("")
    elif kind in ("missing", "directory", "fifo", "broken_link", "symlink_loop"):
        source.unlink()
        if kind == "directory":
            source.mkdir()
        elif kind == "fifo":
            os.mkfifo(source)
        elif kind == "broken_link":
            source.symlink_to(root / "missing.md")
        elif kind == "symlink_loop":
            source.symlink_to(source)
    else:
        original_open = Path.open

        def denied_open(path, *args, **kwargs):
            if path == source:
                raise PermissionError("test access denied")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", denied_open)
    assert review_context.discover(repo) is None
    session_dir = tmp_path / "session"
    create_session(
        workspace=str(repo), base_ref="HEAD", session_dir=str(session_dir),
        agents=[
            {"name": "Vera", "persona": "vera.md", "model": "test", "runner": "codex"},
            {"name": "Curator", "role": "curator", "model": "test", "runner": "codex"},
        ],
    )
    prompts = launch.render_all_prompts(session_dir, agent_names=["Vera", "Curator"])
    assert set(prompts) == {"Vera", "Curator"}
    for prompt in prompts.values():
        assert "# Optional local context" not in prompt.read_text()


def test_rendered_read_command_quotes_path_and_tolerates_disappearance(tmp_path):
    source = tmp_path / "space ' $(touch SENTINEL) `touch SENTINEL`.md"
    source.write_text("only this content\n")
    prompt = review_context.ReviewContext(tmp_path, source).prompt()
    command = prompt.split("```sh\n", 1)[1].split("\n```", 1)[0]
    result = subprocess.run(["sh", "-c", command], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == source.read_text()
    assert not (tmp_path / "SENTINEL").exists()
    source.unlink()
    result = subprocess.run(["sh", "-c", command], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == ""


def test_reviewers_reruns_and_curator_receive_current_pointer_before_spawn(context_workspace, tmp_path, monkeypatch):
    _, repo, source = context_workspace
    session_dir = tmp_path / "session"
    create_session(
        workspace=str(repo), base_ref="HEAD", session_dir=str(session_dir),
        agents=[
            {"name": "Vera", "persona": "vera.md", "model": "test", "runner": "codex"},
            {"name": "Curator", "role": "curator", "model": "test", "runner": "codex"},
        ],
    )
    launches = []

    def fake_popen(cmd, **kwargs):
        assert kwargs["cwd"] == str(repo)
        assert not (repo / ".review-context").exists()
        name = cmd[cmd.index("--agent") + 1]
        prompt = (session_dir / "prompts" / f"{name}.md").read_text()
        assert ("# Optional local context" in prompt) == source.exists()
        if source.exists():
            assert str(source) in prompt
        assert "Private routing instructions" not in prompt
        launches.append(name)
        return SimpleNamespace(pid=999999999)

    monkeypatch.setattr(launch, "subprocess", SimpleNamespace(
        Popen=fake_popen, STDOUT=subprocess.STDOUT,
    ))
    launch.launch_agents(session_dir, dry_run=True)
    assert not launches
    launch.launch_agents(session_dir)
    custom = tmp_path / "custom.md"
    custom.write_text("Custom instructions for ${AGENT}.\n")
    launch.rerun_agents(session_dir, agent_names=["Vera"], template_path=custom)
    assert "Custom instructions for Vera." in (session_dir / "prompts" / "Vera.md").read_text()
    launch.launch_curator(session_dir, template_path=custom)
    assert "Custom instructions for Curator." in (session_dir / "prompts" / "Curator.md").read_text()
    source.unlink()
    launch.rerun_agents(session_dir, agent_names=["Vera"])
    launch.launch_curator(session_dir)
    assert "comment curator" in (session_dir / "prompts" / "Curator.md").read_text()
    assert launches == ["Vera", "Vera", "Curator", "Vera", "Curator"]
    assert git(repo, "status", "--porcelain") == ""


def test_local_context_is_omitted_from_ssh_prompts(context_workspace, tmp_path):
    from peanut_review.models import SshTarget
    from peanut_review.session import load_session, save_session

    _, repo, source = context_workspace
    session_dir = tmp_path / "session"
    create_session(
        workspace=str(repo), base_ref="HEAD", session_dir=str(session_dir),
        agents=[{"name": "Vera", "model": "test", "runner": "codex"},
                {"name": "Curator", "role": "curator", "model": "test", "runner": "codex"}],
    )
    session = load_session(session_dir)
    session.agents[0].ssh_target = "remote"
    session.ssh_targets["remote"] = SshTarget(
        host="reviewer@host", control_path="/tmp/master.sock",
        gateway_url="http://127.0.0.1:27184", workspace_root="/srv/project",
        build_roots=["/srv/project/build"],
    )
    save_session(session_dir, session)
    prompts = launch.render_all_prompts(
        session_dir, agent_names=["Vera", "Curator"], remote_launch_ids={"Vera": "test"},
    )
    assert "# Optional local context" not in prompts["Vera"].read_text()
    assert str(source) not in prompts["Vera"].read_text()
    assert str(source) in prompts["Curator"].read_text()
    assert not (repo / ".review-context").exists()

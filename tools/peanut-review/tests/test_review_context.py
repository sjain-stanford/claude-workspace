"""Optional file pointers reach every local launch without worktree mutations."""
from __future__ import annotations

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
    root = tmp_path / "workspace"
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "-q", "--allow-empty", "-m", "base")
    source = root / "private references" / "context.md"
    source.parent.mkdir()
    source.write_text("Private routing instructions stay in this file.\n")
    (root / review_context.CONFIG_NAME).write_text("private references/context.md\n")
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


@pytest.mark.parametrize("kind", ["absolute", "relative", "home"])
def test_path_resolution(context_workspace, monkeypatch, kind):
    root, repo, source = context_workspace
    monkeypatch.setenv("HOME", str(root))
    value = {"absolute": str(source), "relative": "private references/context.md",
             "home": "~/private references/context.md"}[kind]
    (root / review_context.CONFIG_NAME).write_text(value + "\n")
    assert review_context.discover(repo).source == source


def test_nearest_setting_and_empty_opt_out(context_workspace):
    root, repo, source = context_workspace
    local = repo / review_context.CONFIG_NAME
    local.write_text(str(source))
    assert review_context.discover(repo).root == repo
    local.write_text("")
    assert review_context.discover(repo) is None


@pytest.mark.parametrize("kind", ["unconfigured", "empty", "missing", "directory", "broken_link", "unreadable_file", "unreadable_setting"])
def test_unavailable_context_is_optional(context_workspace, monkeypatch, kind):
    root, repo, source = context_workspace
    config = root / review_context.CONFIG_NAME
    if kind == "unconfigured":
        config.unlink()
    elif kind == "empty":
        config.write_text("\n")
    elif kind in ("missing", "directory", "broken_link"):
        source.unlink()
        if kind == "directory":
            source.mkdir()
        elif kind == "broken_link":
            source.symlink_to(root / "missing.md")
    else:
        target = source if kind == "unreadable_file" else config
        original_open = Path.open

        def denied_open(path, *args, **kwargs):
            if path == target:
                raise PermissionError("test access denied")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", denied_open)
    assert review_context.discover(repo) is None


@pytest.mark.parametrize("setting", ["context.md".encode("utf-16"), b"\xffcontext.md"],
                         ids=["utf16", "invalid_utf8"])
def test_undecodable_setting_does_not_block_prompt_rendering(context_workspace, tmp_path, setting):
    _, repo, _ = context_workspace
    (repo / review_context.CONFIG_NAME).write_bytes(setting)
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

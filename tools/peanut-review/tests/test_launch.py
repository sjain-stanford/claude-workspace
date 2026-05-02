"""Tests for the launcher dispatch (cursor vs opencode)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from peanut_review import launch
from peanut_review.models import AgentConfig, Session


def _mock_git(workspace, *args):
    if args == ("rev-parse", "HEAD"):
        return "abc123def456"
    if args[0] == "diff" and "--stat" in args:
        return "+1 -0 1 file"
    return ""


def _make_session_dir(agents: list[AgentConfig]) -> str:
    from peanut_review.session import create_session

    sd = os.path.join(tempfile.mkdtemp(prefix="pr-launch-"), "session")
    with patch("peanut_review.session._run_git", side_effect=_mock_git):
        create_session(
            workspace="/tmp/fakerepo",
            agents=[a.to_dict() for a in agents],
            session_dir=sd,
        )
    return sd


def test_find_launcher_script_cursor():
    path = launch._find_launcher_script("cursor")
    assert path.endswith("cursor-agent-task.sh")
    assert Path(path).exists()


def test_find_launcher_script_opencode():
    path = launch._find_launcher_script("opencode")
    assert path.endswith("opencode-agent-task.sh")
    assert Path(path).exists()


def test_find_launcher_script_codex():
    path = launch._find_launcher_script("codex")
    assert path.endswith("codex-agent-task.sh")
    assert Path(path).exists()


def test_find_launcher_script_rejects_unknown_runner():
    try:
        launch._find_launcher_script("claude")
    except ValueError as e:
        assert "claude" in str(e)
    else:
        raise AssertionError("expected ValueError for unknown runner")


def test_agent_config_defaults_to_cursor():
    a = AgentConfig(name="vera", model="opus", persona="vera.md")
    assert a.runner == "cursor"


def test_launch_dry_run_cursor_agent_cmd():
    sd = _make_session_dir([AgentConfig(name="vera", model="opus-4.6-thinking", persona="vera.md")])
    results = launch.launch_agents(sd, dry_run=True)
    assert len(results) == 1
    cmd = results[0]["cmd"]
    assert cmd[0].endswith("cursor-agent-task.sh")
    assert "--model" in cmd and "opus-4.6-thinking" in cmd


def test_launch_dry_run_opencode_agent_cmd():
    sd = _make_session_dir([
        AgentConfig(
            name="felix", model="openai/gpt-5.5", persona="felix.md",
            runner="opencode",
        ),
    ])
    results = launch.launch_agents(sd, dry_run=True)
    assert len(results) == 1
    cmd = results[0]["cmd"]
    assert cmd[0].endswith("opencode-agent-task.sh")
    assert "--model" in cmd and "openai/gpt-5.5" in cmd


def test_launch_dry_run_mixed_runners():
    sd = _make_session_dir([
        AgentConfig(name="vera", model="opus-4.6-thinking", persona="vera.md"),
        AgentConfig(
            name="felix", model="openai/gpt-5.5", persona="felix.md",
            runner="opencode",
        ),
    ])
    results = launch.launch_agents(sd, dry_run=True)
    assert len(results) == 2
    assert results[0]["cmd"][0].endswith("cursor-agent-task.sh")
    assert results[1]["cmd"][0].endswith("opencode-agent-task.sh")


def test_launch_dry_run_codex_agent_cmd():
    sd = _make_session_dir([
        AgentConfig(name="cleo", model="gpt-5.5", persona="vera.md", runner="codex"),
    ])
    results = launch.launch_agents(sd, dry_run=True)
    assert len(results) == 1
    cmd = results[0]["cmd"]
    assert cmd[0].endswith("codex-agent-task.sh")
    assert "--model" in cmd and "gpt-5.5" in cmd
    # Codex needs the session dir writable so the agent can post comments.
    assert "--add-dir" in cmd
    assert sd in cmd


def test_launch_uses_python_supervisor_for_non_dry_run():
    sd = _make_session_dir([
        AgentConfig(
            name="felix", model="openai/gpt-5.5", persona="felix.md",
            runner="opencode",
        ),
    ])

    class DummyProc:
        pid = 424242

    with patch("peanut_review.launch.subprocess.Popen", return_value=DummyProc()) as popen:
        results = launch.launch_agents(sd)

    assert results[0]["pid"] is None
    assert results[0]["supervisor_pid"] == 424242
    supervisor_cmd = popen.call_args.args[0]
    assert supervisor_cmd[:3] == [sys.executable, "-m", "peanut_review.supervisor"]
    assert "--session" in supervisor_cmd and sd in supervisor_cmd
    separator = supervisor_cmd.index("--")
    assert supervisor_cmd[separator + 1].endswith("opencode-agent-task.sh")

    from peanut_review import session as sess
    stored = sess.load_session(sd)
    assert stored.agents[0].status == "running"
    assert stored.agents[0].pid is None
    assert stored.agents[0].supervisor_pid == 424242


def test_runner_wrappers_exec_without_shell_timeout():
    base = Path(launch._find_launcher_script("cursor")).parent
    cursor = (base / "cursor-agent-task.sh").read_text()
    opencode = (base / "opencode-agent-task.sh").read_text()
    codex = (base / "codex-agent-task.sh").read_text()

    for text in (cursor, opencode, codex):
        assert '\ntimeout "$timeout_secs"' not in text

    assert "exec cursor-agent --print" in cursor
    assert 'exec "${cmd[@]}" > "$output_file"' in opencode
    assert 'exec "${cmd[@]}" > "$stream_file"' in codex


def test_opencode_agent_uses_cli_prompt_template():
    """Opencode should always get the CLI prompt (MCP not wired up yet)."""
    sd = _make_session_dir([
        AgentConfig(
            name="felix", model="openai/gpt-5.5", persona="felix.md",
            runner="opencode",
        ),
    ])
    prompts = launch.render_all_prompts(sd)
    rendered = prompts["felix"].read_text()
    # CLI template self-identifies by instructing the agent to execute shell commands.
    assert "Shell tool" in rendered
    # The MCP template mentions MCP tool names like add_comment (not Shell).
    assert "mcp__peanut-review" not in rendered


def test_session_roundtrip_preserves_runner():
    from peanut_review import session as sess
    sd = _make_session_dir([
        AgentConfig(
            name="felix", model="openai/gpt-5.5", persona="felix.md",
            runner="opencode",
        ),
    ])
    s = sess.load_session(sd)
    assert s.agents[0].runner == "opencode"
    assert s.agents[0].model == "openai/gpt-5.5"

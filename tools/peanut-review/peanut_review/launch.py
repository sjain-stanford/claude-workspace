"""Spawn cursor agents for review — replaces cursor-agent-multi.py."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from string import Template

from .models import AgentStatus, SessionState
from .session import load_session, save_session, update_agent_status


_LAUNCHER_SCRIPTS = {
    "cursor": "cursor-agent-task.sh",
    "opencode": "opencode-agent-task.sh",
    "codex": "codex-agent-task.sh",
}
_MCP_SERVER_NAME = "peanut-review"
_MCP_MANAGED_ENV = "PEANUT_REVIEW_MCP_MANAGED"


def _find_launcher_script(runner: str = "cursor") -> str:
    """Find the launcher script for a given runner ("cursor" or "opencode")."""
    script_name = _LAUNCHER_SCRIPTS.get(runner)
    if not script_name:
        raise ValueError(f"unknown runner: {runner!r} (expected one of {list(_LAUNCHER_SCRIPTS)})")
    path = (Path(__file__).resolve().parent.parent.parent.parent
            / "skills" / "ask-the-peanut-gallery" / script_name)
    if path.exists():
        return str(path)
    raise FileNotFoundError(f"{script_name} not found at {path}")


def render_prompt(template_path: str | Path, variables: dict[str, str]) -> str:
    """Render an agent prompt template with variable substitution.

    Uses $VARIABLE or ${VARIABLE} syntax (string.Template).
    """
    text = Path(template_path).read_text()
    return Template(text).safe_substitute(variables)


def _resolve_template(user_template: str | Path | None, runner: str) -> str:
    """Pick the prompt template for a given runner.

    Explicit --template always wins. Otherwise: cursor prefers MCP if the MCP
    launcher script is installed; opencode always uses the CLI template (MCP
    integration is not wired up yet).
    """
    if user_template:
        return str(user_template)
    skills_dir = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "peanut-review"
    if runner == "cursor":
        mcp_script = Path(__file__).resolve().parent.parent / "bin" / "peanut-review-mcp"
        if mcp_script.exists():
            mcp_default = skills_dir / "agent-prompt-mcp.md"
            if mcp_default.exists():
                return str(mcp_default)
    default = skills_dir / "agent-prompt.md"
    if default.exists():
        return str(default)
    raise FileNotFoundError(
        f"no prompt template found for runner={runner!r} (looked in {skills_dir})"
    )


def render_all_prompts(
    session_dir: str | Path,
    template_path: str | Path | None = None,
) -> dict[str, Path]:
    """Render per-agent prompts and write to <session>/prompts/. Returns {agent: path}.

    If template_path is provided, it is used for all agents. Otherwise the
    template is picked per agent based on agent.runner.
    """
    session = load_session(session_dir)
    sdir = Path(session_dir)
    prompts_dir = sdir / "prompts"
    prompts_dir.mkdir(exist_ok=True)

    pr_bin = str(Path(__file__).resolve().parent.parent / "bin" / "peanut-review")

    result = {}
    for agent in session.agents:
        variables = {
            "SESSION": str(sdir),
            "WORKSPACE": session.workspace,
            "AGENT": agent.name,
            "DIFF_COMMANDS": " && ".join(session.diff_commands),
            "BASE_REF": session.base_ref,
            "TOPIC_REF": session.topic_ref,
            "PR_BIN": pr_bin,
        }
        tpl = _resolve_template(template_path, agent.runner)
        rendered = render_prompt(tpl, variables)
        prompt_path = prompts_dir / f"{agent.name}.md"
        prompt_path.write_text(rendered)
        result[agent.name] = prompt_path

    return result


def _validate_cli_json(workspace: str | Path) -> None:
    """Warn if cli.json is missing peanut-review permissions or has Shell(**) deny."""
    cli_json_path = Path(workspace) / ".cursor" / "cli.json"
    if not cli_json_path.exists():
        print(f"Warning: {cli_json_path} not found — agents may lack permissions", file=sys.stderr)
        return
    try:
        data = json.loads(cli_json_path.read_text())
        perms = data.get("permissions", {})
        allow = perms.get("allow", [])
        deny = perms.get("deny", [])

        has_pr = any("peanut-review" in str(a) for a in allow)
        if not has_pr:
            print("Warning: cli.json allow list does not include 'Shell(peanut-review **)' "
                  "— agents won't be able to run peanut-review", file=sys.stderr)

        has_shell_deny = any(str(d) == "Shell(**)" for d in deny)
        if has_shell_deny:
            print("Warning: cli.json deny list contains 'Shell(**)' which overrides all "
                  "Shell allows — agents won't be able to run any shell commands", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Warning: could not parse {cli_json_path}: {e}", file=sys.stderr)


def _find_mcp_script() -> str | None:
    """Find the peanut-review-mcp script (uses uv for zero-install)."""
    script = Path(__file__).resolve().parent.parent / "bin" / "peanut-review-mcp"
    if script.exists():
        return str(script)
    return None


def _mcp_server_config(session_dir: Path, agent_name: str, mcp_script: str) -> dict:
    return {
        "mcpServers": {
            _MCP_SERVER_NAME: {
                "command": mcp_script,
                "env": {
                    "PEANUT_SESSION": str(session_dir),
                    "GIT_AUTHOR_NAME": agent_name,
                    _MCP_MANAGED_ENV: "1",
                },
            }
        }
    }


def _is_generated_mcp_server(server: object) -> bool:
    """Return true for peanut-review-managed MCP entries, including legacy ones."""
    if not isinstance(server, dict):
        return False
    env = server.get("env")
    env = env if isinstance(env, dict) else {}
    if env.get(_MCP_MANAGED_ENV) == "1":
        return True
    command = server.get("command")
    if not isinstance(command, str):
        return False
    return (
        Path(command).name == "peanut-review-mcp"
        and "PEANUT_SESSION" in env
        and "GIT_AUTHOR_NAME" in env
    )


def _cleanup_workspace_mcp_config(workspace: str | Path, *, dry_run: bool = False) -> Path | None:
    """Remove old generated workspace peanut-review MCP config.

    Cursor still considers workspace .cursor/mcp.json. A custom server named
    peanut-review there can shadow the per-agent config, so fail clearly unless
    the entry looks like one peanut-review generated and can safely remove.
    """
    mcp_path = Path(workspace) / ".cursor" / "mcp.json"
    if not mcp_path.exists():
        return None
    try:
        data = json.loads(mcp_path.read_text())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"could not parse Cursor MCP config {mcp_path}: {e}") from e
    if not isinstance(data, dict):
        return mcp_path
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or _MCP_SERVER_NAME not in servers:
        return mcp_path
    if not _is_generated_mcp_server(servers[_MCP_SERVER_NAME]):
        raise RuntimeError(
            f"{mcp_path} already defines mcpServers.{_MCP_SERVER_NAME}, but it "
            "does not look like a peanut-review-generated entry. Remove or "
            "rename that server before launching Cursor reviewers because it "
            "would shadow the per-agent MCP config."
        )
    if dry_run:
        return mcp_path
    servers.pop(_MCP_SERVER_NAME, None)
    mcp_path.write_text(json.dumps(data, indent=2) + "\n")
    return mcp_path


def _cursor_runtime_paths(session_dir: Path, agent_name: str) -> dict[str, Path]:
    cursor_home = session_dir / "runtime" / "cursor" / agent_name
    cursor_dir = cursor_home / ".cursor"
    return {
        "cursor_home": cursor_home,
        "cursor_dir": cursor_dir,
        "mcp_config": cursor_dir / "mcp.json",
    }


def _setup_cursor_runtime(
    session_dir: Path,
    agent_name: str,
    mcp_script: str | None,
    *,
    dry_run: bool = False,
) -> dict[str, str]:
    """Prepare an isolated Cursor home/config directory for one agent."""
    paths = _cursor_runtime_paths(session_dir, agent_name)
    if not dry_run:
        paths["cursor_dir"].mkdir(parents=True, exist_ok=True)
        if mcp_script:
            mcp_config = _mcp_server_config(session_dir, agent_name, mcp_script)
            paths["mcp_config"].write_text(json.dumps(mcp_config, indent=2) + "\n")
    runtime = {"cursor_home": str(paths["cursor_home"])}
    if mcp_script:
        runtime["mcp_config"] = str(paths["mcp_config"])
    return runtime


def _apply_cursor_env(env: dict[str, str], cursor_runtime: dict[str, str]) -> None:
    original_home = env.get("HOME") or str(Path.home())
    original_xdg_config = env.get("XDG_CONFIG_HOME") or str(Path(original_home) / ".config")
    cursor_home = cursor_runtime["cursor_home"]
    cursor_config_dir = str(Path(cursor_home) / ".cursor")

    env["HOME"] = cursor_home
    env["CURSOR_CONFIG_DIR"] = cursor_config_dir
    env["CURSOR_DATA_DIR"] = cursor_config_dir
    env["XDG_CONFIG_HOME"] = original_xdg_config
    env["PEANUT_CURSOR_HOME"] = cursor_home
    if "mcp_config" in cursor_runtime:
        env["PEANUT_CURSOR_MCP_CONFIG"] = cursor_runtime["mcp_config"]


def _build_agent_cmd(
    agent,
    *,
    session,
    session_dir: Path,
    prompt_path: Path,
) -> list[str]:
    """Build the launcher command for a single agent based on its runner."""
    launcher = _find_launcher_script(agent.runner)
    cmd = [
        launcher,
        "--model", agent.model,
        "--workspace", session.workspace,
        "--output-dir", str(session_dir / "log"),
        "--name", agent.name,
        "--timeout", str(session.timeout),
        "--prompt-file", str(prompt_path),
    ]
    if agent.runner == "codex":
        # Codex sandboxes the agent to the workspace by default; the session
        # dir lives outside it, so without --add-dir the agent can't write
        # comments/signals through `peanut-review add-comment`. /tmp is added
        # for ad-hoc body files (agent-prompt.md instructs agents to use
        # `--body-file /tmp/...` to dodge backtick-quoting issues).
        cmd += ["--add-dir", str(session_dir), "--add-dir", "/tmp"]
    return cmd


def _build_supervisor_cmd(
    *,
    session_dir: Path,
    agent_name: str,
    timeout: int,
    workspace: str,
    wrapper_cmd: list[str],
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "peanut_review.supervisor",
        "--session",
        str(session_dir),
        "--agent",
        agent_name,
        "--timeout",
        str(timeout),
        "--cwd",
        workspace,
        "--",
        *wrapper_cmd,
    ]


def launch_agents(
    session_dir: str | Path,
    template_path: str | Path | None = None,
    dry_run: bool = False,
    cli_json: str | None = None,
) -> list[dict]:
    """Spawn agents for all entries in the session, dispatching by agent.runner.

    Returns list of {name, pid, cmd} dicts.
    """
    session = load_session(session_dir)
    sdir = Path(session_dir)

    runners = {a.runner for a in session.agents}
    if "cursor" in runners:
        _validate_cli_json(session.workspace)
        _cleanup_workspace_mcp_config(session.workspace, dry_run=dry_run)

    mcp_script = _find_mcp_script() if "cursor" in runners else None
    if "cursor" in runners and not mcp_script:
        print("  MCP: peanut-review-mcp script not found", file=sys.stderr)

    prompts = render_all_prompts(session_dir, template_path)

    session.state = SessionState.ROUND.value
    save_session(sdir, session)

    results = []
    for agent in session.agents:
        prompt_path = prompts[agent.name]
        log_path = sdir / "log" / f"{agent.name}.log"
        cmd = _build_agent_cmd(agent, session=session, session_dir=sdir, prompt_path=prompt_path)
        supervisor_cmd = _build_supervisor_cmd(
            session_dir=sdir,
            agent_name=agent.name,
            timeout=session.timeout,
            workspace=session.workspace,
            wrapper_cmd=cmd,
        )

        env = os.environ.copy()
        bin_dir = str(Path(__file__).resolve().parent.parent / "bin")
        env["PATH"] = bin_dir + ":" + env.get("PATH", "")
        env["GIT_AUTHOR_NAME"] = agent.name
        env["GIT_AUTHOR_EMAIL"] = f"{agent.name}@peanut-review.local"
        env["GIT_COMMITTER_NAME"] = agent.name
        env["GIT_COMMITTER_EMAIL"] = f"{agent.name}@peanut-review.local"
        env["PEANUT_SESSION"] = str(sdir)
        cursor_runtime = None
        if agent.runner == "cursor":
            cursor_runtime = _setup_cursor_runtime(
                sdir,
                agent.name,
                mcp_script,
                dry_run=dry_run,
            )
            _apply_cursor_env(env, cursor_runtime)

        if dry_run:
            result = {
                "name": agent.name,
                "pid": None,
                "pgid": None,
                "supervisor_pid": None,
                "cmd": cmd,
                "supervisor_cmd": supervisor_cmd,
            }
            if cursor_runtime:
                result.update(cursor_runtime)
            results.append(result)
            continue

        with open(log_path, "w") as log_file:
            proc = subprocess.Popen(
                supervisor_cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=session.workspace,
                start_new_session=True,
            )

        update_agent_status(
            sdir,
            agent.name,
            AgentStatus.RUNNING.value,
            supervisor_pid=proc.pid,
        )
        result = {
            "name": agent.name,
            "pid": None,
            "pgid": None,
            "supervisor_pid": proc.pid,
            "cmd": cmd,
            "supervisor_cmd": supervisor_cmd,
        }
        if cursor_runtime:
            result.update(cursor_runtime)
        results.append(result)

        # Stagger launches: cursor-agent has a cli-config.json race, and lcode's
        # idempotent llama-server startup also benefits from letting the first
        # opencode agent finish booting servers before peers join.
        if agent != session.agents[-1]:
            time.sleep(1)

    return results

"""Offline regressions for CI check reporting."""

import argparse
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).parents[1] / "scripts" / "inspect_pr_checks.py"
    spec = importlib.util.spec_from_file_location("inspect_pr_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_successful_json_output_is_parseable(helper, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(helper, "parse_args", lambda: argparse.Namespace(
        repo=str(tmp_path), pr="42", json=True,
    ))
    monkeypatch.setattr(helper, "find_git_root", lambda path: path)
    monkeypatch.setattr(helper, "ensure_gh_available", lambda path: True)
    monkeypatch.setattr(helper, "fetch_checks", lambda *args: [{"state": "SUCCESS"}])
    assert helper.main() == 0
    assert json.loads(capsys.readouterr().out) == {"pr": "42", "results": []}


def test_current_check_fields_succeed_without_a_fallback(helper, monkeypatch, tmp_path):
    def run(args, cwd):
        fields = args[args.index("--json") + 1].split(",")
        assert "link" in fields and "bucket" in fields
        assert "detailsUrl" not in fields and "conclusion" not in fields
        return helper.GhResult(0, '[{"state":"FAILURE","bucket":"fail"}]', "")

    monkeypatch.setattr(helper, "run_gh_command", run)
    checks = helper.fetch_checks("42", tmp_path)
    assert len(checks) == 1 and helper.is_failing(checks[0])


@pytest.mark.parametrize("max_lines", [1, 2, 10, 160])
@pytest.mark.parametrize("error_line", [0, 50, 99])
def test_bounded_snippet_always_contains_failure(helper, max_lines, error_line):
    lines = [f"ordinary output {i}" for i in range(100)]
    lines[error_line] = "fatal: compilation failed"
    snippet = helper.extract_failure_snippet("\n".join(lines), max_lines, context=30)
    assert "fatal: compilation failed" in snippet
    assert len(snippet.splitlines()) <= max_lines


def test_legacy_check_fields_are_used_when_advertised(helper, monkeypatch, tmp_path):
    calls = []

    def run(args, cwd):
        calls.append(args)
        if len(calls) == 1:
            return helper.GhResult(1, "", "Unknown JSON field: bucket\nAvailable fields:\n"
                                   "  name\n  state\n  conclusion\n  detailsUrl\n")
        fields = args[args.index("--json") + 1].split(",")
        assert fields == ["name", "state", "conclusion", "detailsUrl"]
        return helper.GhResult(0, '[{"name":"build","conclusion":"failure"}]', "")

    monkeypatch.setattr(helper, "run_gh_command", run)
    checks = helper.fetch_checks("42", tmp_path)
    assert len(calls) == 2
    assert len(checks) == 1 and helper.is_failing(checks[0])

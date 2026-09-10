"""Offline regressions for PR identity and independent GraphQL pagination."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).parents[1] / "scripts" / "fetch_comments.py"
    spec = importlib.util.spec_from_file_location("fetch_comments", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def connection(nodes, cursor=None):
    return {"nodes": nodes, "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}}


@pytest.mark.parametrize("hostname", ["github.com", "github.example.com"])
def test_fork_pr_uses_base_repository_and_host(helper, monkeypatch, hostname):
    monkeypatch.setattr(helper, "gh_pr_view_json", lambda fields: {
        "number": 42,
        "url": f"https://{hostname}/upstream/project/pull/42",
        "headRepositoryOwner": {"login": "contributor"},
        "headRepository": {"name": "fork"},
    })
    assert helper.get_current_pr_ref() == (hostname, "upstream", "project", 42)


def test_unequal_page_counts_do_not_repeat_completed_connections(helper, monkeypatch):
    calls = []

    def graphql(cmd, stdin):
        assert stdin == helper.QUERY
        assert cmd[cmd.index("--hostname") + 1] == "github.example.com"
        values = dict(item.split("=", 1) for item in cmd if "=" in item)
        calls.append(values)
        assert len(calls) <= 3
        pr = {"number": 42, "url": "https://github.example.com/upstream/project/pull/42",
              "title": "Example", "state": "OPEN"}
        for field, variable, pages in (("comments", "Comments", 2),
                                       ("reviews", "Reviews", 3),
                                       ("reviewThreads", "Threads", 1)):
            if values[f"include{variable}"] == "false":
                continue
            index = int(values.get(f"{variable.lower()}Cursor", "0"))
            node = {"id": f"{field}-{index}"}
            if field == "reviewThreads":
                node["comments"] = connection([])
            pr[field] = connection([node], str(index + 1) if index + 1 < pages else None)
        return {"data": {"repository": {"pullRequest": pr}}}

    monkeypatch.setattr(helper, "_run_json", graphql)
    result = helper.fetch_all("upstream", "project", 42, "github.example.com")
    assert [c["id"] for c in result["conversation_comments"]] == ["comments-0", "comments-1"]
    assert [r["id"] for r in result["reviews"]] == ["reviews-0", "reviews-1", "reviews-2"]
    assert len(result["review_threads"]) == 1
    assert len(calls) == 3
    assert calls[1]["includeThreads"] == "false"
    assert calls[2]["includeComments"] == "false"


def test_thread_comments_beyond_first_hundred_are_fetched(helper, monkeypatch):
    thread = {"id": "thread-1", "comments": connection(
        [{"id": f"comment-{i}"} for i in range(100)], "page-2",
    )}
    requests = []

    def graphql(cmd, stdin):
        assert stdin == helper.THREAD_COMMENTS_QUERY
        assert cmd[cmd.index("--hostname") + 1] == "github.example.com"
        requests.append(cmd)
        if "cursor=page-2" in cmd:
            page = connection([{"id": f"comment-{i}"} for i in range(100, 200)], "page-3")
        else:
            assert "cursor=page-3" in cmd
            page = connection([{"id": "comment-200"}])
        return {"data": {"node": {"comments": page}}}

    monkeypatch.setattr(helper, "_run_json", graphql)
    helper._complete_thread_comments(thread, "github.example.com")
    assert [c["id"] for c in thread["comments"]["nodes"]] == [f"comment-{i}" for i in range(201)]
    assert len(requests) == 2
    assert "pageInfo" not in thread["comments"]


@pytest.mark.parametrize("repository", [None, {"pullRequest": None}])
def test_missing_pr_reports_actionable_error(helper, monkeypatch, repository):
    monkeypatch.setattr(helper, "gh_api_graphql", lambda **kwargs: {"data": {"repository": repository}})
    with pytest.raises(RuntimeError, match="Pull request not found"):
        helper.fetch_all("upstream", "project", 42)


def test_graphql_errors_are_not_silently_returned_as_partial_results(helper, monkeypatch):
    monkeypatch.setattr(helper, "gh_api_graphql", lambda **kwargs: {
        "errors": [{"message": "rate limit"}], "data": {"repository": None},
    })
    with pytest.raises(RuntimeError, match="rate limit"):
        helper.fetch_all("upstream", "project", 42)


@pytest.mark.parametrize("cursor", [None, "unchanged"])
def test_nonadvancing_cursor_fails_instead_of_looping(helper, cursor):
    page = {"pageInfo": {"hasNextPage": True, "endCursor": cursor}}
    with pytest.raises(RuntimeError, match="did not advance"):
        helper._next_cursor(page, "unchanged")


def test_nested_graphql_errors_are_reported(helper, monkeypatch):
    thread = {"id": "thread-1", "comments": connection([], "next")}
    monkeypatch.setattr(helper, "_run_json", lambda *args, **kwargs: {
        "errors": [{"message": "thread unavailable"}],
    })
    with pytest.raises(RuntimeError, match="thread unavailable"):
        helper._complete_thread_comments(thread, "github.com")

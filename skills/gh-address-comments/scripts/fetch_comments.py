#!/usr/bin/env python3
"""
Fetch all PR conversation comments + reviews + review threads (inline threads)
for the PR associated with the current git branch, by shelling out to:

  gh api graphql

Requires:
  - `gh auth login` already set up
  - current branch has an associated (open) PR

Usage:
  python fetch_comments.py > pr_comments.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

QUERY = """\
query(
  $owner: String!,
  $repo: String!,
  $number: Int!,
  $commentsCursor: String,
  $reviewsCursor: String,
  $threadsCursor: String,
  $includeComments: Boolean!,
  $includeReviews: Boolean!,
  $includeThreads: Boolean!
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      url
      title
      state

      # Top-level "Conversation" comments (issue comments on the PR)
      comments(first: 100, after: $commentsCursor) @include(if: $includeComments) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          createdAt
          updatedAt
          author { login }
        }
      }

      # Review submissions (Approve / Request changes / Comment), with body if present
      reviews(first: 100, after: $reviewsCursor) @include(if: $includeReviews) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          state
          body
          submittedAt
          author { login }
        }
      }

      # Inline review threads (grouped), includes resolved state
      reviewThreads(first: 100, after: $threadsCursor) @include(if: $includeThreads) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          diffSide
          startLine
          startDiffSide
          originalLine
          originalStartLine
          resolvedBy { login }
          comments(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              body
              createdAt
              updatedAt
              author { login }
            }
          }
        }
      }
    }
  }
}
"""

THREAD_COMMENTS_QUERY = """\
query($id: ID!, $cursor: String!) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          createdAt
          updatedAt
          author { login }
        }
      }
    }
  }
}
"""


def _run(cmd: list[str], stdin: str | None = None) -> str:
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr}")
    return p.stdout


def _run_json(cmd: list[str], stdin: str | None = None) -> dict[str, Any]:
    out = _run(cmd, stdin=stdin)
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse JSON from command output: {e}\nRaw:\n{out}") from e


def _ensure_gh_authenticated() -> None:
    try:
        _run(["gh", "auth", "status"])
    except RuntimeError:
        print("run `gh auth login` to authenticate the GitHub CLI", file=sys.stderr)
        raise RuntimeError("gh auth status failed; run `gh auth login` to authenticate the GitHub CLI") from None


def gh_pr_view_json(fields: str) -> dict[str, Any]:
    # fields is a comma-separated list like: "number,headRepositoryOwner,headRepository"
    return _run_json(["gh", "pr", "view", "--json", fields])


def get_current_pr_ref() -> tuple[str, str, str, int]:
    """
    Resolve the PR for the current branch (whatever gh considers associated).
    The PR URL identifies its host and base repository, including fork PRs.
    """
    pr = gh_pr_view_json("number,url")
    url = urlparse(pr["url"])
    parts = url.path.strip("/").split("/")
    if not url.hostname or len(parts) != 4 or parts[2] != "pull":
        raise RuntimeError(f"Unexpected pull request URL: {pr['url']}")
    return url.hostname, parts[0], parts[1], int(pr["number"])


def gh_api_graphql(
    owner: str,
    repo: str,
    number: int,
    comments_cursor: str | None = None,
    reviews_cursor: str | None = None,
    threads_cursor: str | None = None,
    hostname: str = "github.com",
    include_comments: bool = True,
    include_reviews: bool = True,
    include_threads: bool = True,
) -> dict[str, Any]:
    """
    Call `gh api graphql` using -F variables, avoiding JSON blobs with nulls.
    Query is passed via stdin using query=@- to avoid shell newline/quoting issues.
    """
    cmd = [
        "gh",
        "api",
        "graphql",
        "--hostname",
        hostname,
        "-F",
        "query=@-",
        "-F",
        f"owner={owner}",
        "-F",
        f"repo={repo}",
        "-F",
        f"number={number}",
        "-F",
        f"includeComments={str(include_comments).lower()}",
        "-F",
        f"includeReviews={str(include_reviews).lower()}",
        "-F",
        f"includeThreads={str(include_threads).lower()}",
    ]
    if comments_cursor:
        cmd += ["-F", f"commentsCursor={comments_cursor}"]
    if reviews_cursor:
        cmd += ["-F", f"reviewsCursor={reviews_cursor}"]
    if threads_cursor:
        cmd += ["-F", f"threadsCursor={threads_cursor}"]

    return _run_json(cmd, stdin=QUERY)


def _check_graphql_errors(payload: dict[str, Any]) -> None:
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors:\n{json.dumps(payload['errors'], indent=2)}")


def _next_cursor(connection: dict[str, Any], previous: str | None) -> str | None:
    info = connection["pageInfo"]
    if not info["hasNextPage"]:
        return None
    cursor = info["endCursor"]
    if not cursor or cursor == previous:
        raise RuntimeError("GitHub pagination did not advance")
    return cursor


def _complete_thread_comments(thread: dict[str, Any], hostname: str) -> None:
    connection = thread["comments"]
    cursor = _next_cursor(connection, None)
    while cursor:
        payload = _run_json([
            "gh", "api", "graphql", "--hostname", hostname,
            "-F", "query=@-", "-F", f"id={thread['id']}", "-F", f"cursor={cursor}",
        ], stdin=THREAD_COMMENTS_QUERY)
        _check_graphql_errors(payload)
        node = payload["data"]["node"]
        if node is None:
            raise RuntimeError(f"Review thread is no longer available: {thread['id']}")
        page = node["comments"]
        connection["nodes"].extend(page.get("nodes") or [])
        cursor = _next_cursor(page, cursor)
    # Preserve the original output shape: callers consume comments.nodes.
    connection.pop("pageInfo")


def fetch_all(
    owner: str, repo: str, number: int, hostname: str = "github.com",
) -> dict[str, Any]:
    conversation_comments: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    review_threads: list[dict[str, Any]] = []

    comments_cursor: str | None = None
    reviews_cursor: str | None = None
    threads_cursor: str | None = None
    comments_done = reviews_done = threads_done = False

    pr_meta: dict[str, Any] | None = None

    while True:
        payload = gh_api_graphql(
            owner=owner,
            repo=repo,
            number=number,
            comments_cursor=comments_cursor,
            reviews_cursor=reviews_cursor,
            threads_cursor=threads_cursor,
            hostname=hostname,
            include_comments=not comments_done,
            include_reviews=not reviews_done,
            include_threads=not threads_done,
        )

        _check_graphql_errors(payload)

        repository = payload["data"]["repository"]
        pr = repository["pullRequest"] if repository else None
        if pr is None:
            raise RuntimeError(f"Pull request not found: {hostname}/{owner}/{repo}#{number}")
        if pr_meta is None:
            pr_meta = {
                "number": pr["number"],
                "url": pr["url"],
                "title": pr["title"],
                "state": pr["state"],
                "owner": owner,
                "repo": repo,
            }

        if not comments_done:
            c = pr["comments"]
            conversation_comments.extend(c.get("nodes") or [])
            comments_cursor = _next_cursor(c, comments_cursor)
            comments_done = comments_cursor is None
        if not reviews_done:
            r = pr["reviews"]
            reviews.extend(r.get("nodes") or [])
            reviews_cursor = _next_cursor(r, reviews_cursor)
            reviews_done = reviews_cursor is None
        if not threads_done:
            t = pr["reviewThreads"]
            for thread in t.get("nodes") or []:
                _complete_thread_comments(thread, hostname)
                review_threads.append(thread)
            threads_cursor = _next_cursor(t, threads_cursor)
            threads_done = threads_cursor is None

        if comments_done and reviews_done and threads_done:
            break

    assert pr_meta is not None
    return {
        "pull_request": pr_meta,
        "conversation_comments": conversation_comments,
        "reviews": reviews,
        "review_threads": review_threads,
    }


def main() -> None:
    _ensure_gh_authenticated()
    hostname, owner, repo, number = get_current_pr_ref()
    result = fetch_all(owner, repo, number, hostname)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

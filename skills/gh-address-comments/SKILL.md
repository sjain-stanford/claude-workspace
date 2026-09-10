---
name: gh-address-comments
description: Help address review/issue comments on the open GitHub PR for the current branch using gh CLI; verify gh auth first and prompt the user to authenticate if not logged in.
metadata:
  short-description: Address comments in a GitHub PR review
---

# PR Comment Handler

Find the open PR for the current branch and address the requested comments with
the gh CLI. Use the PR's branch-backed development worktree and the target
repository's contribution and verification guidance.

Run `gh auth status` for the target host with normal permissions first. Request
network escalation only when the sandbox actually blocks access. Ask the user
to authenticate only for an authentication failure; distinguish that from rate
limits and transient network failures.

## 1) Inspect comments needing attention
- Run `python3 <skill-dir>/scripts/fetch_comments.py` from the PR worktree to
  print conversation comments, reviews, and complete inline threads as JSON.
  The helper resolves the base repository and host from the PR URL, including
  fork PRs, and paginates each connection and long thread independently.

## 2) Establish scope
- Follow comments already selected by the user. A request to address PR
  feedback authorizes fixing actionable comments; do not ask the user to
  select the same scope again.
- Summarize actionable findings and validate them against the current code.
  Ask only when a comment requires a material product decision or its intended
  scope is unclear.

## 3) Apply and verify fixes
- Implement the requested fixes, run appropriate checks, and summarize which
  comments were addressed or remain unresolved.
- Posting replies or resolving GitHub threads requires explicit authorization
  to change that remote discussion state.

Offline helper checks: `python3 -m pytest <skill-dir>/tests`.

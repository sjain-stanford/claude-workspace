---
name: pr-review
description: Perform a focused single-agent pull request review and save a Markdown report. Use for ordinary PR review requests; use peanut-review instead when the user asks for multi-agent reviewers, personas, curation, a persistent session, the web UI, or GitHub publishing.
---

# PR Review Skill

Provides comprehensive pull request reviews following project coding standards.

This is the lightweight, report-oriented review path. Do not launch
peanut-review implicitly. If a peanut-review session already exists, inspect it
only when the user asks to incorporate or summarize that session.

## Usage

```
/pr-review <PR-URL-or-number> [--repo <repo-name>]
```

## Review Process

### 1. Fetch PR Branch and Get Diff

Resolve the PR's URL, author, head branch/commit, and actual base branch first:

```shell
gh pr view <PR-number-or-URL> --json url,author,headRefName,headRefOid,baseRefName
git status --short
git worktree list
```

Reuse the branch-backed task worktree that owns the PR branch. If none exists,
create one under `<workspace-root>/projects/worktrees/<repo>/`; preserve the
PR branch name. Do not switch the canonical checkout or discard local changes.
Identify the remote for the PR's base repository, including for fork PRs.
Fetch its base branch before collecting the diff, including when reusing an
existing worktree.

For a PR branch that is not already local, run from `projects/<repo>`:

```shell
git fetch <base-remote> <baseRefName>
git fetch <base-remote> pull/<PR-number>/head
git worktree add -b <headRefName> ../worktrees/<repo>/pr-<number>-<change> FETCH_HEAD
```

If the local branch exists, add its worktree using that branch instead of
`-b ... FETCH_HEAD`. Check that its `HEAD` matches `headRefOid`; handle divergence
without overwriting local commits or uncommitted work. Ask only if the intended
review snapshot cannot be inferred safely.

From the selected worktree, use the resolved base (`develop` for rocjitsu),
never a hardcoded `main`:

```shell
git diff <base-remote>/<baseRefName>...HEAD

# List all changed files
git diff --name-only <base-remote>/<baseRefName>...HEAD

# View commit history on this branch
git log <base-remote>/<baseRefName>..HEAD --oneline
```

Read the changed files directly using the Read tool and use file-relative line numbers when referencing code.

Leave the PR worktree available for follow-up discussion. Identify any local
changes separately; a GitHub PR review covers the committed PR snapshot.

### 2. Review the Changes against Review Criteria

**CRITICAL**: Review the code referencing `skills/review-criteria.md` for the complete review checklist, code standards, and output format. Do not miss this step as otherwise the review is pointless.

### 3. Save Review

Use the standard output format from `skills/review-criteria.md` with:
- **Review-Type**: "PR Review"
- **Source**: PR URL
- **Author**: PR author from metadata
- **Branch**: `<headRefName> -> <baseRefName>`

Save the review to `<workspace_root>/reviews/` with filename `pr-review-<repo>-<number>.md` (example: `pr-review-rocm-systems-123.md`). If the file already exists, check if the PR / diff was updated since last review and re-review if so, saving to a file of the same name with a suffix `-take-N.md` for the Nth attempt.

**IMPORTANT**: Always save reviews to the top-level `claude-workspace/reviews/` directory, not within sub-project directories.

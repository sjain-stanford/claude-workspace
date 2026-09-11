---
name: self-review
description: Perform a focused single-agent review of local branch changes before creating a PR. Use for ordinary local review requests; use peanut-review instead when the user asks for multi-agent reviewers, personas, curation, a persistent session, or the web UI.
---

# Self Review Skill

Provides comprehensive review of local branch changes following project coding standards.

This is the lightweight, report-oriented local review path. Do not launch
peanut-review implicitly. If a peanut-review session already exists, inspect it
only when the user asks to incorporate or summarize that session.

## Usage

```
/self-review [--base <ref>]
```

- **Default**: Reviews changes between the repository's actual target branch and
  `HEAD` (`develop` for rocjitsu); infer it from branch/PR/upstream context
- **Custom base**: Use `--base <ref>` to specify a different base reference (e.g., `--base origin/feature`)
- Include staged and unstaged changes plus relevant untracked source files
  unless the user explicitly requests only committed changes.

## Review Process

### 1. Detect Current Branch and Get Diff

```shell
# Get current branch name and determine the intended target branch
git branch --show-current
git status --short

# Get diff against the resolved base
git diff <base>...HEAD

# Inspect staged and unstaged changes as well
git diff --cached
git diff

# List changed files
git diff --name-only <base>...HEAD
```

Read relevant untracked files from `git status` directly. Do not stage or
commit merely to make them reviewable. Assess the final working-tree content
against the merge base (use `git diff <merge-base>` after resolving it with
`git merge-base <base> HEAD`), so committed, staged, and unstaged edits are
reviewed together. Record the base, `HEAD`, and local-change scope in the report.

### 2. Review the Changes against Review Criteria

**CRITICAL**: Review the code referencing `skills/review-criteria.md` for the complete review checklist, code standards, and output format. Do not miss this step as otherwise the review is pointless.

### 3. Save Review

Use the standard output format from `skills/review-criteria.md` with:
- **Review-Type**: "Self Review"
- **Source**: Current branch name
- **Author**: Current git user (`git config user.name`)
- **Branch**: `<current-branch> -> <base-ref>`

Save the review to `<workspace-root>/reviews/` with filename `self-review-<short-description>.md`, where `<short-description>` is a few words separated by dashes summarizing the changes (e.g., `self-review-add-auth-middleware.md`, `self-review-fix-cache-invalidation.md`).

**IMPORTANT**: Always save reviews to the top-level `claude-workspace/reviews/` directory, not within sub-project directories.

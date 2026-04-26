---
name: self-review
description: Review local branch changes before creating a PR. Use when you want feedback on uncommitted or committed changes on the current branch compared to main or another base branch.
---

# Self Review Skill

Provides comprehensive review of local branch changes following project coding standards.

## Usage

```
/self-review [--base <ref>]
```

- **Default**: Reviews changes between `main` and `HEAD`
- **Custom base**: Use `--base <ref>` to specify a different base reference (e.g., `--base origin/feature`)

## Review Process

### 1. Detect Current Branch and Get Diff

```shell
# Get current branch name
git branch --show-current

# Get diff against main (default) or specified base
git diff main...HEAD

# Or with custom base
git diff <base>...HEAD

# List changed files
git diff --name-only main...HEAD
```

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

---
name: pr-review
description: Comprehensive pull request review for projects in this workspace. Use when asked to review a PR, analyze code changes, or provide feedback on pull requests.
---

# PR Review Skill

Provides comprehensive pull request reviews following project coding standards.

## Usage

```
/pr-review <PR-URL-or-number> [--repo <repo-name>]
```

## Review Process

### 1. Fetch PR Details

Use the `gh` CLI to fetch PR details and diff:

```shell
# Get PR metadata
gh pr view <PR-number> --repo <owner/repo> --json title,body,author,baseRefName,headRefName,files

# Get full diff
gh pr diff <PR-number> --repo <owner/repo>
```

### 2. Apply Review Criteria

Reference `skills/review-criteria.md` for the complete review checklist, code standards, and output format.

### 3. Output Format

Use the standard output format from `skills/review-criteria.md` with:
- **Review-Type**: "PR Review"
- **Source**: PR URL
- **Author**: PR author from metadata
- **Branch**: `<headRefName> -> <baseRefName>`

### 4. Save Review

Save the review to `reviews/` directory (already exists) with filename `pr-review-<repo>-<number>.md` (example: `pr-review-fusilli-123.md`).

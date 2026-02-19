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

### 1. Fetch PR Branch and Get Diff

Fetch and checkout the PR branch locally using git, then collect diff:

```shell
# Navigate to the project directory
cd projects/<repo>

# Fetch the PR branch
git fetch origin pull/<PR-number>/head:pr-<PR-number>

# Checkout the PR branch
git checkout pr-<PR-number>

# View the diff against main
git diff main...HEAD

# List all changed files
git diff main...HEAD --name-only

# View commit history on this branch
git log main..HEAD --oneline
```

Read the changed files directly using the Read tool and use file-relative line numbers when referencing code.

After the review, stay on the PR branch for follow-up discussion. Do NOT switch back or delete it.

### 2. Review the Changes against Review Criteria

**CRITICAL**: Review the code referencing `skills/review-criteria.md` for the complete review checklist, code standards, and output format. Do not miss this step as otherwise the review is pointless.

### 3. Save Review

Use the standard output format from `skills/review-criteria.md` with:
- **Review-Type**: "PR Review"
- **Source**: PR URL
- **Author**: PR author from metadata
- **Branch**: `<headRefName> -> <baseRefName>`

Save the review to `<workspace_root>/reviews/` with filename `pr-review-<repo>-<number>.md` (example: `pr-review-fusilli-123.md`). If the file already exists, check if the PR / diff was updated since last review and re-review if so, saving to a file of the same name with a suffix `-take-N.md` for the Nth attempt.

**IMPORTANT**: Always save reviews to the top-level `claude-workspace/reviews/` directory, not within sub-project directories.

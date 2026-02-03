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

### 1. Fetch PR Branch

Fetch and checkout the PR branch locally using git:

```shell
# Record the current branch to return to later
ORIGINAL_BRANCH=$(git branch --show-current)

# Navigate to the project directory
cd projects/<repo>

# Fetch the PR branch
git fetch origin pull/<PR-number>/head:pr-<PR-number>

# Checkout the PR branch
git checkout pr-<PR-number>
```

### 2. Review the Code

With the PR branch checked out, you can:

```shell
# View the diff against main
git diff main...HEAD

# List all changed files
git diff main...HEAD --name-only

# View commit history on this branch
git log main..HEAD --oneline
```

Read the changed files directly using the Read tool with file-relative line numbers for any issues found.

### 3. Apply Review Criteria

Reference `skills/review-criteria.md` for the complete review checklist, code standards, and output format.

### 4. Output Format

Use the standard output format from `skills/review-criteria.md` with:
- **Review-Type**: "PR Review"
- **Source**: PR URL
- **Author**: PR author from metadata
- **Branch**: `<headRefName> -> <baseRefName>`

### 5. Save Review

Save the review to `reviews/` directory (already exists) with filename `pr-review-<repo>-<number>.md` (example: `pr-review-fusilli-123.md`). If the file already exists, check if the PR / diff was updated since last review and re-review if so, saving to a file of the same name with a suffix `-take-N.md` for the Nth attempt.

### 6. Cleanup

After the review is complete, switch back to the original branch and delete the PR branch:

```shell
# Switch back to the original branch
git checkout $ORIGINAL_BRANCH

# Delete the PR branch
git branch -D pr-<PR-number>
```

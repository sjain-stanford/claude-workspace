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

Use one of the following methods in order of preference:

#### Option A: `gh` CLI (preferred)

```shell
# Get PR metadata
gh pr view <PR-number> --repo <owner/repo> --json title,body,author,baseRefName,headRefName,files

# Get full diff
gh pr diff <PR-number> --repo <owner/repo>
```

#### Option B: `curl` fallback

Use when `gh` is unavailable or not authenticated:

```shell
# Get PR metadata (public repos, no auth needed)
curl -s "https://api.github.com/repos/<owner>/<repo>/pulls/<PR-number>"

# Get raw diff directly
curl -sL "https://github.com/<owner>/<repo>/pull/<PR-number>.diff"
```

For private repos, add authentication header:
```shell
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" "https://api.github.com/repos/<owner>/<repo>/pulls/<PR-number>"
```

#### Option C: WebFetch tool

For public repos, use Claude Code's WebFetch tool to fetch the raw diff:

```
WebFetch URL: https://github.com/<owner>/<repo>/pull/<PR-number>.diff
Prompt: "Extract the complete diff content"
```

**Note**: WebFetch will fail for private/authenticated URLs. Use `curl` with a token for private repos.

### 2. Apply Review Criteria

Reference `skills/review-criteria.md` for the complete review checklist, code standards, and output format.

### 3. Output Format

Use the standard output format from `skills/review-criteria.md` with:
- **Review-Type**: "PR Review"
- **Source**: PR URL
- **Author**: PR author from metadata
- **Branch**: `<headRefName> -> <baseRefName>`

### 4. Save Review

Save the review to `reviews/` directory (already exists) with filename `pr-review-<repo>-<number>.md` (example: `pr-review-fusilli-123.md`). If the file already exists, check if the PR / diff was updated since last review and re-review if so, saving to a file of the same name with a suffix `-take-N.md` for the Nth attempt.

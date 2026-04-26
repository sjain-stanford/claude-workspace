---
name: pr-create
description: Create a GitHub pull request for a sub-repo branch. Use when asked to create a PR, open a pull request, or submit changes for review.
---

# PR Create Skill

Creates GitHub pull requests following workspace conventions: succinct descriptions.

## Usage

```
/pr-create [--repo <repo-name>] [--base <base-branch>]
```

- `repo` (optional): Sub-repo name under `projects/`. Inferred from current context if omitted.
- `base` (optional): Base branch for the PR. Defaults to `main`.

## Process

Run git commands from the sub-repo directory or use `git -C projects/<repo> ...` from the workspace root. The `gh` CLI must be run from inside the sub-repo directory using `cd projects/<repo> && gh ...`.

### 1. Gather Information

Run these commands in parallel:

```bash
git -C projects/<repo> status -sb
git -C projects/<repo> log --oneline -5 --decorate
git -C projects/<repo> diff origin/main...HEAD
git -C projects/<repo> diff origin/main...HEAD --name-only
```

Verify:
- Branch is **not** `main` (must be on a feature branch)
- Branch has been **pushed** to remote (check for `origin/<branch>` in `--decorate` output, or push first)

### 2. Push if Needed

If the branch is not yet pushed or is ahead of remote:

```bash
cd projects/<repo> && git push -u origin HEAD
```

### 3. Draft PR Title and Description

**Title**: Use the same style as commit messages — concise, imperative mood, under 72 characters. For single-commit PRs, reuse the commit subject line.

**Description**: Keep it succinct but clear. Use the following template:

```markdown
## Summary

- <bullet 1: what changed and why>
- <bullet 2: additional context if needed>
```

**Rules**:
- Focus on *why*, not *what* — the diff shows what changed
- One to three bullets maximum
- Do NOT include a "Test Plan" section unless test coverage is not handled by CI (per workspace PR preferences)
- Do NOT include `Co-Authored-By` in the PR body — co-authorship is already tracked in commit messages

### 4. Create the PR

Use HEREDOC format for the body to preserve formatting:

```bash
cd projects/<repo> && gh pr create \
  --title "<title>" \
  --body "$(cat <<'EOF'
## Summary

- <bullet>
EOF
)"
```

To target a non-default base branch:

```bash
cd projects/<repo> && gh pr create \
  --base <base-branch> \
  --title "<title>" \
  --body "$(cat <<'EOF'
...
EOF
)"
```

### 5. Report

Return the PR URL to the user.

## Example

```bash
cd projects/docker && gh pr create \
  --title "Mount ~/.cursor into dev container for Cursor config access" \
  --body "$(cat <<'EOF'
## Summary

- Mount `~/.cursor` so Cursor IDE settings and MCP configs are accessible inside the dev container.
EOF
)"
```

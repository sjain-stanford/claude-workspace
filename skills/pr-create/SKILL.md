---
name: pr-create
description: Create a GitHub pull request for a sub-repo branch with PR-body agent attribution. Use when asked to create a PR, open a pull request, or submit changes for review.
---

# PR Create Skill

Creates GitHub pull requests following workspace conventions: compact prose descriptions with PR-body agent attribution.

## Usage

```
/pr-create [--repo <repo-name>] [--base <base-branch>]
```

- `repo` (optional): Sub-repo name under `projects/`. Inferred from current context if omitted.
- `base` (optional): Base branch for the PR. Infer the repository's target
  branch when omitted (`develop` for rocjitsu); do not assume `main`.

## Process

Run git and `gh` commands from the sub-repo directory.

### 1. Gather Information

Run these commands in parallel:

```bash
git status -sb
git log --oneline -5 --decorate
git diff origin/<base>...HEAD
git diff origin/<base>...HEAD --name-only
```

Verify:
- Branch is not the resolved base branch (must be on a feature branch)
- Branch has been **pushed** to remote (check for `origin/<branch>` in `--decorate` output, or push first)

### 2. Push if Needed

If the branch is not yet pushed or is ahead of remote:

```bash
cd projects/<repo> && git push -u origin HEAD
```

### 3. Draft PR Title and Description

**Title**: Use the same style as commit messages — concise, imperative mood, under 72 characters. For single-commit PRs, reuse the commit subject line.

**Description**: Use short prose paragraphs, no section headings by default.

```markdown
<One concise paragraph describing the primary change and why it matters.>

<Optional second concise paragraph for supporting changes, cleanup, or test adjustments.>

Co-authored-by: GPT-5.6 Sol <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
```

**Rules**:
- Focus on *why*, not *what* — the diff shows what changed
- Prefer one paragraph; use two paragraphs when there is a meaningful secondary change
- Do not use bullets or headings for normal PRs
- Keep each paragraph short and specific; avoid restating every changed file
- Do NOT include a "Test Plan" section unless test coverage is not handled by CI (per workspace PR preferences)
- Include this final PR-body attribution footer:
  ```markdown
  Co-authored-by: GPT-5.6 Sol <codex@openai.com>

  🤖 Generated with [Codex](https://openai.com/codex)
  ```
- For Claude Code, use:
  ```markdown
  Co-authored-by: Claude Opus 4.7 <noreply@anthropic.com>

  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  ```
- Do NOT include agent `Co-authored-by` trailers in individual commit messages

### 4. Create the PR

Use HEREDOC format for the body to preserve formatting:

```bash
cd projects/<repo> && gh pr create \
  --title "<title>" \
  --body "$(cat <<'EOF'
<One concise paragraph describing the primary change and why it matters.>

<Optional second concise paragraph for supporting changes, cleanup, or test adjustments.>

Co-authored-by: GPT-5.6 Sol <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
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
Mounts `~/.cursor` into the dev container so Cursor IDE settings and MCP configs are available inside the workspace.

Co-authored-by: GPT-5.6 Sol <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
EOF
)"
```

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
- `base` (optional): Base branch for the PR. Defaults to `main`.

## Process

Run git and `gh` commands from the sub-repo directory.

### 1. Gather Information

Run these commands in parallel:

```bash
git status -sb
git log --oneline -5 --decorate
git diff origin/main...HEAD
git diff origin/main...HEAD --name-only
```

Verify:
- Branch is **not** `main` (must be on a feature branch)
- Branch has been **pushed** to remote (check for `origin/<branch>` in `--decorate` output, or push first)

### 2. Push if Needed

If the branch is not yet pushed or is ahead of remote:

```bash
cd projects/<repo> && git push -u origin HEAD
```

### 3. Resolve Model Attribution

Resolve the active model name before drafting the PR body:

1. Read the active model identifier from the runtime or system context. Do not
   confuse it with a catalog of available model overrides.
2. Convert an identifier to its display name mechanically: uppercase `GPT`,
   preserve the version punctuation, and title-case a named suffix. For example,
   `gpt-5.6-sol` becomes `GPT-5.6 Sol`.
3. Record the resolved display name in a commentary update before creating the
   PR. If any active model identifier is available, do not replace it with the
   generic name `Codex`.
4. If the runtime and system context provide no active model identifier, ask the
   user to confirm the attribution before creating the PR. Use the generic name
   `Codex` only when the user explicitly chooses it. Do not infer the active
   model from the available-model catalog or from old PRs.

Immediately before `gh pr create`, inspect the final body and confirm that the
`Co-authored-by` line contains the resolved display name and no placeholder.

### 4. Draft PR Title and Description

**Title**: Use the same style as commit messages — concise, imperative mood, under 72 characters. For single-commit PRs, reuse the commit subject line.

**Description**: Use short prose paragraphs, no section headings by default.

```markdown
<One concise paragraph describing the primary change and why it matters.>

<Optional second concise paragraph for supporting changes, cleanup, or test adjustments.>

Co-authored-by: <active agent and model> <agent email>

🤖 Generated with [<active tool>](<active tool URL>)
```

**Rules**:
- Focus on *why*, not *what* — the diff shows what changed
- Prefer one paragraph; use two paragraphs when there is a meaningful secondary change
- Do not use bullets or headings for normal PRs
- Keep each paragraph short and specific; avoid restating every changed file
- Do NOT include a "Test Plan" section unless test coverage is not handled by CI (per workspace PR preferences)
- Include a final PR-body attribution footer for the active tool and model.
- For Codex, use the display name resolved in step 3:
  ```markdown
  Co-authored-by: <active Codex model display name> <codex@openai.com>

  🤖 Generated with [Codex](https://openai.com/codex)
  ```
- For Claude Code, use:
  ```markdown
  Co-authored-by: Claude Opus 4.7 <noreply@anthropic.com>

  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  ```
- Do NOT include agent `Co-authored-by` trailers in individual commit messages

### 5. Create the PR

Use HEREDOC format for the body to preserve formatting:

```bash
cd projects/<repo> && gh pr create \
  --title "<title>" \
  --body "$(cat <<'EOF'
<One concise paragraph describing the primary change and why it matters.>

<Optional second concise paragraph for supporting changes, cleanup, or test adjustments.>

Co-authored-by: <active agent and model> <agent email>

🤖 Generated with [<active tool>](<active tool URL>)
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

### 6. Report

Return the PR URL to the user.

## Example

```bash
cd projects/docker && gh pr create \
  --title "Mount ~/.cursor into dev container for Cursor config access" \
  --body "$(cat <<'EOF'
Mounts `~/.cursor` into the dev container so Cursor IDE settings and MCP configs are available inside the workspace.

Co-authored-by: <active Codex model display name> <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
EOF
)"
```

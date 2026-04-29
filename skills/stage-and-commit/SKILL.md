---
name: stage-and-commit
description: Stage and commit changes to the current branch with signed commits and co-authorship. Use when asked to commit, save changes, or create a commit.
---

# Stage and Commit Skill

Stages and commits changes following workspace conventions: signed commits with co-authorship attribution.

## Usage

```
/stage-and-commit [message]
```

- `message` (optional): Commit message. If not provided, the active agent will analyze changes and draft an appropriate message.

## Commit Rules

**CRITICAL**: These rules must always be followed:

1. **Signed commits**: Always use `git commit -s` to include `Signed-off-by` trailer
2. **Co-authorship**: Always include the active agent's co-author trailer:
   - Codex/OpenAI: `Co-Authored-By: GPT <model> <codex@openai.com>` (for example, `GPT 5.5`)
   - Claude/Anthropic: `Co-Authored-By: Claude <model> <noreply@anthropic.com>` (for example, `Claude Opus 4.6`)
3. **No push**: NEVER push to remote. Only commit locally. User must explicitly request push separately.
4. **Specific staging**: Prefer staging specific files by name over `git add -A` or `git add .`

## Process

Run git commands from the target repository directory.

### 1. Gather Information

Run these commands in parallel to understand the current state:

```bash
# See all changes (never use -uall flag)
git status

# See staged and unstaged changes
git diff
git diff --cached

# See recent commit messages for style reference
git log --oneline -5
```

### 2. Analyze and Draft Commit Message

- Summarize the nature of changes (new feature, enhancement, bug fix, refactor, test, docs, etc.)
- Use appropriate verbs: "add" for new features, "update" for enhancements, "fix" for bugs
- Keep the first line under 72 characters
- Focus on "why" rather than "what" when possible
- Follow the commit message style observed in recent commits

### 3. Stage Files

Stage relevant files by name. Avoid staging:
- Files containing secrets (`.env`, `credentials.json`, etc.)
- Large binaries
- Unrelated changes

```bash
git add <specific-files>
```

### 4. Create Commit

Use HEREDOC format to ensure proper formatting of multi-line commit messages:

```bash
git commit -s -m "$(cat <<'EOF'
<commit message>

Co-Authored-By: <active agent and model> <agent email>
EOF
)"
```

Replace the co-author trailer with the actual agent and model being used:
- Codex/OpenAI: `Co-Authored-By: GPT 5.5 <codex@openai.com>`
- Claude/Anthropic: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`

### 5. Verify

Run `git status` after commit to confirm success.

## Commit Message Format

```
<short description>

<optional body explaining why, not what>

Co-Authored-By: <active agent and model> <agent email>
Signed-off-by: <user name> <user email>
```

Do not add a type prefix such as `feat:`, `fix:`, `docs:`, or `chore:`
unless the user explicitly asks for one or the repository's recent history
overwhelmingly requires it.

## Example

```bash
git add skills/stage-and-commit/SKILL.md CLAUDE.md README.md
git commit -s -m "$(cat <<'EOF'
Add stage-and-commit skill for standardized commits

Introduces /stage-and-commit skill that enforces signed commits
and co-authorship attribution per workspace conventions.

Co-Authored-By: GPT 5.5 <codex@openai.com>
EOF
)"
```

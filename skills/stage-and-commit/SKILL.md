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

- `message` (optional): Commit message. If not provided, Claude will analyze changes and draft an appropriate message.

## Commit Rules

**CRITICAL**: These rules must always be followed:

1. **Signed commits**: Always use `git commit -s` to include `Signed-off-by` trailer
2. **Co-authorship**: Always include `Co-Authored-By: Claude <model> <noreply@anthropic.com>` trailer
3. **No push**: NEVER push to remote. Only commit locally. User must explicitly request push separately.
4. **Specific staging**: Prefer staging specific files by name over `git add -A` or `git add .`

## Process

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

Co-Authored-By: Claude <model> <noreply@anthropic.com>
EOF
)"
```

Replace `<model>` with the actual model name (e.g., `Opus 4.5`, `Sonnet 4`).

### 5. Verify

Run `git status` after commit to confirm success.

## Commit Message Format

```
<type>: <short description>

<optional body explaining why, not what>

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Signed-off-by: <user name> <user email>
```

**Types**: feat, fix, update, refactor, test, docs, chore

## Example

```bash
git add skills/stage-and-commit/SKILL.md CLAUDE.md README.md
git commit -s -m "$(cat <<'EOF'
feat: Add stage-and-commit skill for standardized commits

Introduces /stage-and-commit skill that enforces signed commits
and co-authorship attribution per workspace conventions.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

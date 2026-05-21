---
name: stage-and-commit
description: Stage and commit changes to the current branch with signed commits. Use when asked to commit, save changes, or create a commit.
---

# Stage and Commit Skill

Stages and commits changes following workspace conventions: signed commits only. Agent attribution is added to pull request descriptions, not individual commit messages.

## Usage

```
/stage-and-commit [message]
```

- `message` (optional): Commit message. If not provided, the active agent will analyze changes and draft an appropriate message.

## Commit Rules

**CRITICAL**: These rules must always be followed:

1. **Signed commits**: Always use `git commit -s` to include `Signed-off-by` trailer
2. **No commit co-authorship**: Do not include agent `Co-authored-by` trailers in commit messages. The PR creation workflow handles agent attribution in the pull request description.
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
- Include a concise body for every non-trivial commit. Do not leave the
  message as just a subject line plus sign-off.
- Use 2-3 short body lines to explain both why the change is needed and what
  behavior, workflow, or contract it changes.
- If the user provides only a terse phrase, expand it into a clear subject and
  body based on the staged diff while preserving the user's intent.
- Focus on "why" as well as "what"
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
EOF
)"
```

### 5. Verify

Run `git status` after commit to confirm success.

## Commit Message Format

```
<short description>

<body explaining why the change is needed and what it changes>

Signed-off-by: <user name> <user email>
```

Only omit the body for a truly tiny mechanical commit, such as a typo fix or
single-value metadata bump, and only when that matches the repository's recent
commit style.

Do not add a type prefix such as `feat:`, `fix:`, `docs:`, or `chore:`
unless the user explicitly asks for one or the repository's recent history
overwhelmingly requires it.

## Example

```bash
git add skills/stage-and-commit/SKILL.md CLAUDE.md README.md
git commit -s -m "$(cat <<'EOF'
Add stage-and-commit skill for standardized commits

Introduces /stage-and-commit skill that enforces signed commits
per workspace conventions.
EOF
)"
```

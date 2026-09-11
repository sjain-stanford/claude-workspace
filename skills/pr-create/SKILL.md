---
name: pr-create
description: Create a GitHub pull request for a sub-repo branch with a concise prose description and relevant validation. Use when asked to create a PR, open a pull request, or submit changes for review.
---

# PR Create Skill

Creates GitHub pull requests following workspace conventions: a few concise paragraphs with enough context for a reviewer to understand the change.

## Usage

```
/pr-create [--repo <repo-name>] [--base <base-branch>]
```

- `repo` (optional): Sub-repo name under `projects/`. Inferred from current context if omitted.
- `base` (optional): Base branch for the PR. Infer the repository's target
  branch when omitted (`develop` for rocjitsu); do not assume `main`.

## Process

Run git and `gh` commands from the branch-backed development worktree that
owns the change. For meta-workspace changes, use the active workspace checkout.
Do not return to the canonical sub-repo to push or create the PR.

### 1. Gather Information

Run these commands in parallel:

```bash
git status -sb
git log --oneline -5 --decorate
git diff <base-remote>/<base>...HEAD
git diff <base-remote>/<base>...HEAD --name-only
```

Verify:
- Branch is not the resolved base branch (must be on a feature branch)
- The diff and commits contain only the intended work. Confirm the PR's base
  repository and push remote, including when the branch lives in a fork.
- Determine whether the branch is published and whether the remote has the
  same commit as `HEAD`; a remote decoration in the last five commits is not
  sufficient to establish this.

### 2. Draft PR Title and Description

**Title**: Use the same style as commit messages — concise, imperative mood, under 72 characters. For single-commit PRs, reuse the commit subject line.

**Description**: Default to one to three short prose paragraphs, including
for non-trivial fixes and features. Use headings only when the user requests
them or the repository's template requires them. Prefer prose to bullet lists
for normal PRs.

Lead with the problem and the resulting behavior. Add a brief explanation of
the cause, design, or tradeoff when it helps a reviewer assess the change.
Include relevant validation and any material gaps in a short final paragraph
or sentence. A small change may fit in a single paragraph.

Keep only details that affect the review. Link existing issues or documentation
for longer investigations; omit the investigation chronology and file-by-file
changelogs. Include exact commands or environment details when needed to
reproduce the behavior, without listing every check performed. Describe only
validation actually run, distinguishing an equivalent reproducer from the
reported one when relevant.

Do not include a "Test Plan" section unless test coverage is not handled by
CI, per workspace PR preferences.

### 3. Publish the Prepared PR

Write the complete description to a temporary file with a quoted heredoc (or
use a structured tool argument). Review the title, body, diff, and commit
history before the remote write. In this workspace, verify that they contain
no material derived from `projects-emu/`.

```bash
PR_BODY=$(mktemp)
cat > "$PR_BODY" <<'EOF'
<Briefly explain the problem and resulting behavior.>

<Add only supporting context needed to assess the change, if any.>

<Summarize relevant validation and material gaps in a sentence or two.>
EOF
```

Combine or omit optional paragraphs as appropriate, and replace all
placeholders before publishing.

If the branch needs publishing, push from this same worktree within the user's
authorization and execution permissions:

```bash
git push -u <push-remote> HEAD
```

If a remote write is denied, stop remote mutations and report the denial with
the prepared title/body. Follow the workspace's no-bypass rule; do not try an
API, alternate tool, or different remote-write mechanism to evade it.

Once the intended commit is available remotely:

```bash
gh pr create --base <base-branch> --title "<title>" --body-file "$PR_BODY"
```

For a fork, pass `--repo <base-owner>/<repo>` and `--head <fork-owner>:<branch>`
when needed to identify the prepared change. Remove the temporary body file
when it is no longer needed.

### 4. Report

Return the PR URL to the user.

## Example

A typical PR body:

```markdown
Resolve the review diff against the PR's declared base branch so rocjitsu PRs
are reviewed against develop. Reuse the branch's development worktree for
follow-up fixes.

Checked the documented commands against the local worktree layout.
```

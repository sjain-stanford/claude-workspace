---
name: pr-create
description: Create a GitHub pull request for a sub-repo branch with a complexity-appropriate description, validation details, and PR-body agent attribution. Use when asked to create a PR, open a pull request, or submit changes for review.
---

# PR Create Skill

Creates GitHub pull requests following workspace conventions: evidence-backed descriptions with enough context for a reviewer to understand the change and PR-body agent attribution.

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

**Description**: Match the structure to the complexity of the change.

- For a small, self-explanatory PR such as a version bump, documentation edit,
  or narrow configuration change, use one to three short paragraphs without
  Markdown section headings. State why the change is needed, what it changes,
  and the validation performed. Use a compact `Validation:` line or list only
  when it improves readability.
- For a non-trivial fix or feature, use short Markdown sections so reviewers
  can follow the investigation and design. Cover the following points when
  applicable:

- **Provenance**: Link the originating issue, report, or request. State the base revision or environment used for investigation and distinguish pre-existing work from this PR when that history affects the diagnosis.
- **Reproducer**: Record the smallest meaningful reproducer, relevant hardware/software configuration, and the observed versus expected behavior. If the original reproducer was unavailable, say so and explain why the substitute exercises the same path.
- **Root cause**: Explain the failed mechanism and the evidence that isolated it. Do not merely restate the symptom.
- **Fix**: Describe the design and important invariants or tradeoffs, including why the approach is robust. Avoid a file-by-file changelog.
- **Validation**: List the commands, test groups, or end-to-end workloads actually run and their outcomes. Include test counts or exit behavior when useful, and disclose meaningful gaps.

Do not force provenance, reproduction, or root-cause sections onto a simple PR
when those concepts add no useful information. Never add empty or redundant
sections merely to match a template.

Simple PR format:

```markdown
<Why the change is needed and what it changes.>

Validation: <checks actually run and any meaningful gaps.>

Co-authored-by: <active Codex model> <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
```

Non-trivial PR format:

```markdown
## Context

<Originating issue/request, investigation baseline, and relevant prior work.>

## Reproduction

<Minimal reproducer or equivalent, environment, observed behavior, and expected behavior.>

## Root cause

<The failed mechanism and the evidence used to isolate it.>

## Fix

<The design, why it resolves the cause, and any important invariants.>

## Validation

<Tests and end-to-end checks actually run, with outcomes and any gaps.>

Co-authored-by: <active Codex model> <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
```

**Rules**:
- For a non-trivial change, focus on the causal chain: provenance and
  reproduction → root cause → fix → validation
- Use detail proportional to the change: a simple PR should make the motivation,
  change, and validation clear; a non-trivial PR should let a reviewer assess
  scope and reproduce the observed failure without rediscovering the investigation
- Prefer concrete evidence over generic claims such as "fixes the issue" or "tests pass"
- Keep sections focused and avoid restating every changed file
- Never claim the exact reported reproducer was run when only an equivalent path was tested
- Do NOT include a "Test Plan" section unless test coverage is not handled by CI (per workspace PR preferences)
- For Codex, use the active model display name supplied by the runtime or
  system context in the final PR-body footer. If the exact model variant is
  unavailable, use `Codex` instead of guessing. Do not copy a model version
  from a previous PR or template:
  ```markdown
  Co-authored-by: <active Codex model> <codex@openai.com>

  🤖 Generated with [Codex](https://openai.com/codex)
  ```
- For Claude Code, use:
  ```markdown
  Co-authored-by: <active Claude model> <noreply@anthropic.com>

  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  ```
- Do NOT include agent `Co-authored-by` trailers in individual commit messages

### 3. Publish the Prepared PR

Write the complete description to a temporary file with a quoted heredoc (or
use a structured tool argument). Review the title, body, diff, and commit
history before the remote write. In this workspace, verify that they contain
no material derived from `projects-emu/`.

```bash
PR_BODY=$(mktemp)
cat > "$PR_BODY" <<'EOF'
<Use concise prose for a simple PR or the sectioned format above for a
non-trivial PR. Replace all placeholders before publishing.>

Validation: <Checks actually run and their outcomes.>

Co-authored-by: <active Codex model> <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
EOF
```

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

A small PR body can be one paragraph plus validation and attribution:

```markdown
Resolve the review diff against the PR's declared base branch so rocjitsu PRs
are reviewed against develop. Reuse the branch's development worktree for
follow-up fixes.

Validation: checked the documented commands against the local worktree layout.

Co-authored-by: <active Codex model> <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
```

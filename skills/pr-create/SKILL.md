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

Co-authored-by: GPT-5.6 Sol <codex@openai.com>

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

Co-authored-by: GPT-5.6 Sol <codex@openai.com>

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
<Use concise prose for a simple PR or the sectioned format above for a
non-trivial PR.>

Validation: <Checks actually run and their outcomes.>

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
cd projects/rocm-systems && gh pr create \
  --base develop \
  --title "[rocjitsu] Route trap-handler queue exceptions" \
  --body "$(cat <<'EOF'
## Context

Fixes #1234. The failure was reproduced from the current `origin/develop` baseline; a related earlier change already modeled the architectural registers but did not connect the runtime notification path.

## Reproduction

Running the minimal device-assert workload on gfx1250 printed the assertion and then timed out instead of notifying the runtime and terminating.

## Root cause

The trap handler encoded the queue exception in M0, but the simulated KFD acknowledged the interrupt without forwarding those bits to the queue error event.

## Fix

Decode the runtime exception payload and defer delivery until the compute-unit wave lock is released, preserving the command processor's lock ordering.

## Validation

Added a focused gfx1250 regression and ran the affected KFD/debug suites plus the end-to-end device-assert workload. The runtime now reports the queue exception and terminates without timing out.

Co-authored-by: GPT-5.6 Sol <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
EOF
)"
```

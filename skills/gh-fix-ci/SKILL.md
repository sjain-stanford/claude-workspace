---
name: gh-fix-ci
description: Inspect and fix failing GitHub Actions PR checks using gh, logs, and focused local verification. For external checks (e.g., Buildkite), report the details URL without attempting provider-specific fixes.
metadata:
  short-description: Fix failing Github CI actions
---

# Gh Pr Checks Plan Fix

## Overview

Use gh to locate failing PR checks, fetch GitHub Actions logs, summarize the
cause, and implement the fix when the user requested it. A diagnosis-only or
plan-only request stops at that deliverable. Use the PR's development worktree
and the repository's contribution and verification guidance.

Run `gh auth status` for the target host with normal permissions first. Request
escalation only if the sandbox blocks network access. Distinguish authentication
failures from rate limits and network errors; only authentication failures
require the user to log in.

## Inputs

- `repo`: path inside the repo (default `.`)
- `pr`: PR number or URL (optional; defaults to current branch PR)
- `gh` authentication for the repo host

## Quick start

- `python "<path-to-skill>/scripts/inspect_pr_checks.py" --repo "." --pr "<number-or-url>"`
- Add `--json` if you want machine-friendly output for summarization.

## Workflow

1. Verify gh authentication.
   - Run `gh auth status` in the repo for the target host.
   - If sandboxed auth status fails, rerun the command with `sandbox_permissions=require_escalated` to allow network/keyring access.
   - If unauthenticated, ask the user to log in before proceeding.
2. Resolve the PR.
   - Prefer the current branch PR: `gh pr view --json number,url`.
   - If the user provides a PR number or URL, use that directly.
3. Inspect failing checks (GitHub Actions only).
   - Preferred: run the bundled script (handles gh field drift and job-log fallbacks):
     - `python "<path-to-skill>/scripts/inspect_pr_checks.py" --repo "." --pr "<number-or-url>"`
     - Add `--json` for machine-friendly output.
   - Manual fallback:
     - `gh pr checks <pr> --json name,state,bucket,link,startedAt,completedAt,workflow`
       - If a field is rejected, rerun with the available fields reported by `gh`.
     - For each failing check, extract the run id from `link` (or `detailsUrl`
       in legacy output) and run:
       - `gh run view <run_id> --json name,workflowName,conclusion,status,url,event,headBranch,headSha`
       - `gh run view <run_id> --log`
     - If the run log says it is still in progress, fetch job logs directly:
       - `gh api "/repos/<owner>/<repo>/actions/jobs/<job_id>/logs" > "<path>"`
4. Scope non-GitHub Actions checks.
   - If the check URL is not a GitHub Actions run, label it as external and only report the URL.
   - Do not attempt Buildkite or other providers; keep the workflow lean.
5. Summarize failures for the user.
   - Provide the failing check name, run URL (if any), and a concise log snippet.
   - Call out missing logs explicitly.
6. Create a plan.
   - State the proposed fix and verification. Save a plan under the workspace's
     `plans/` directory for non-trivial work; no separate `plan` skill is required.
7. Implement the requested fix.
   - Apply the fix within the user's authorized scope. Ask only for a material
     unresolved decision or an action outside that scope.
8. Recheck status.
   - Run the relevant local checks and summarize their results. Remote checks
     still describe the pushed commit until the fix is published; do not claim
     CI passed based only on local tests. Respect workspace remote-write rules.

## Bundled Resources

### scripts/inspect_pr_checks.py

Fetch failing PR checks, pull GitHub Actions logs, and extract a failure snippet. Exits non-zero when failures remain so it can be used in automation.

Usage examples:
- `python "<path-to-skill>/scripts/inspect_pr_checks.py" --repo "." --pr "123"`
- `python "<path-to-skill>/scripts/inspect_pr_checks.py" --repo "." --pr "https://github.com/org/repo/pull/123" --json`
- `python "<path-to-skill>/scripts/inspect_pr_checks.py" --repo "." --max-lines 200 --context 40`

Offline helper checks: `python3 -m pytest <path-to-skill>/tests`.

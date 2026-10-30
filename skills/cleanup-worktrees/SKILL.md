---
name: cleanup-worktrees
description: Remove unused task worktrees and retire peanut-review sessions for landed PRs and stale or abandoned work. Use for workspace housekeeping with configurable inactivity and a preview mode; preserve active work, local changes, and recoverable commits.
---

# Clean Up Worktrees and Review Sessions

Clean up task worktrees under `projects/worktrees/` and
`projects-emu/worktrees/`, plus inactive peanut-review session directories.
Resolve the workspace root from this skill's physical location under `skills/`.
Follow workspace instructions and read `LOCAL_CONTEXT.md` once if present.

## Invocation and scope

- `$cleanup-worktrees`: clean eligible worktrees and sessions; use 30 days as
  the inactivity cutoff for stale or abandoned work.
- `$cleanup-worktrees preview`: inventory and report proposed actions only.
- `$cleanup-worktrees older-than 60 days`: change the inactivity cutoff.
- `$cleanup-worktrees landed-only`: limit eligibility to confirmed merged PRs.

These are natural-language routing hints, not installed CLI commands. Honor
narrower repository, worktree, session, age, or keep-list choices. A full cleanup
invocation authorizes removing eligible idle worktrees and retiring their
sessions after preservation checks. Show the concrete candidate summary in
commentary and proceed; do not add a blanket confirmation step. Creating or
editing this skill does not authorize running cleanup.

Never remove canonical clones, shared Git directories, the current working
directory or its ancestors, locked worktrees, explicitly retained items, or
paths outside the selected cleanup roots. Task worktrees pinned to review
commits can qualify; being detached alone is neither proof of abandonment nor
an instruction to preserve the checkout forever.

## Discover and establish ownership

Discover canonical repositories afresh under `projects/` and `projects-emu/`,
excluding worktree, artifact, dependency-cache, and build directories. Use
`git worktree list --porcelain -z` in each canonical clone; do not infer worktree
ownership from directory names. Deduplicate by resolved common Git directory.
Do not remove unregistered directories as though they were Git worktrees.

Read [peanut session handling](references/peanut-sessions.md) before inspecting
sessions. Discover configured review roots and inventory sessions independently
of worktrees, including sessions whose checkout is already gone. Join them by
repository identity and resolved checkout path. All sessions sharing a worktree
must be checked before removing that checkout; an active session protects it.

For each candidate, record its path, repository, branch/HEAD, associated sessions
and local tasks, PR identity and state, most recent activity, disk usage, and
preservation needs. Use local task records to find ongoing ownership and any
explicit keep instruction, but do not close tasks merely because their checkout
is old or removed.

Match PRs using saved session metadata, task records, and exact repository/head
branch identity. Confirm state through read-only GitHub queries with the correct
host and existing account selection. Record the PR URL, state, `mergedAt`,
`closedAt`, `updatedAt`, head SHA and branch, and base branch. A missing remote
branch, old local ref, matching PR-number filename, or failed API request does
not prove that a PR landed or was abandoned. Do not switch global authentication.

## Classify eligibility

Apply active-use protections before age or PR status:

- Keep worktrees used by live agents, queued/running review jobs, builds, tests,
  shells, or other processes with working directories or open files there.
  Verify process identity, not just a saved PID. If access prevents checking
  relevant local or remote activity, mark the item uncertain and retain it.
- Keep work associated with a current task or explicit owner/keep instruction.
  An old task status alone is not proof of current use or abandonment; combine
  it with progress notes and runtime evidence.
- Keep worktrees with an ongoing merge, rebase, cherry-pick, revert, or bisect.
  Do not kill agents, stop shared services, cancel jobs, or unlock worktrees to
  make them eligible.

Use the latest meaningful activity across worktree creation/checkout and
reflogs, local source edits, task updates, session launches/comments/reports,
and PR updates. Inspect evidence before commands that refresh metadata. Commit
author dates and directory mtimes alone are insufficient; missing timestamps
mean unknown age. Do not count this cleanup's inspection as new activity.

| Classification | Eligibility when idle and preservation checks pass |
| --- | --- |
| Confirmed merged PR | Eligible immediately; no inactivity wait |
| Closed, unmerged PR | Eligible after the cutoff, or when explicitly declared abandoned |
| Open PR with no recent activity | Eligible after the cutoff when no current task or live owner depends on it; label stale, not merged |
| Local work without a PR | Eligible after the cutoff with evidence it is unused, or explicit abandonment |
| Unknown PR state, ownership, or activity | Retain and explain the missing evidence |

Eligibility applies separately to each session and worktree. Explicit
abandonment waives the age threshold, not active-use or data-preservation checks.

## Preserve work before removal

Inspect staged/unstaged changes, untracked files, ignored files, and nested
repositories/submodules. Keep dirty worktrees or those containing unclassified
local files; report the exact reason. Ignored does not mean disposable: identify
generated build/cache output separately from saved experiments, datasets,
configuration, credentials, or results. Remove rebuildable output only as part
of an otherwise eligible checkout. Do not use `git clean`, `reset --hard`, or a
blanket force-removal to overcome refusal.

Preserve local branches, including unmerged and unpushed history. Worktree
removal does not require branch deletion. For a detached HEAD not retained by
a surviving local branch/ref, create and verify a uniquely named local backup
branch following the workspace branch convention before removal. Reflogs and
remote-tracking refs alone are not durable preservation. Check worktree-local
reflogs for additional recovery tips that would become unreachable on removal
and retain them too. For squash/rebase merges, Git ancestry may not match the
landed PR: use the confirmed PR state for classification and keep the original
local history anyway.

Preserve linked sessions' reviewed Git objects in the surviving canonical
repository, and archive each retiring session as described in the reference.
Failure to verify a required archive or Git object blocks that item; continue
with independent candidates.

Write a recovery manifest containing paths, branch/commit mappings, eligibility
evidence, session archives/checksums, and exact restore instructions. Keep it
and archives in a gitignored run directory under
`projects-emu/artifacts/worktree-cleanup/`; this also keeps mixed public/private
results local. Do not embed real inventories or private details in tracked
instructions or public artifacts. Preview mode must not create backup refs,
repair sessions, fetch, archive, remove files, or alter cleanup targets.

## Apply and verify

Recheck ownership, process/queue activity, HEAD, and local changes immediately
before each removal. Skip items that changed since inspection. Run from the
surviving canonical repository, with an exact inventoried absolute path:

```bash
git worktree remove -- "$worktree_path"
```

Use normal Git removal without `--force`. A refusal is a reason to inspect and
retain the item, not to fall back to recursive deletion. Resolve and validate
path containment component by component; reject symlink substitutions and do
not traverse nested mounts or repositories when deleting artifacts.

Retire verified session directories independently when their own eligibility
and archival checks pass. Do not delete entire session roots, queue state, or
shared configuration. Missing-directory registrations are a separate repair:
preview `git worktree prune --dry-run --verbose` and prune only if every proposed
entry is confirmed abandoned and no unavailable mount or locked path explains
its absence. Otherwise leave registrations alone; never prune indiscriminately.

Verify removed checkouts are absent from both disk and `git worktree list`;
retired sessions are absent from live roots and their archives verify. Confirm
canonical/default branches, retained worktrees, local history, and retained
review snapshots still resolve. Keep recovery branches and session-retention
refs; do not prune them or expire archives as part of ordinary cleanup.

Report each removed, retired, retained, or failed item with the reason, plus
total disk space reclaimed net of archives. Do not call archived bytes freed.
Include recovery locations and preservation refs. Update local task handoff
notes when paths changed and flush task-tracker state at session end. Do not
publish review state, close PRs, delete remote branches, or push anything.

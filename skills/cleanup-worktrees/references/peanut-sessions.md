# Peanut-review session retirement

This workflow manages whole session directories; it does not curate comments
or run a review. Do not launch reviewers or curators for housekeeping. Consult
the workspace [peanut-review skill](../../peanut-review/SKILL.md) for lifecycle
context, and verify current behavior against the local CLI before using it.

## Inventory and activity

Resolve `reviewRoot` from `.cache/peanut-review/.peanut-review.json` and any
explicit additional roots used by the running UI. The usual root is
`.cache/peanut-review/sessions/`, but use actual configuration. Enumerate real
session directories containing `session.json`; shared configuration, `.queue/`,
server PID files, and parent roots are not sessions. Do not assume a missing
worktree means its saved review should be deleted.

Use `workspace` plus `repo_relative` for the execution repository,
`git_common_dir` for durable Git storage, and `workspace_branch` for the saved
branch. Saved GitHub metadata carries repository, PR, host, and account identity;
preserve that identity when checking remote PR state.

The current tool has no separate session lifecycle status. `round-done`, a
verdict, or a stale `AgentConfig.status` does not establish that a session is
idle. Inspect signals, `log/<agent>/meta.json`, process/supervisor identities,
SSH launch state where applicable, and queue jobs. In the current
`review_queue.py`, `queued`, `preparing`, `reviewing`, and `curating` are active
job states. Uncertain runtime ownership protects the session and its worktree.

For preview, read metadata and inspect runtime without refreshing it:
`peanut-review status` calls `refresh_agent_statuses` and may write session
metadata. Do not instantiate a queue object just to inspect its files; its
constructor can retire recorded jobs. Read queue state as data and inspect the
running server/processes. Do not cancel jobs or restart the shared UI for cleanup.

## Retain Git objects

Before removing a checkout needed by a retained or archived session, ensure its
recorded base, topic, original head, current head, and earlier retained revisions
remain readable through the surviving repository. The supported repair is:

```bash
"$PR_BIN" --session "$session_path" retain-git --repo "$canonical_repo"
```

Use the workspace `tools/peanut-review/bin/peanut-review` as `PR_BIN`. This repair
writes session metadata and Git refs, so run it only during apply and while
idle, before making the final archive. Verify all recorded commits resolve.

The tool retains reviewed commits under `refs/peanut-review/`. These refs survive
session-directory deletion and should remain for archived sessions. They are
cumulative across revisions; do not guess their namespace from a session name
or delete refs merely because no live directory matches. See
`retain_review_git` in `tools/peanut-review/peanut_review/session.py` when needed.

## Archive, remove from the live root, and restore

`peanut-review archive` only appends comments to Git notes; it neither removes
the session nor preserves all session data. It is not the backup for cleanup.
The current CLI has no whole-session delete command; verify this against the
installed CLI before deciding how to retire a directory.

Create a complete compressed archive of each eligible idle session outside all
live review roots, under the cleanup run directory specified in `SKILL.md`.
Preserve relative paths, metadata, comments including deleted/history records,
verdicts, notes, signals, prompts, logs, and other session files. Preserve symlinks
as links without traversing them; retain or separately preserve any external
target the session needs. Record original path and durable Git storage in the
manifest. Never overwrite an existing archive.

Before removing the live session, verify the archive by reading it back and
comparing its entries, contents/checksums, and required metadata with the source.
Recheck that the source and runtime state did not change during archival.
Retain the source on verification failure or concurrent activity. Remove only
the exact verified session directory; reject root paths, symlink substitutions,
and nested mounts. Do not hand-edit shared queue state to hide old entries.

Verify the remaining sessions are still discoverable. Record restoration steps:
extract the verified archive back to its original session path without replacing
an existing directory; use `git worktree add` with the preserved local branch
to restore a removed checkout when execution is needed. Saved diffs can remain
readable through `git_common_dir` without restoring the checkout. Archived data
and retained Git refs remain local; permanent purge requires a separate explicit
request and a fresh check for dependencies.

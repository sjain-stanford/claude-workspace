---
name: sync-repos
description: Fetch origin default branches across this workspace's canonical clones and fast-forward their local default branches, excluding task and pinned worktrees. Use for bulk repository refreshes; supports fetch-only requests.
---

# Sync Repositories

Refresh canonical clones under `projects/` and `projects-emu/`, then report each
repository's outcome. Resolve the workspace root from this skill's physical
location under `skills/`, even when invoked from a sub-repo or worktree. Follow
the workspace instructions and read `LOCAL_CONTEXT.md` once if present.

## Invocation

- `$sync-repos`: fetch and fast-forward local default branches in both roots.
- `$sync-repos fetch-only`: fetch remote-tracking default branches only.
- `$sync-repos projects only`: limit the full refresh to `projects/`.

Honor explicit scope and mode overrides. A request to fetch alone does not
authorize local branch updates. Invoking the full refresh authorizes updating
the canonical clones directly; do not create implementation worktrees for this
maintenance. Update default branches only, not every local branch.

## Discover and inspect

Discover clones afresh on every run; do not reuse a saved inventory. Walk the
requested roots and organization directories, excluding `worktrees/`,
`.worktrees/`, Git internals, artifact directories, dependency caches, and build
outputs. Avoid following symlinks outside the selected roots or into excluded
directories. Deduplicate clones by their resolved Git common directory.

Use `git rev-parse --absolute-git-dir` and
`git rev-parse --path-format=absolute --git-common-dir` to distinguish canonical
clones from linked worktrees: unequal resolved paths indicate a linked
worktree, which must be skipped. Do not treat a `.git` file alone as proof of a
canonical clone. Do not create missing clones or repair stale worktree entries.

Run Git commands from each repository's directory. Read applicable repository
instructions. Use the existing `origin` configuration without changing remote
URLs or authentication. If `origin` is absent, report the repository as skipped.
Identify the actual default branch with:

```bash
git ls-remote --symref origin HEAD
```

Parse the `ref: refs/heads/<branch>` entry. Do not assume `main`, `master`, the
checked-out branch, or a cached `origin/HEAD` is correct. If discovery fails,
report that repository and continue with the others.

Record the default branch's local and remote-tracking SHAs, all local branch
refs, and `git worktree list --porcelain` before mutation. Inspect the current
branch, `git status --porcelain=v1 --untracked-files=normal`, and any ongoing
merge, rebase, cherry-pick, revert, or bisect before a local update.

## Fetch

Fetch only the discovered default branch, explicitly updating its remote-tracking
ref. The variables below stand for validated discovery results:

```bash
git fetch --no-tags --no-recurse-submodules --no-auto-maintenance origin \
  "+refs/heads/${default_branch}:refs/remotes/origin/${default_branch}"
```

The leading `+` allows the remote-tracking ref to reflect upstream rewrites;
it does not authorize rewriting a local branch. Do not prune unrelated refs,
fetch submodules, or push. Avoid interactive authentication prompts in bulk
commands; report authentication failures without changing credentials.

Record the fetched SHA and whether the remote-tracking branch advanced, was
rewritten, was newly created, or was already current. If fetching fails, skip
the local update for that repository. In fetch-only mode, proceed to verification
and reporting without moving local branches or checked-out files.

## Update local default branches

Compare each local default branch to the successfully fetched SHA. Use
`git rev-list --left-right --count <local-sha>...<fetched-sha>` to distinguish
behind, ahead, and diverged histories. If any Git operation is in progress,
skip local updates for that repository.

- Equal SHAs: report already current, even if unrelated local files are dirty.
- Local-only commits: preserve them; report ahead or diverged and skip the update.
- Behind only: update using the rules below.
- No local default branch: create a tracking branch only when no Git operation
  is in progress; leave the current checkout unchanged.

For a default branch checked out in the canonical clone, require a clean status
and no Git operation in progress. Recheck the branch, HEAD, and status immediately
before updating; if they changed since inspection, skip the repository. Apply
the exact fetched commit with:

```bash
git -c submodule.recurse=false merge --ff-only --no-autostash --no-edit \
  --no-overwrite-ignore --no-stat "$fetched_sha"
```

If the default branch is checked out in any other worktree, skip its local
update. If it is checked out nowhere, verify that the saved local SHA is an
ancestor of the fetched SHA, recheck worktree ownership, and update only that
ref with a compare-and-swap operation:

```bash
git update-ref "refs/heads/${default_branch}" "$fetched_sha" "$local_sha"
```

Do not switch a canonical clone from a different branch or detached HEAD.
Do not reset, rebase, stash, clean, discard changes, or create merge commits to
make an update succeed. Preserve dirty or conflicted repositories and continue
with independent repositories; report what prevented each skipped update.

## Verify and report

Verify updated local branches equal their fetched tips and only the intended
default-branch refs moved. Confirm linked worktrees' HEADs and branches are
unchanged, and that existing local changes remain intact. Remember that fetched
remote-tracking refs are shared with linked worktrees even though their HEADs
and files stay pinned.

Report totals and a table grouped by workspace root: repository, default branch,
fetch result, and local update result when applicable. Include commit counts
for advances and concise reasons for skips or failures. Distinguish commits
newly fetched from commits advanced locally; these counts can differ. Make clear
whether local checkouts were updated or only fetched, and whether pinned
worktrees were preserved.

Keep internal repository names, paths, logs, and results out of tracked files
and public artifacts. If a durable report is useful, use a gitignored local
destination under `projects-emu/` for results involving that root. Do not embed
a repository inventory in this skill. Follow the workspace's local task-tracking
and session-end sync requirements; this workflow does not require a commit or PR.

---
name: peanut-review
description: Orchestrate structured multi-agent code review for local changes or GitHub PRs using the peanut-review CLI, and curate existing peanut-review sessions. Use when starting or managing review sessions, or when asked to deduplicate, shorten, validate, dismiss, filter, or decide whether agent review comments are worth pushing.
---

# Peanut Review

You are the orchestrator for a structured multi-agent review. Drive the review
lifecycle with `tools/peanut-review/bin/peanut-review`; it sets `PYTHONPATH`
for the local checkout, so no install step is needed.

## Remote Publishing Requires Explicit Authorization

Never push comments, approvals, request-changes verdicts, replies, edits, or
any other review state to GitHub unless the user explicitly asks to publish or
push it. A request to run, start, perform, or complete a review—including
`/peanut-review pr ...`—authorizes local review work and a push dry-run only;
it does not authorize `gh-push` or `gh-push-verdict`.

For GitHub PR reviews, prepare and curate a push-ready comment set, run
`gh-push --dry-run`, report exactly what would be published, and stop. If the
user later explicitly asks to push, rerun the dry-run against current session
state immediately before publishing.

## Subcommands

Codex skills do not have a separate subcommand registry. Treat the first word
after `/peanut-review` as a routing hint when present:

- `/peanut-review curate <session-or-pr-context>`: clean up an existing review
  session's comments, using the dedicated curator agent when appropriate.
  This is not a new reviewer pass.
- `/peanut-review pr <PR URL>`: run the GitHub PR review lifecycle below.
- `/peanut-review local <base-ref>`: run the author-owned local review
  lifecycle below.
- `/peanut-review status <session-path>`: inspect or recover a session without
  changing comments unless asked.

For `curate`, start from the live session data and produce a push-ready,
author-facing comment set:

- Resolve the live session path and source checkout. If the current directory
  is a wrapper, read `.peanut-review.json` first and keep `reviewRoot`,
  `workspaceRoot`, and `repoRelative` separate.
- Inspect `comments --format json` before editing. Also inspect
  `comments --include-deleted --format json` when duplicate cleanup, prior
  deletions, or mistaken cleanup might matter.
- Bucket local agent comments into keep/rewrite, merge, delete, or undelete.
  Leave imported GitHub comments alone unless the discussion is actually
  resolved or the user asks you to manage it.
- Validate likely survivors against exact files, generated artifacts, or the
  smallest useful repro/test. Spend verification time on comments that might
  survive, not on likely deletes.
- Rewrite kept comments as concise PR feedback. Start with the requested change
  or scoped question, include only compact evidence, and align severity with
  confidence. Avoid internal triage wording such as "confirmed" or "partly
  confirmed".
- Delete duplicate, incorrect, stale, nitpicky, speculative, praise-only,
  overly broad, or low-ROI comments. When merging duplicates, edit the kept
  comment first so it absorbs any useful detail, then delete the redundant
  copy. Preserve disposition history: never delete a resolved comment, a
  reply, or a thread root that has replies. Deletion is only for comments that
  have not become part of a reply/resolution trail; if such a comment was
  deleted by mistake, undelete it before replying to or resolving it. When a
  later review round adds a substantive new finding or rebuttal to a resolved
  thread, unresolve the thread before adding the reply and leave it unresolved
  until the renewed concern is addressed and resolved again.
- For GitHub-backed sessions, finish with `gh-push --dry-run`. Treat it as
  authoritative for what will surface and whether anchors are pushable. If an
  anchor is out of range, recreate the finding as a global comment preserving
  the original `file:line`, then delete the stale anchored copy.

Do not launch or rerun reviewers, patch source, or push to GitHub during
`curate` unless the user explicitly asks. Launching the dedicated curator
agent is allowed when the user asks for curation or when a GitHub review
lifecycle reaches the automatic curation step.

## Operator Checklist

Track these items explicitly. If your harness has a todo list, create this list
before running commands and keep it current.

- [ ] Choose one lifecycle: GitHub PR review or local author-owned review.
- [ ] Record the session path, source workspace, any separate build/tool root,
      base/topic refs or PR number, and configured reviewers.
- [ ] Ask for external facts/preferences that are not discoverable: review
      root, web UI root, repo layout, build/test command, session reuse/archive
      choice, persona lineup, runner, and model choices.
- [ ] Confirm the checkout is built/testable and reviewer-visible tools are
      reachable before launching reviewers.
- [ ] Confirm project config and reviewer permissions are valid.
- [ ] Launch reviewers and verify startup with `status`, logs, and
      `wait-all`.
- [ ] Inspect failed runs and non-review agent reports promptly.
- [ ] Track the last reviewed comment id for later `--since` queries.
- [ ] Triage every finding: keep, delete, resolve, or reply locally; publish
      only with explicit user authorization.
- [ ] Finish with the right artifact: a push-ready GitHub dry-run for PRs, or
      a local verdict/archive for author-owned reviews. Push only when the user
      explicitly asks.

Mode-specific checklist:

- [ ] GitHub PR: select or create the branch-backed development worktree under
      `projects/worktrees/<repo>/` and use it for both review and iteration.
- [ ] GitHub PR: prefer `start --no-launch`, build/test, then `launch`, unless
      the user says the checkout is already built.
- [ ] GitHub PR: after all reviewers signal `round-done`, let `wait-all`
      launch and wait for the `Curator` agent by default; use `--no-curate`
      only when you intentionally want to skip this.
- [ ] GitHub PR: inspect the curated feedback; do not fix code, resolve
      imported GitHub threads, or force rebuttal loops unless the user asks.
- [ ] GitHub PR: always finish with `gh-push --dry-run` and stop unless the
      user explicitly asked to publish the review.
- [ ] Local review: own the patch and run the iterative development loop below.
      Review and curate, triage every surviving finding, commit relevant fixes,
      migrate anchors, reply or resolve addressed comments, and refresh the
      same session until the curator leaves no actionable comments.

## Ask Before Guessing

Use project config and discoverable local facts first. If a choice affects
where session data is written, which checkout is reviewed, or which paid/local
model runner is used, and the answer is not already in the repo or user
request, ask a concise question instead of inventing it. Do not ask for facts
you can cheaply read from config files or CLI discovery.

If the lifecycle is unclear, ask: "Is this a local author-owned review, or a
GitHub PR review?"

## Working Variables

Set these descriptive names in an operator scratchpad or shell snippets:

```bash
PR_BIN=tools/peanut-review/bin/peanut-review
SESSION=<session-path>
WORKSPACE=<source-workspace>
REVIEW_ROOT=<configured-review-root>
LAST_COMMENT_ID=<last-reviewed-comment-id>
```

Examples assume `PR_BIN` and the intended `SESSION` path are set.
Name new GitHub PR sessions `<repo>-pr-<number>-<change-title>`, using the PR
head branch or title for `change-title`. Development worktrees keep their
task-oriented names under `projects/worktrees/<repo>/`; a session name does
not require a matching worktree leaf. Keep descriptive suffixes and avoid bare
PR-number names.

## Config And Permissions

When `.peanut-review.json` exists, use it as-is. In this workspace, use the
shared config at `.cache/peanut-review/.peanut-review.json`, run from the
branch-backed development worktree under `projects/worktrees/<repo>/`, and
store `<repo>-pr-<number>-<change>` sessions under
`.cache/peanut-review/sessions/`. The config defines
`reviewRoot`, `workspaceRoot`, `repoRelative`, `reviewAgentTimeoutSeconds`, and
the exact `agents` lineup. Point the web UI at the same `reviewRoot`. If no
config exists, ask before choosing persistent roots, repo layout, reviewers,
runners, or models.

`peanut-review start` consumes an existing checkout; it does not create a
worktree. For a GitHub-backed PR session, reuse the branch-backed development
worktree that owns the change. If one does not exist, create a normal task
worktree under `projects/worktrees/<repo>/` and use it for both review and
subsequent development. Do not create a detached or review-only worktree under
`.cache/peanut-review/`. Run only the following `git worktree add` commands from
the `claude-workspace` root. When the local PR branch already exists and is not
checked out elsewhere, use:

```bash
git -C projects/<repo> worktree add \
  ../worktrees/<repo>/<task>-<change> \
  <local-pr-branch>
```

When the PR branch exists only as a remote-tracking branch, explicitly create
and track a local branch:

```bash
git -C projects/<repo> worktree add \
  --track -b <local-pr-branch> \
  ../worktrees/<repo>/<task>-<change> \
  <remote>/<remote-pr-branch>
```

After selecting or creating the worktree, run every `peanut-review start`
command from inside that worktree because the shared config uses `$PWD` as its
workspace. Capture absolute paths before changing directories so the workspace
tool and shared config remain reachable:

```bash
META_WORKSPACE="$PWD"
PR_BIN="$META_WORKSPACE/tools/peanut-review/bin/peanut-review"
CONFIG="$META_WORKSPACE/.cache/peanut-review/.peanut-review.json"
WORKTREE="$META_WORKSPACE/projects/worktrees/<repo>/<task>-<change>"

cd "$WORKTREE"
"$PR_BIN" start <pr> --config "$CONFIG" --dry-run --no-launch
```

Verify that the committed `HEAD` is the intended review snapshot before
launch. Preserve local modifications and never reset or clean the development
worktree as part of review setup or synchronization. Peanut-review pins commit
ranges, so commit intended review changes first or use the local author-owned
lifecycle for work that is not yet represented by the PR snapshot.

For GitHub PR sessions, the config must include a dedicated curator agent in
`agents`, for example `{"name":"Curator","model":"gpt-5.5-high",
"runner":"cursor","role":"curator"}`. The curator uses a dedicated prompt, so
do not invent a `curator.md` persona. Do not rely on a Python default for the
curator model; missing curator config should fail before launch. Add the same
entry for local sessions when the web UI curator button or `curate` command
should be available.

Do not blur roots. `reviewRoot` is session storage/web UI data;
`workspaceRoot` + `repoRelative` identify the checkout under review. If build
outputs or project tools live outside the source checkout, make sure the actual
runner workspace and permissions let agents reach them before launch.

When root/layout changed or is ambiguous, dry-run before spending reviewer
runs:

```bash
"$PR_BIN" start <pr> --config <config> --dry-run --no-launch
"$PR_BIN" start <pr> --config <config> --no-launch
SESSION=<printed-session-path>
"$PR_BIN" --session "$SESSION" launch --dry-run
```

Cursor agents need `.cursor/cli.json` in the actual runner workspace shown by
`launch --dry-run`.

```bash
mkdir -p "$WORKSPACE/.cursor"
cp tools/peanut-review/peanut_review/templates/cli.sample.json "$WORKSPACE/.cursor/cli.json"
```

The launch command validates config and Cursor permissions. Keep
`Shell(peanut-review **)` allowed, and keep `Shell(**)` out of the deny list
because it overrides all Shell allows.

When build tools live outside the runner workspace, Cursor permissions must
also allow the paths or commands reviewers are expected to use.

## GitHub PR Review

Use this for PR numbers, PR URLs, or external author changes. Import GitHub
context, run reviewers, curate findings, and prepare a push-ready preview.
Publish comments or an approve/request-changes decision only when the user
explicitly asks.

1. Select the PR's branch-backed development worktree described above and run
   from inside it. Verify that its committed `HEAD` is the intended snapshot;
   preserve any uncommitted work.

2. Start without launching unless the checkout is already built. The command
   imports existing GitHub context and prints the session path.

   ```bash
   "$PR_BIN" start <pr-number-or-url> --no-launch
   SESSION=<printed-session-path>
   ```

3. Build/test the checkout with the project workflow. If reviewers need
   non-obvious tool paths, make them available through the runner workspace
   or rendered prompt before launch; do not use Agent reports as setup chat.

4. Launch reviewers and wait for the first pass plus automatic curation:

   ```bash
   "$PR_BIN" --session "$SESSION" launch
   "$PR_BIN" --session "$SESSION" wait-all round-done --timeout 900
   ```

5. Inspect the curator's result. Delete duplicate/noisy local comments with
   `delete <c_id>` if anything remains. Add replies only when they clarify a
   finding for the PR author. Do not resolve imported GitHub comments unless
   the GitHub discussion was actually resolved or the user asks you to manage
   it.

   ```bash
   "$PR_BIN" --session "$SESSION" gh-pull
   "$PR_BIN" --session "$SESSION" comments
   "$PR_BIN" --session "$SESSION" comments --since "$LAST_COMMENT_ID"
   ```

6. Add one top-level verdict comment when there is an overall conclusion:

   ```bash
   "$PR_BIN" --session "$SESSION" add-global-comment --category request-changes --body "Blocking issue: ..."
   "$PR_BIN" --session "$SESSION" add-global-comment --category approve --body "LGTM"
   ```

   Use `--category comment` or omit `--category` for non-verdict feedback. For
   self-owned PRs, GitHub may reject approve/request-changes events; use a
   normal global comment in that case.

7. Preview the review payload:

   ```bash
   "$PR_BIN" --session "$SESSION" gh-push --dry-run
   ```

   Stop after the dry-run and show the user what would be published. Do not
   infer push permission from a request to review a PR, run
   `/peanut-review pr`, complete the lifecycle, or produce a verdict.

8. Only when the user explicitly asks to publish or push the review, rerun the
   dry-run and then push:

   ```bash
   "$PR_BIN" --session "$SESSION" gh-push --dry-run
   "$PR_BIN" --session "$SESSION" gh-push
   ```

   Treat `gh-push-verdict` the same way: never run it without explicit user
   authorization to publish the verdict.

After author updates have been committed and pushed through the authorized
normal development workflow in the same worktree, run `sync-pr` and `gh-pull`.
Never reset or clean the worktree to refresh a session. Rerun reviewers only
for substantial updates or a human request.

```bash
"$PR_BIN" --session "$SESSION" sync-pr
"$PR_BIN" --session "$SESSION" gh-pull
```

## Local Author-Owned Review

Use this when the orchestrator can modify and commit the patch under review.
The stopping condition is a completed curator pass with no remaining actionable
curated findings. A clean reviewer pass without a completed curator pass is not
enough.

### Iterative Local Development Loop

1. Create the session. If project config exists, reuse its complete `agents`
   lineup, including its dedicated curator. If no curator is configured, ask
   before changing the lineup.

   ```bash
   "$PR_BIN" --session "$SESSION" init \
     --workspace "$WORKSPACE" \
     --base <base-ref> \
     --topic HEAD \
     --agents '<agents-json-or-file>'
   ```

2. Run the configured reviewers, wait for them to finish, then run the
   configured curator and wait for its `round-done` signal. Local sessions do
   not launch the curator automatically. Inspect the curated unresolved
   comments, including the curator report and deleted comments when needed to
   understand the result.

   ```bash
   "$PR_BIN" --session "$SESSION" launch
   "$PR_BIN" --session "$SESSION" wait-all round-done --timeout 900
   "$PR_BIN" --session "$SESSION" curate
   "$PR_BIN" --session "$SESSION" status
   "$PR_BIN" --session "$SESSION" comments --unresolved --format json
   ```

   Use `status`, signals, logs, and reports to confirm the curator completed;
   `wait-all` waits for reviewers only in a local session. If the curator leaves
   no actionable comments, continue to step 5.

3. Triage every curated finding; do not silently skip any. Apply real fixes and
   run proportionate verification. For findings that should not be fixed, add a
   concrete local rebuttal explaining the disposition. Review the resulting
   diff. When code changed, stage only relevant paths and commit the iteration
   locally using the project's commit workflow. Do not create empty commits and
   do not push.

4. After the commit, migrate the session to the new `HEAD` so comment anchors
   follow the updated snapshot. Then reply to and resolve comments addressed by
   the commit; keep genuinely outstanding comments unresolved. Do not delete
   addressed comments after resolving them: the comment, its commit reply, and
   any other replies are the iteration's audit trail. On later curator passes,
   preserve every resolved comment, every reply, and every thread root with
   replies even when the finding is now stale or duplicated by a new comment.
   If a later reviewer finds that a resolved concern still applies, that
   reviewer must `unresolve <c_id>` before replying on the existing thread.
   Keep the reopened thread unresolved until the new concern has been fixed or
   rebutted and explicitly resolved again. The curator must unresolve it as a
   safety net if a reviewer adds an actionable reply without doing so.
   Refresh the review by rerunning every configured reviewer in the same
   session, wait for the reviewer round, and run the curator again. Repeat from
   step 2 until the curator leaves no actionable findings. Here, "refresh"
   means `migrate` plus a full configured-reviewer rerun and curator pass; there
   is no `refresh` CLI subcommand.

   ```bash
   "$PR_BIN" --session "$SESSION" migrate
   "$PR_BIN" --session "$SESSION" add-comment --reply-to <c_id> --body "Addressed in <commit>: ..."
   "$PR_BIN" --session "$SESSION" resolve <c_id>
   "$PR_BIN" --session "$SESSION" rerun \
     --agent <reviewer-1> --agent <reviewer-2>
   "$PR_BIN" --session "$SESSION" wait-all round-done --timeout 900
   "$PR_BIN" --session "$SESSION" curate
   "$PR_BIN" --session "$SESSION" comments --since "$LAST_COMMENT_ID"
   ```

   List every configured reviewer with a repeated `--agent`; do not rerun the
   curator through `rerun`. Track each round's starting comment id and use
   `--since <comment-id>` to isolate new feedback. There is no round counter.

5. At the clean stopping point, inspect and analyze the complete change set
   from the session base through the final `HEAD`, not only the last iteration.
   Run any final project verification warranted by that aggregate diff and
   record the final verdict. A verdict writes `result.json` but does not close
   the session or prevent later reruns.

   ```bash
   "$PR_BIN" --session "$SESSION" verdict --approve --body "All critical issues addressed"
   "$PR_BIN" --session "$SESSION" verdict --request-changes --body "Outstanding critical issue in X"
   ```

   Summarize the complete result and local commits, then stop so the user has a
   chance to push them through the normal development workflow. Do not push on
   the user's behalf unless separately authorized. If the branch has a PR,
   offer to update its title and description after the user confirms the remote
   contains the final commits. Re-read the pushed PR and complete diff before
   proposing metadata, and update remote PR metadata only with explicit user
   authorization.

## Shared Review Mechanics

After any launch, monitor reports, rerun failed reviewers, and stop stale
processes through the CLI:

```bash
"$PR_BIN" --session "$SESSION" status
"$PR_BIN" --session "$SESSION" wait-all round-done --timeout 900
"$PR_BIN" --session "$SESSION" comments
"$PR_BIN" --session "$SESSION" launch --agent Irene
"$PR_BIN" --session "$SESSION" rerun --agent Irene
"$PR_BIN" --session "$SESSION" kill-agents
"$PR_BIN" --session "$SESSION" kill-agents --agent Irene
```

Use `status` for a compact view, but treat signal files, comments, reports, logs,
and live processes as the real health checks. `process=...` is supervisor-owned
runtime status; `review=done` means the agent posted `round-done`. There is no
separate session lifecycle state: web progress is derived from reviewer and
Curator runtime status, and an optional verdict is stored independently.

The authoritative reviewer prompt is
`tools/peanut-review/peanut_review/templates/agent-prompt.md`; do not maintain
a second skill-local copy. It tells agents to signal `round-done` and exit. The
supervisor should stop a lingering process shortly after observing that signal.
Use `kill-agents` only when `status` shows stale live processes, a launch needs
to be aborted, or the user explicitly asks.

There is no interactive agent help channel. If a reviewer is blocked, it may
record one `Review Blocked` report and exit without `round-done`; inspect the
runner log/report, fix the environment, then rerun it. Review discussion stays
in comments and anchored comment replies.

## Reviewer Selection

Use configured reviewers as-is during a review. When authoring config, ask
before changing persistent roots, runners, personas, or models. If asked to
choose a lineup, include Vera, one domain expert suited to the patch, and two
or three breadth reviewers such as Felix, Petra, or Soren. Map `tier: expert`
personas to the strongest available model and
`tier: standard` to a balanced/fast model. Discover models with
`cursor-agent --list-models` or `opencode models`; common Codex ids are
`gpt-5.5-high`, `gpt-5.5`, `gpt-5.4`, and `gpt-5.3-codex`.

Use display-case agent names in config, e.g. `Vera`, while keeping persona
filenames lowercase, e.g. `vera.md`. The web UI shows the configured agent
name.

## Web UI

The web UI reads the same session storage as the CLI. Its `--root` should match
the configured `reviewRoot`; without `--root`, it uses `$PEANUT_SESSION`'s
parent if set, otherwise `/tmp/peanut-review`.

If the user says the review server is already up, discover its root from the
running `peanut_review serve --root ...` process and use that for session
storage instead of starting a new server or guessing a different root.

```bash
"$PR_BIN" serve --root "$REVIEW_ROOT" --host 0.0.0.0 --port 27183
"$PR_BIN" stop --root "$REVIEW_ROOT"
```

Use `--host 0.0.0.0` when serving from Docker through a published port. For a
direct connection, leave `--base-url` unset and open the server root. Set a
base URL only behind a reverse proxy that strips the same prefix before
forwarding requests.

## Runners

- **cursor**: `cursor-agent --print` through Shell/CLI, not MCP; isolated
  runtime home under `<session>/runtime/cursor/`.
- **opencode**: `opencode run`; model ids are `provider/model`, including
  `openai/*`, `opencode/*`, or local `llama.cpp/*`.
- **codex**: `codex exec`; requires `codex login` and gets
  `--add-dir <session>` so it can write session files. Set per-agent
  `"fastMode": true` to enable Codex fast mode. It defaults to `false`.

Agents submit findings, comment replies, non-review reports, and completion
signals with peanut-review CLI commands from the rendered prompt. The `note`
channel is only for reports such as test execution and comment curation; notes
are not pushed to GitHub.

## Failure Handling

- If an agent times out, inspect `status` and `<session>/log/`.
- If an agent exits without `round-done`, treat it as failed or incomplete and
  use `rerun --agent <name>` after confirming no live reviewer remains.
- If a session was launched under bad assumptions, prefer archiving it and
  starting fresh over reusing stale signals/comments.
- If the orchestrator crashes, run `status`, then resume from the latest
  comments, reports, logs, and signals.

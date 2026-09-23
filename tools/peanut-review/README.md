# peanut-review

Structured code review for humans and agents, with a CLI, JSONL session data,
and a browser UI.

## TL;DR

Run from this checkout:

```bash
PEANUT_REVIEW_DIR=$PWD
PR_BIN=$PEANUT_REVIEW_DIR/bin/peanut-review
"$PR_BIN" --help
```

Use `peanut-review` instead of `$PR_BIN` if it is installed on `PATH`.
Most flows run from the repo being reviewed, so keep `PR_BIN` absolute.

In `claude-workspace`, use `skills/peanut-review/` to orchestrate multi-agent
review sessions and `tools/peanut-review/bin/peanut-review` as the CLI.

### GitHub accounts

One web server can publish reviews using several accounts, including accounts
on the same GitHub host. Each GitHub session saves its hostname, login, and
verified user ID. Authenticate each account with `gh auth login`, then select
an account when creating a session:

```bash
"$PR_BIN" start https://github.com/owner/repo/pull/123 --gh-account work-login --no-launch
```

Alternatively, set a default in the checkout being reviewed:

```bash
git config --local peanut-review.githubAccount work-login
```

Git `includeIf` configuration is supported, so different checkout directories
can have different defaults. The explicit `--gh-account` flag takes precedence.
The saved session identity is used for `start --reuse`, `sync-pr`, imports,
comments, replies, edits, and verdicts, even if the repository default changes.
A bare PR number is resolved from the checkout's `origin` remote locally. Use a
full PR URL for a different target repository, or `--gh-host` to specify the
actual GitHub hostname when origin uses an SSH alias.

Bind an existing session explicitly before using its GitHub operations:

```bash
"$PR_BIN" --session /path/to/session gh-auth --account work-login
"$PR_BIN" --session /path/to/session gh-auth
```

The first command verifies the account and PR access before saving a binding;
the second verifies the saved identity. Bound sessions cannot be reassigned to
a different account; create a new session when a different author is needed.
Existing local review data remains readable without a binding.

For a second account on the same PR, provide a unique `--id` so the new session
does not collide with the existing session's generated name:

```bash
"$PR_BIN" start https://github.com/owner/repo/pull/123 \
  --gh-account public-login --id repo-pr-123-public-login --no-launch
```

To reuse that session later, pass the same `--id` with `--reuse`, or select its
path with `--session`. Session IDs must also differ when separate repositories
or hosts would otherwise generate the same name.

For each operation, peanut-review retrieves the selected account's stored token
with `gh auth token --hostname HOST --user LOGIN`, verifies it with `gh api user`,
and uses that same token for every request in the operation. It overrides
inherited token/host settings only in those subprocesses, without changing the
active `gh` account or the server environment. Tokens stay in memory and child
process environments; they are never saved to sessions or sent to the browser.
The server must be able to access the selected accounts in its gh credential
store. If credentials expire or disappear, authenticate that account again;
peanut-review never falls back to the active account.

Both CLI dry-runs and the web publish preview show the verified account and
target. The web server revalidates credentials on submission and rejects a
changed account or target. Missing bindings, unavailable credentials, and an
unexpected login or user ID block publishing. Updating the server to this
version requires restarting it from the updated tool checkout.

## Web UI

Start the server from this tool checkout:

```bash
bin/peanut_review_serve.sh
```

Defaults: `root=$HOME/reviews`, `port=27183`, and a root-mounted UI. The
launcher binds to `0.0.0.0` in Docker and `127.0.0.1` otherwise. Open
`http://127.0.0.1:27183/` through the Docker/SSH port forwarding path.

The shared `claude-workspace` configuration stores sessions under
`.cache/peanut-review/sessions/`. Start its UI from the workspace root with the
same root explicitly selected:

```bash
PR_ROOT="$PWD/.cache/peanut-review/sessions" \
  tools/peanut-review/bin/peanut_review_serve.sh
```

Keep `PR_ROOT` aligned with the config's `reviewRoot`; otherwise the CLI and UI
will show different session sets. If `<PR_ROOT>/.queue/config.json` exists, the
server automatically enables the review queue using that local configuration.
An explicit `--queue-config` selects a different file. To reach the UI through the development
container, enable its forwarding when launching the container:

```bash
DOCKER_ENABLE_PEANUT_REVIEW_WEB=1 ./projects/docker/run_docker.sh
```

The Docker launcher's `init_docker.sh` publishes port `27183` only on the SSH
host's loopback when this option is enabled, so VSCode Remote SSH can forward
it without exposing the UI externally. When attached directly to the container,
you can instead forward its port through the editor's Ports panel. Set
`PR_HOST` or `PR_PORT` only to override the normal bind or port. Set
`PR_BASE_URL` only when a reverse proxy removes that same path prefix before
forwarding requests.

### Optional browser profiling

The runtime has no browser dependency. For repeatable local performance
measurements, install Playwright in a disposable virtual environment and run
the optional profiler against either the direct server or the Caddy mount:

```bash
python -m venv /tmp/peanut-review-profiler
/tmp/peanut-review-profiler/bin/pip install playwright
/tmp/peanut-review-profiler/bin/playwright install chromium

/tmp/peanut-review-profiler/bin/python scripts/profile_web.py \
  --url http://127.0.0.1:27183/example-session/ \
  --url http://127.0.0.1:27182/pr/example-session/ \
  --runs 3 --output /tmp/peanut-review-profile.json
```

The JSON report records medians plus every run: response start,
DOMContentLoaded, main-thread task, layout and style time, long tasks,
transferred bytes, DOM shape, bottom-scroll cost, and steady-state polling
bytes and CPU. Compare medians from the same machine, browser build, server
mount, session snapshot, and run count.

## Copy/Paste Prompts

First-time project setup:

```text
Help me set up peanut-review for this repo. Inspect the checkout/worktree
layout, ask before choosing reviewRoot, workspaceRoot, repoRelative, reviewers,
runners, models, or build/test commands, then generate .peanut-review.json and
run dry-run validation. Do not launch reviewers yet.
```

GitHub PR orchestration:

```text
Set up peanut-review for <PR URL> under <review-root>. Use the existing
.peanut-review.json, confirm the exact reviewer lineup and runner/model choices
before launching. Reuse the PR's branch-backed development worktree under
projects/worktrees, creating one there if needed, then start with --no-launch
so I can build/test the checkout. Do not create a separate detached review
worktree. After reviewers signal round-done, wait-all should run the curator;
help me inspect the curated feedback for the web UI push flow.
```

Local author-owned review:

```text
Run a local peanut-review session for the current branch under <review-root>.
Use base <base-ref>, topic HEAD, and the configured reviewers. Launch reviewers,
triage every finding, apply fixes, migrate comment anchors, and run one rebuttal
round if useful.
```

Update an existing GitHub-backed session:

```text
Update peanut-review session <SESSION> after the PR changed. Update or recreate
the branch-backed development worktree through the normal development flow,
then run sync-pr and gh-pull and show new/unresolved comments. Preserve local
changes rather than discarding them. Do not create a separate detached review
worktree or launch agents unless the update is substantial or I explicitly
ask.
```

After `.peanut-review.json` exists, future PR/session setup is a good task to
delegate to a subagent. Keep the first setup interactive so roots, permissions,
reviewers, and model choices are intentional.

## Project Config

Outside a preconfigured workspace, GitHub PR flow usually starts from a
`.peanut-review.json` in the worktree parent or repo:

```json
{
  "reviewRoot": "$HOME/reviews",
  "workspaceRoot": "$HOME/src",
  "repoRelative": "my-repo",
  "reviewAgentTimeoutSeconds": 1200,
  "agents": [
    {"name": "Vera", "model": "gpt-5.5", "reasoningEffort": "high", "fastMode": false, "persona": "vera.md", "runner": "codex"},
    {"name": "Irene", "model": "claude-opus-4-7-thinking-medium", "persona": "irene.md", "runner": "cursor"},
    {"name": "Curator", "model": "gpt-5.5-high", "runner": "cursor", "role": "curator"}
  ]
}
```

In `claude-workspace`, do not create another repository-local config. Use the
shared `.cache/peanut-review/.peanut-review.json`; it resolves the reviewed
repository from the current working directory and stores sessions under
`.cache/peanut-review/sessions/`. Name GitHub sessions
`<repo>-pr-<number>-<change>`. Because the shared config is outside development
worktrees, pass its absolute path with `--config`.

Supported runners: `cursor`, `opencode`, `codex`.
Codex agents accept an optional per-agent `fastMode` boolean. It defaults to
`false`; set it to `true` to enable Codex fast mode for a specific agent.
GitHub PR sessions require a configured agent with `"role": "curator"` because
the curator model is intentionally owned by project config, not by Python
defaults.

Cursor runners need permissions in the reviewed workspace before `launch`:

```bash
mkdir -p "$WORKSPACE/.cursor"
cp "$PEANUT_REVIEW_DIR/peanut_review/templates/cli.sample.json" \
  "$WORKSPACE/.cursor/cli.json"
```

Selected reviewer agents can instead use an existing persistent SSH
ControlMaster, an independent remote checkout/build tree, and a reverse-forwarded
capability gateway while retaining the same reviewer CLI. Curator, web, and
GitHub operations remain local. See [SSH reviewers](docs/ssh-reviewers.md) for
the configuration, security boundary, lifecycle, and real localhost validation.

### Prompt context

Every GitHub-backed reviewer and curator prompt includes the saved PR title,
full description, repository/number, and URL. This also applies to custom
templates, reruns, automatic curation, and SSH reviewers. Author-supplied text
is marked as review context whose claims need verification.

`start` and `init --gh-pr` capture this metadata. `sync-pr` or
`start --reuse --sync` refresh it, including description-only changes. Launching
agents renders the saved metadata without fetching GitHub. Older sessions show
that the description was not captured until synchronized; an empty GitHub
description is identified separately. Local sessions without a PR omit this
section. Existing prompt files and running agents are unchanged until the next
launch or rerun.

The default reviewer prompt also includes workspace/repository paths and layout,
detected build directories, compilation database and venv paths, diff commands,
and a command to read the copied persona file. It tells reviewers to load prior
comments/rebuttals, post structured findings, run relevant tests and report them,
and signal completion. The default curator prompt includes workspace/repository
paths, the reviewer lineup and curation baseline, commands to read visible and
deleted comments and preview GitHub publication, and rules for validating,
deduplicating, rewriting, and reporting curation decisions.

Diffs, source files, persona contents, and comment history are read by the agents
using those commands; they are not embedded in the prompt. Agent reports/notes
are not automatically included or requested. Custom templates replace the role
instructions; the launcher still appends PR metadata and optional local context.
Rendered prompts are saved in `<session>/prompts/<Agent>.md`.

### Local reference context

Put optional local instructions and reference routing in `LOCAL_CONTEXT.md` at
the enclosing workspace root. This workspace's `.gitignore` excludes the file.
The launcher finds it directly in the runner workspace or its parents; no
separate path setting is needed. The nearest file wins, and an empty file
disables inherited context for that subtree.

Each local reviewer and curator prompt receives the resolved absolute path and
an instruction to read it once and follow its routing to relevant references.
This applies to custom templates, reruns, and automatic curation; existing
sessions discover the current file on their next launch. Reference contents stay
in their original files. Follow their routing and private-material handling rules.

Missing context does not block launch; an unreadable nearest file disables
context for that subtree. SSH reviewer prompts omit local context paths.
Use `launch --dry-run` or `curate --dry-run` while the selected agents are idle
to inspect the rendered prompts.

## Flow: GitHub PR

Use this for changes that came from GitHub.

In `claude-workspace`, run from the branch-backed development worktree under
`projects/worktrees/<repo>/` that owns the PR. Reuse that worktree for review
and subsequent fixes; do not create a detached review checkout under
`.cache/peanut-review/`. Before launching reviewers, confirm committed `HEAD`
is the intended snapshot and preserve any uncommitted work.

```bash
PR=https://github.com/owner/repo/pull/123
CONFIG=<path-to-.peanut-review.json>

# Run inside the target checkout. Config discovery walks upward from cwd.
# Keep --config when the selected config is outside the checkout.

# Update an existing PR worktree without discarding local changes.
gh pr co "$PR"

"$PR_BIN" start "$PR" --config "$CONFIG" --no-launch
SESSION=<printed-session-path>

# Build/test the checkout with the repo's normal commands.

"$PR_BIN" --session "$SESSION" launch --dry-run
"$PR_BIN" --session "$SESSION" launch
"$PR_BIN" --session "$SESSION" wait-all round-done --timeout 900
```

For GitHub-backed sessions, `wait-all round-done` waits for reviewers, then
launches the dedicated `Curator` agent and waits for it to finish. Inspect the
curated result in the web UI, then use the UI's GitHub push modal when ready:

```bash
"$PR_BIN" --session "$SESSION" gh-pull
"$PR_BIN" --session "$SESSION" comments --unresolved
"$PR_BIN" --session "$SESSION" edit c_1234abcd --body-file /tmp/comment.md
"$PR_BIN" --session "$SESSION" delete c_9999ffff
```

The web UI also exposes manual **curate** and **rerun all** controls in the
Agents section when you need to rerun comment curation or start a fresh
reviewer pass.

## Flow: Local Branch

Use this when you own the patch and want reviewers to find issues before you
ship it.

```bash
REVIEW_ROOT=$HOME/reviews
SESSION=$REVIEW_ROOT/my-repo-my-branch
WORKSPACE=$PWD
AGENTS='[
  {"name":"Vera","model":"gpt-5.5","persona":"vera.md","runner":"codex"},
  {"name":"Irene","model":"claude-opus-4-7-thinking-medium","persona":"irene.md","runner":"cursor"},
  {"name":"Curator","model":"gpt-5.5-high","runner":"cursor","role":"curator"}
]'

"$PR_BIN" --session "$SESSION" init \
  --workspace "$WORKSPACE" \
  --base origin/main \
  --topic HEAD \
  --agents "$AGENTS"

"$PR_BIN" --session "$SESSION" launch --dry-run
"$PR_BIN" --session "$SESSION" launch
"$PR_BIN" --session "$SESSION" wait-all round-done --timeout 900
"$PR_BIN" --session "$SESSION" comments --unresolved
```

Local sessions do not run the curator automatically. If you want comment
cleanup before fixing the patch, use the web UI's **curate** button or:

```bash
"$PR_BIN" --session "$SESSION" curate
```

After fixing code:

```bash
"$PR_BIN" --session "$SESSION" comments --unresolved
COMMENT_ID=c_1234abcd

"$PR_BIN" --session "$SESSION" resolve "$COMMENT_ID"
"$PR_BIN" --session "$SESSION" migrate
"$PR_BIN" --session "$SESSION" rerun --agent Vera --agent Irene
"$PR_BIN" --session "$SESSION" wait-all round-done --timeout 900
"$PR_BIN" --session "$SESSION" verdict --approve --body "All critical issues addressed"
```

## Flow: PR Updated

Use this after the author pushes a new revision.

```bash
# First update the branch-backed checkout. Preserve local changes and resolve
# divergence through the normal development workflow rather than force-resetting.
gh pr co "$PR"

"$PR_BIN" --session "$SESSION" sync-pr
"$PR_BIN" --session "$SESSION" gh-pull
"$PR_BIN" --session "$SESSION" comments --since "$LAST_COMMENT_ID"
```

Session base/head refs are stored as commit SHAs. Opening the web UI never
retargets them: if the checkout has moved, the page reports that the workspace
differs until `sync-pr` (GitHub sessions) or `migrate` (local sessions) is run
explicitly. Agent launch/rerun is refused for a GitHub session while its
workspace is checked out at a different commit.

Rerun agents only for substantial changes. Use `rerun`, not `launch`, so stale
round signals are cleared before the selected reviewers start:

```bash
"$PR_BIN" --session "$SESSION" rerun --agent Vera --agent Irene
"$PR_BIN" --session "$SESSION" wait-all round-done --timeout 900
```

## Common Commands

```bash
"$PR_BIN" --session "$SESSION" status
"$PR_BIN" --session "$SESSION" note --message "Ran targeted tests; passed."
"$PR_BIN" --session "$SESSION" add-comment --file path/to/file.py --line 42 --severity warning --body-file /tmp/body.md
"$PR_BIN" --session "$SESSION" comments --unresolved   # use this to find c_... ids
"$PR_BIN" --session "$SESSION" curate                 # launch the comment curator
"$PR_BIN" --session "$SESSION" add-global-comment --severity suggestion --body "A few comments."
"$PR_BIN" --session "$SESSION" add-global-comment --category request-changes --body-file /tmp/blocking.md
"$PR_BIN" --session "$SESSION" add-comment --reply-to <global-comment-id> --body "Response"
```

Replies to anchored comments remain in their GitHub thread. Because GitHub
does not support threading review-level comments, replying to a global comment
creates a new global comment that quotes the original body as a Markdown
blockquote before the response.

`note` is a report-only channel for non-review output such as test execution
and comment curation. Review findings and discussion belong in comments.
Review progress is derived from reviewer and Curator runtime status. Sessions
do not have a separate lifecycle state: `round-done` records an agent's
completion, while `result.json` records an optional verdict without preventing
later reruns.
There is no interactive agent help channel: blocked reviewers record a
`Review Blocked` report when possible, exit without `round-done`, and are
rerun after the environment is fixed. Comment-thread replies remain available
through `add-comment --reply-to`.

## Review queue

The **Review queue** tab discovers open PRs requested from each configured
GitHub account, including team requests. It shares the existing server and
session pages. Started reviews and existing account-bound sessions remain
tracked when their review request disappears; closed PRs are available through
**Include closed PRs**. Account failures retain cached rows and show an error.

Filter by **Team request**, **Direct request**, or **Following** alongside the
account, search, and review-status filters. **Following** shows tracked PRs
without an active review request.

Keep the queue configuration local and gitignored. Save it as
`<primary-session-root>/.queue/config.json` to load it automatically with the
normal web launcher, or select another file with `--queue-config`.
Credentials are read from `gh auth` at operation time; never put tokens in this
file. For example:

```json
{
  "pollSeconds": 120,
  "accounts": [
    {
      "hostname": "github.com",
      "login": "my-public-login",
      "label": "Public",
      "cloneRoot": "/home/me/work/public",
      "worktreeRoot": "/home/me/work/worktrees/public",
      "reviewConfig": "/home/me/work/.peanut-review.json",
      "repositories": {
        "example/project": {
          "path": "/home/me/work/public/project",
          "worktreeRoot": "/home/me/work/worktrees/project",
          "prepare": [["cmake", "--build", "build"]]
        }
      }
    },
    {
      "hostname": "github.com",
      "login": "my-work-login",
      "label": "Work",
      "cloneRoot": "/home/me/work/private",
      "worktreeRoot": "/home/me/work/private-worktrees",
      "reviewConfig": "/home/me/work/.peanut-review.json"
    }
  ]
}
```

Paths may be absolute or relative to the queue config, and support `~` and
environment variables. `repositories` provides optional per-repository
settings; unmapped repositories use `<cloneRoot>/<owner>/<repo>` and
`<worktreeRoot>/<owner>/<repo>`. These paths are included in the copied driver
task. The driver handles clone/worktree setup and discovers any missing settings.

`prepare` is an optional list of command argument arrays included as setup
context in the copied task. The driver follows project build/test instructions
and decides how to prepare the checkout. The queue never executes these commands.
New reviews use the selected review config's agents; existing sessions retain
their saved lineup, models, and runners.

```bash
peanut-review serve --host 127.0.0.1 --port 27183 \
  --root /home/me/work/review-sessions \
  --queue-config /home/me/work/queue.local.json
```

Open `http://localhost:27183/queue`. The queue uses a loopback bind on the host.
Inside Docker, the normal launcher's `0.0.0.0` bind is supported with the
container port published on host loopback as described above. Restart the
existing server from the updated checkout after changing its startup
configuration; a server started in another container does not replace the
instance reached by your forwarded port. Remote access can use an SSH
localhost port forward. A stripped proxy prefix is still
supported through `--base-url`. The browser polls local cached status every
three seconds; GitHub is polled at `pollSeconds` (minimum 30). **Refresh queue**
requests a remote poll and never starts reviewers. Search results are paginated;
GitHub's incomplete-search response or 1,000-result cap is reported as an error
rather than silently dropping requests.

**Copy review task** and **Copy re-review task** copy a task for your driver
conversation. It includes the PR URL, selected GitHub account, review config,
session root, existing session/workspace, configured checkout paths, and observed
revision. If clipboard access is unavailable, a dialog provides selectable text.
The driver uses the peanut-review skill and CLI to fetch the latest revision,
preserve local work, reconcile force pushes or divergent branches, prepare the
build, run reviewers and the curator, and produce a publication dry-run. Copying
a task does not launch agents, change a checkout, or publish to GitHub.

The queue automatically discovers CLI-created sessions under its session roots.
Progress and the **Running reviews** filter reflect session agent activity;
historical queue job failures do not override current driver progress.
**Open review** opens the existing session. The old queue start endpoint is
retired; reload any browser tab still showing execution buttons.

Freshness compares the remote head, base commit and base branch with the last
completed reviewer-and-curator round. Each CLI launch records its pinned
snapshot and unique run IDs in the session's `review-completion.json`.
Supervisors record completion only after fresh completion signals and successful
exits (including supervised shutdown after completion). All configured reviewers
and a subsequent curator covering those runs must complete against the same
snapshot. This also works when the dashboard is stopped. A push during a review
leaves the completed result stale; fetching or synchronizing alone cannot mark
it reviewed. Stale polling or an API failure produces **Unknown**.

Older recorded queue completions remain valid. Legacy sessions containing only
completion signals cannot prove which revision was reviewed and remain
**Not reviewed** (or **Stale** when their pinned revision differs) until a full
round is recorded with the updated launcher. Synchronize legacy PR metadata
before that round to capture the base branch name as well as its commit.

Queue metadata is stored beneath `<primary-session-root>/.queue/` with restricted
file permissions. Keep that root private when combining accounts. Only the
configured account identities are exposed, and GitHub operations never switch
the globally active `gh` account. Queue actions require a token supplied by the
local page and reject cross-origin submissions.

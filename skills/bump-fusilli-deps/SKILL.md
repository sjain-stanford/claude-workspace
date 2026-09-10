---
name: bump-fusilli-deps
description: Bump IREE and TheRock nightly versions for the archived Fusilli project. Use only when the user explicitly requests Fusilli dependency maintenance.
---

# Bump Fusilli Dependencies Skill

Fusilli is archival in this workspace. Do not run this workflow as part of
rocjitsu or general ROCm dependency work.

Bumps IREE and TheRock to the latest nightly versions in the fusilli repository.
Each dependency gets its own branch and PR to isolate failures and simplify bisection.
Also used for **Docker image updates** when system packages change (which is rare
and separate from IREE/TheRock version bumps).

## Usage

```
/bump-fusilli-deps
```

**Autonomy**: Execute this workflow autonomously. Only ask the user for help if you encounter errors or blockers (e.g., version not found, workflow failed, permission denied, build failures). Otherwise, proceed through all steps automatically.

## Prerequisites

- `gh` CLI must be authenticated (`gh auth login`)
- User must have write access to the fusilli repo
- For docker image updates: write access to the docker repo as well

## Agent Attribution

Use the active agent's identity in generated PR footers only. Do not add agent co-authorship trailers to individual commit messages.

For Codex, use GPT-6 Astra in the PR attribution footer:
```markdown
Co-authored-by: GPT-6 Astra <codex@openai.com>

🤖 Generated with [Codex](https://openai.com/codex)
```

For Claude Code, use:
```markdown
Co-authored-by: <active Claude model> <noreply@anthropic.com>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Architecture

Version management uses `version.json` as the single source of truth:
- `iree-version`: IREE version string (e.g., `3.11.0rc20260217`) — note: no `iree-` prefix; consumers prepend it
- `therock-version`: TheRock nightly tag (e.g., `7.12.0a20260217`)

The CI script `exec_docker_ci.sh` reads versions from `version.json` and passes them
as environment variables to the Docker container, overriding the defaults baked into
the image's `entrypoint.sh`. This decouples version bumps from Docker image rebuilds.

## Workflow: Version Bump (Fusilli Only)

This is the common case — bumping IREE and/or TheRock versions. Each dependency gets its own branch and PR to isolate failures and simplify bisection.

### Phase 0: Pre-flight Checks

1. **Check `gh` auth**: `gh auth status`
2. **Read current versions** from `projects/fusilli/version.json`
3. **Inspect existing work**: run `git status` and `git worktree list` in the
   Fusilli repo. Preserve unrelated changes and use a separate task worktree
   for each dependency bump.

### Phase 1: Find Latest Versions

Run in parallel:

**IREE** — Use the git refs/tags API (NOT the releases API, which may not list recent rc tags):
```bash
gh api 'repos/iree-org/iree/git/refs/tags' --jq '.[].ref' --paginate 2>&1 \
  | grep 'rc' | sort -V | tail -1 | sed 's|refs/tags/iree-||'
```

> **WARNING**: Do NOT use `gh api repos/iree-org/iree/releases` — the releases API
> returns only formally published releases, which may be months behind the latest
> nightly rc tags. Always use the git tags API.

**Verify IREE wheel availability** — The git tag can exist before the pip wheel is uploaded:
```bash
curl -sL https://iree.dev/pip-release-links.html | grep -q "iree_base_compiler-${IREE_VERSION}" \
  && echo "OK: iree-base-compiler ${IREE_VERSION} is available" \
  || echo "MISSING: iree-base-compiler ${IREE_VERSION} is NOT available"
```
If the wheel is **not available**:
- Report the missing version to the user and **stop the IREE portion of the workflow**.
- Suggest trying again later or falling back to the most recent version that has wheels:
  ```bash
  curl -sL https://iree.dev/pip-release-links.html \
    | grep -oP 'iree_base_compiler-\K[0-9]+\.[0-9]+\.[0-9]+rc[0-9]+' \
    | sort -Vu | tail -1
  ```
- TheRock bump can still proceed independently.

**TheRock** — Use `curl` HEAD requests to check for the latest nightly via the CDN:
```bash
# Read current therock-version from version.json to extract the version prefix (e.g., "7.12.0a").
# Don't hardcode the prefix — the major version may change between bumps.
for DATE in $(date +%Y%m%d) $(date -d yesterday +%Y%m%d) $(date -d '2 days ago' +%Y%m%d); do
  URL="https://rocm.nightlies.amd.com/tarball/therock-dist-linux-gfx94X-dcgpu-${PREFIX}${DATE}.tar.gz"
  if curl -sI "$URL" | grep -q "HTTP.*200"; then
    echo "FOUND: ${PREFIX}${DATE}"
    break
  fi
done
```

### Phase 2: Update Fusilli Repo (Separate PRs)

Each dependency that has a newer version gets its own branch, commit, and PR. If only one has changed, only one PR is created.
Use `projects/fusilli` only to inspect or create worktrees. Run edits, build,
test, commit, and PR commands from the corresponding task worktree.

1. **Prepare Fusilli Repo**
   - Read the current repository instructions and confirm its base branch
     (historically `main`). Preserve the canonical checkout's branch and work.
     From `projects/fusilli`:
     ```bash
     git fetch origin
     ```

2. **IREE Bump** (if version changed)
   - From `projects/fusilli`, create a worktree from the confirmed base:
     ```bash
     git worktree add ../worktrees/fusilli/bump-iree-YYYYMMDD \
       -b users/sambhav/bump-iree-YYYYMMDD origin/<base>
     cd ../worktrees/fusilli/bump-iree-YYYYMMDD
     ```
   - Update only the `iree-version` field in `version.json`
   - The `iree-version` value is the bare version string (e.g., `3.11.0rc20260217`) without the `iree-` prefix — consumers prepend it as needed
   - Commit:
     ```bash
     git add version.json
     git commit -s -m "$(cat <<'EOF'
     Bump IREE to MM/DD nightly

     IREE: OLD_VERSION -> NEW_VERSION
     EOF
     )"
     ```
   - **Push**: Ask the user to push manually:
     ```
     Please run git push -u origin HEAD from the IREE task worktree.
     ```
   - Create PR:
     ```bash
     gh pr create -R iree-org/fusilli --title "Bump IREE to NEW_VERSION" --body "$(cat <<'EOF'
     ## Summary
     Automated IREE version bump.

     | Dependency | Old | New |
     |------------|-----|-----|
     | IREE | `OLD_VERSION` | `NEW_VERSION` |

     **IREE changelog**: https://github.com/iree-org/iree/compare/iree-OLD_VERSION...iree-NEW_VERSION

     Co-authored-by: <active agent and model> <agent email>

     🤖 Generated with [<active tool>](<active tool URL>)
     EOF
     )"
     ```
   - Leave the worktree available for follow-up. Create the next bump from
     the canonical checkout without switching this worktree's branch.

3. **TheRock Bump** (if version changed)
   - From `projects/fusilli`, create a separate worktree from the same base:
     ```bash
     git worktree add ../worktrees/fusilli/bump-therock-YYYYMMDD \
       -b users/sambhav/bump-therock-YYYYMMDD origin/<base>
     cd ../worktrees/fusilli/bump-therock-YYYYMMDD
     ```
   - Update only the `therock-version` field in `version.json`
   - Commit:
     ```bash
     git add version.json
     git commit -s -m "$(cat <<'EOF'
     Bump TheRock to MM/DD nightly

     TheRock: OLD_VERSION -> NEW_VERSION
     EOF
     )"
     ```
   - **Push**: Ask the user to push manually:
     ```
     Please run git push -u origin HEAD from the TheRock task worktree.
     ```
   - Create PR:
     ```bash
     gh pr create -R iree-org/fusilli --title "Bump TheRock to NEW_VERSION" --body "$(cat <<'EOF'
     ## Summary
     Automated TheRock version bump.

     | Dependency | Old | New |
     |------------|-----|-----|
     | TheRock | `OLD_VERSION` | `NEW_VERSION` |

     Co-authored-by: <active agent and model> <agent email>

     🤖 Generated with [<active tool>](<active tool URL>)
     EOF
     )"
     ```

4. **Build and Test** (optional)
   - Use the `fusilli-build-test-lint` skill to verify changes
   - Only if running inside docker dev-container
   - If not in container, skip this step and let CI handle it

## Workflow: Docker Image Update (Rare)

This is needed only when system packages change (new clang, cmake, etc.) or the
entrypoint script structure changes. IREE/TheRock version bumps do NOT require
Docker image rebuilds.

### Steps

Before editing, create or reuse a Docker task worktree under
`projects/worktrees/docker/` using the confirmed Docker base branch. Run all
following commands there; read `entrypoint.sh` from that worktree.

1. **Update Docker Entrypoint** (optional)
   - File: `entrypoint.sh` in the Docker task worktree
   - Update `IREE_GIT_TAG` and `THEROCK_GIT_TAG` default pins for local dev convenience
   - Make any structural changes needed

2. **Create Docker Branch, Commit, and PR**
   Run these commands from the Docker task worktree:
   ```bash
   git add entrypoint.sh
   git commit -s -m "Update docker image"
   ```
   - Ask user to push manually, then create PR

3. **Wait for PR Merge and Publish**
   - Ask user to merge the docker PR and trigger "Publish Docker Image" workflow
   - Poll for workflow completion:
     ```bash
     WORKFLOW_ID=$(gh run list --workflow="Publish Docker Image" --limit 1 --json databaseId --jq '.[0].databaseId')
     while STATUS=$(gh run view $WORKFLOW_ID --json status --jq '.status'); [ "$STATUS" != "completed" ]; do
       sleep 30
     done
     ```

4. **Update Fusilli docker image digest** after the new image is published
   - `exec_docker_ci.sh` pins the image by SHA digest (e.g., `:main@sha256:...`), so it must be updated explicitly
   - Get the new digest from the published image:
     ```bash
     NEW_DIGEST=$(docker manifest inspect ghcr.io/sjain-stanford/compiler-dev-ubuntu-24.04:main --verbose \
       | jq -r '.Descriptor.digest // .digest')
     ```
   - Update the digest in `build_tools/docker/exec_docker_ci.sh`

## Error Handling

- If IREE or TheRock versions cannot be found, report error and stop
- If the `iree-base-compiler` pip wheel is not available, stop and suggest retrying later
- If the base branch or remote is unclear, resolve it from repository metadata
  before creating a worktree; do not change an existing branch's upstream.
- Preserve uncommitted work in place; do not stash or switch another task's branch.
- If build/test fails, report failures but still create PR (CI will catch issues)
- If not in docker container for build/test, skip that step and note in PR that CI will validate

## Known Constraints

1. **`git push` is sandboxed**: The Bash tool cannot execute `git push`. Always ask the user to push branches manually.
2. **IREE releases API is unreliable**: The GitHub releases API (`/releases`) may not list recent rc tags. Always use the git tags API (`/git/refs/tags`) with `--paginate`.
3. **TheRock version prefix may change**: Don't hardcode the version prefix (e.g., `7.12.0a`). Read it from the current `therock-version` in `version.json` and only replace the date portion.
4. **Fusilli repo branch state**: The canonical checkout may be on a feature
   branch. Leave it intact and create each bump in its own task worktree.

---
name: bump-fusilli-deps
description: Bump IREE and TheRock to latest nightly versions in the fusilli repository. Updates version.json and optionally the docker entrypoint defaults and image digest.
---

# Bump Fusilli Dependencies Skill

Bumps IREE and TheRock to the latest nightly versions in the fusilli repository.
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

## Architecture

Version management uses `version.json` as the single source of truth:
- `iree-version`: IREE version string (e.g., `3.11.0rc20260217`) — note: no `iree-` prefix; consumers prepend it
- `therock-version`: TheRock nightly tag (e.g., `7.12.0a20260217`)

The CI script `exec_docker_ci.sh` reads versions from `version.json` and passes them
as environment variables to the Docker container, overriding the defaults baked into
the image's `entrypoint.sh`. This decouples version bumps from Docker image rebuilds.

## Workflow: Version Bump (Fusilli Only)

This is the common case — bumping IREE and/or TheRock versions.

### Phase 0: Pre-flight Checks

1. **Check `gh` auth**: `gh auth status`
2. **Read current versions** from `projects/fusilli/version.json`
3. **Check for uncommitted changes**: `git status` in fusilli repo. If unrelated changes exist, ask the user whether to include them or only commit the version bump.

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
- Report the missing version to the user and **stop the workflow**.
- Suggest trying again later or falling back to the most recent version that has wheels:
  ```bash
  curl -sL https://iree.dev/pip-release-links.html \
    | grep -oP 'iree_base_compiler-\K[0-9]+\.[0-9]+\.[0-9]+rc[0-9]+' \
    | sort -Vu | tail -1
  ```

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

### Phase 2: Update Fusilli Repo

1. **Prepare Fusilli Repo**
   - The fusilli repo may NOT be on `main` when starting. Handle this:
     ```bash
     cd projects/fusilli
     git stash          # Save any in-progress work
     git checkout main
     ```
   - If `git pull` fails with "no tracking information", set it first:
     ```bash
     git branch --set-upstream-to=origin/main main
     git pull
     ```
   - Create the bump branch:
     ```bash
     git checkout -b bump-deps-YYYYMMDD
     ```

2. **Update `version.json`**
   - Update both `iree-version` and `therock-version` fields:
     ```json
     {
       "package-version": "0.0.1.dev",
       "iree-version": "NEW_IREE_VERSION",
       "therock-version": "NEW_THEROCK_VERSION"
     }
     ```
   - The `iree-version` value is the bare version string (e.g., `3.11.0rc20260217`) without the `iree-` prefix — consumers prepend it as needed
   - All consumers (CMakeLists.txt, build-and-test-win.yml, exec_docker_ci.sh, ThePebble.py) read from this file automatically

3. **Commit Changes**
   ```bash
   cd projects/fusilli
   git add version.json
   git commit -s -m "$(cat <<'EOF'
   Bump IREE and TheRock to MM/DD nightly

   - IREE: OLD_VERSION -> NEW_VERSION
   - TheRock: OLD_VERSION -> NEW_VERSION

   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```

4. **Build and Test** (optional)
   - Use the build-test-lint skill to verify changes
   - Only if running inside docker dev-container
   - If not in container, skip this step and let CI handle it

5. **Push and Create PR**
   - **IMPORTANT**: `git push` is blocked by the Bash tool sandbox. Ask the user to push manually:
     ```
     Please run: cd projects/fusilli && git push -u origin bump-deps-YYYYMMDD
     ```
   - Once pushed, create PR:
     ```bash
     cd projects/fusilli
     gh pr create --title "Bump IREE and TheRock to MM/DD nightly" --body "$(cat <<'EOF'
     ## Summary
     - IREE: OLD_VERSION → NEW_VERSION
     - TheRock: OLD_VERSION → NEW_VERSION

     🤖 Generated with [Claude Code](https://claude.com/claude-code)
     EOF
     )"
     ```

## Workflow: Docker Image Update (Rare)

This is needed only when system packages change (new clang, cmake, etc.) or the
entrypoint script structure changes. IREE/TheRock version bumps do NOT require
Docker image rebuilds.

### Steps

1. **Update Docker Entrypoint** (optional)
   - File: `projects/docker/entrypoint.sh`
   - Update `IREE_GIT_TAG` and `THEROCK_GIT_TAG` default pins for local dev convenience
   - Make any structural changes needed

2. **Create Docker Branch, Commit, and PR**
   ```bash
   cd projects/docker
   git checkout main && git pull
   git checkout -b update-docker-YYYYMMDD
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
- If `git pull` fails with no tracking info, set upstream with `git branch --set-upstream-to=origin/main main`
- If repo has uncommitted changes on a non-main branch, `git stash` before switching to main
- If build/test fails, report failures but still create PR (CI will catch issues)
- If not in docker container for build/test, skip that step and note in PR that CI will validate

## Known Constraints

1. **`git push` is sandboxed**: The Bash tool cannot execute `git push`. Always ask the user to push branches manually.
2. **IREE releases API is unreliable**: The GitHub releases API (`/releases`) may not list recent rc tags. Always use the git tags API (`/git/refs/tags`) with `--paginate`.
3. **TheRock version prefix may change**: Don't hardcode the version prefix (e.g., `7.12.0a`). Read it from the current `therock-version` in `version.json` and only replace the date portion.
4. **Fusilli repo branch state**: The fusilli repo may be on a feature branch when this skill runs. Always stash and checkout main first.

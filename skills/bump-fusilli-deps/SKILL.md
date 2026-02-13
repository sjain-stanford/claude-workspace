---
name: bump-fusilli-deps
description: Automate bumping IREE and TheRock to latest nightly versions across docker and fusilli repositories. Updates entrypoint.sh, publishes docker image, extracts digest, updates fusilli exec_docker_ci.sh, builds/tests, and creates PRs.
---

# Bump Fusilli Dependencies Skill

Automates the end-to-end process of bumping IREE and TheRock to the latest nightly versions across both the docker and fusilli repositories.

## Usage

```
/bump-fusilli-deps
```

**Autonomy**: Execute this workflow autonomously. Only ask the user for help if you encounter errors or blockers (e.g., version not found, workflow failed, permission denied, build failures). Otherwise, proceed through all steps automatically.

This skill performs the complete workflow:
1. Find latest IREE and TheRock nightly versions
2. Update docker repo and create PR
3. Wait for docker image publish
4. Update fusilli repo with new container digest
5. Build and test fusilli
6. Create PR for fusilli

## Prerequisites

- `gh` CLI must be authenticated (`gh auth login`)
- User must have write access to both docker and fusilli repos
- For build/test step: must be running inside docker dev-container

## Workflow

### Phase 0: Pre-flight Checks

Before starting, verify the environment:

1. **Check `gh` auth**: `gh auth status`
2. **Read current versions** from `projects/docker/entrypoint.sh` to get the `IREE_GIT_TAG` and `THEROCK_GIT_TAG` values. These are the OLD versions to bump from.
3. **Read current digest** from `projects/fusilli/build_tools/docker/exec_docker_ci.sh` to get the current sha256 digest.
4. **Check for pre-existing uncommitted changes** in both repos (`git status` in each). If unrelated changes exist, ask the user whether to include them or only commit the version bump files.

### Phase 1: Update Docker Repo

1. **Find Latest Versions** (run in parallel)

   **IREE** — Use the git refs/tags API (NOT the releases API, which may not list recent rc tags):
   ```bash
   gh api 'repos/iree-org/iree/git/refs/tags' --jq '.[].ref' --paginate 2>&1 \
     | grep 'rc' | sort -V | tail -1 | sed 's|refs/tags/iree-||'
   ```
   This returns a version string like `3.11.0rc20260212`.

   > **WARNING**: Do NOT use `gh api repos/iree-org/iree/releases` — the releases API
   > returns only formally published releases, which may be months behind the latest
   > nightly rc tags. Always use the git tags API.

   **TheRock** — Use `curl` HEAD requests to check S3 bucket for the latest nightly:
   ```bash
   # Read current THEROCK_GIT_TAG from entrypoint.sh to extract the version prefix (e.g., "7.12.0a").
   # Don't hardcode the prefix — the major version may change between bumps.
   # Try today's date first, then yesterday, then day before.
   for DATE in $(date +%Y%m%d) $(date -d yesterday +%Y%m%d) $(date -d '2 days ago' +%Y%m%d); do
     URL="https://therock-nightly-tarball.s3.us-east-2.amazonaws.com/therock-dist-linux-gfx94X-dcgpu-${PREFIX}${DATE}.tar.gz"
     if curl -sI "$URL" | grep -q "HTTP.*200"; then
       echo "FOUND: ${PREFIX}${DATE}"
       break
     fi
   done
   ```

   > **NOTE**: Extract the version prefix (e.g., `7.12.0a`) from the current
   > `THEROCK_GIT_TAG` in entrypoint.sh rather than hardcoding it. The major version
   > may change between bumps.

2. **Update Docker Entrypoint**
   - File: `projects/docker/entrypoint.sh`
   - Update `IREE_GIT_TAG` and `THEROCK_GIT_TAG` version pins
   - Example:
     ```bash
     IREE_GIT_TAG="${IREE_GIT_TAG:-3.11.0rc20260212}"
     THEROCK_GIT_TAG="${THEROCK_GIT_TAG:-7.12.0a20260212}"
     ```

3. **Create Docker Branch and Commit**
   - Ensure you're on a clean `main` branch first:
     ```bash
     cd projects/docker
     git checkout main && git pull
     ```
   - Create a new branch:
     ```bash
     git checkout -b bump-iree-therock-YYYYMMDD
     ```
   - Stage ONLY `entrypoint.sh` (not any other changed files):
     ```bash
     git add entrypoint.sh
     ```
   - Commit with sign-off:
     ```bash
     git commit -s -m "$(cat <<'EOF'
     Bump IREE and TheRock to MM/DD nightly

     - IREE: OLD_VERSION -> NEW_VERSION
     - TheRock: OLD_VERSION -> NEW_VERSION

     Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
     EOF
     )"
     ```

4. **Push and Create Docker PR**
   - **IMPORTANT**: `git push` is blocked by the Bash tool sandbox. Ask the user to push manually:
     ```
     Please run: cd projects/docker && git push -u origin bump-iree-therock-YYYYMMDD
     ```
   - Once the user confirms the push, create the PR:
     ```bash
     cd projects/docker
     gh pr create --title "Bump IREE and TheRock to MM/DD nightly" --body "$(cat <<'EOF'
     ## Summary
     - Bump IREE from OLD_VERSION to NEW_VERSION
     - Bump TheRock from OLD_VERSION to NEW_VERSION

     ## Test plan
     - [ ] Clear `.cache/docker` directory
     - [ ] Run container and verify IREE and TheRock install correctly
     - [ ] Verify build/test workflow passes

     🤖 Generated with [Claude Code](https://claude.com/claude-code)
     EOF
     )"
     ```

5. **Wait for PR Merge and Publish**
   - Ask user to merge the docker PR and trigger "Publish Docker Image" workflow
   - Poll for workflow completion:
     ```bash
     gh run list --workflow="Publish Docker Image" --limit 1 --json databaseId,status,conclusion
     ```
   - Loop with 30-second intervals until `status` is `completed`:
     ```bash
     WORKFLOW_ID=$(gh run list --workflow="Publish Docker Image" --limit 1 --json databaseId --jq '.[0].databaseId')
     # Poll loop
     while STATUS=$(gh run view $WORKFLOW_ID --json status --jq '.status'); [ "$STATUS" != "completed" ]; do
       sleep 30
     done
     ```

6. **Extract Docker Digest**
   ```bash
   WORKFLOW_ID=$(gh run list --workflow="Publish Docker Image" --limit 1 --json databaseId --jq '.[0].databaseId')
   DIGEST=$(gh run view $WORKFLOW_ID --log 2>&1 | grep "exporting manifest sha256:" | grep -oP 'sha256:[a-f0-9]{64}' | head -1)
   ```

### Phase 2: Update Fusilli Repo

7. **Prepare Fusilli Repo**
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
     git checkout -b bump-docker-YYYYMMDD
     ```

8. **Update Fusilli Docker Digest**
   - File: `projects/fusilli/build_tools/docker/exec_docker_ci.sh`
   - Replace the old sha256 digest with the new one extracted in step 6
   - Example:
     ```bash
     ghcr.io/sjain-stanford/compiler-dev-ubuntu-24.04:main@sha256:NEW_DIGEST
     ```

9. **Update Fusilli IREE Version**
   - IREE version is pinned in a single file: `version.json` (the `iree-version` field)
   - All other consumers (CMakeLists.txt, Windows CI workflow, ThePebble.py) read from this file automatically
   - Update the `iree-version` field from OLD_IREE_VERSION to NEW_IREE_VERSION:
     ```json
     {
       "package-version": "0.0.1.dev",
       "iree-version": "iree-NEW_IREE_VERSION"
     }
     ```
   - The value uses the git tag format with the `iree-` prefix (e.g., `iree-3.11.0rc20260212`)

10. **Commit Fusilli Changes**
   ```bash
   cd projects/fusilli
   git add build_tools/docker/exec_docker_ci.sh version.json
   git commit -s -m "$(cat <<'EOF'
   [Docker] Update CI container to MM/DD nightly

   Updates docker container digest and IREE version references:
   - Docker digest: sha256:OLD_DIGEST -> sha256:NEW_DIGEST
   - IREE: OLD_VERSION -> NEW_VERSION
   - TheRock: OLD_VERSION -> NEW_VERSION (via docker container)

   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```

11. **Build and Test Fusilli** (optional)
    - Use the build-test-lint skill to verify changes
    - Only if running inside docker dev-container
    - If not in container, skip this step and let CI handle it

12. **Push and Create Fusilli PR**
    - Ask user to push manually (same sandbox restriction as docker):
      ```
      Please run: cd projects/fusilli && git push -u origin bump-docker-YYYYMMDD
      ```
    - Once pushed, create PR:
      ```bash
      cd projects/fusilli
      gh pr create --title "[Docker] Update CI container to MM/DD nightly" --body "$(cat <<'EOF'
      ## Summary
      - Update docker container digest to use latest IREE and TheRock nightlies
      - Update IREE version references across the codebase
      - IREE: OLD_VERSION → NEW_VERSION
      - TheRock: OLD_VERSION → NEW_VERSION

      ## Test plan
      - [ ] Verify CI passes with new container
      - [ ] Smoke test build and tests locally

      🤖 Generated with [Claude Code](https://claude.com/claude-code)
      EOF
      )"
      ```

## Error Handling

- If IREE or TheRock versions cannot be found, report error and stop
- If `git pull` fails with no tracking info, set upstream with `git branch --set-upstream-to=origin/main main`
- If repo has uncommitted changes on a non-main branch, `git stash` before switching to main
- If workflow doesn't complete within reasonable time, ask user to check manually
- If digest extraction fails, ask user to provide manually
- If build/test fails, report failures but still create PR (CI will catch issues)
- If not in docker container for build/test, skip that step and note in PR that CI will validate

## Known Constraints

1. **`git push` is sandboxed**: The Bash tool cannot execute `git push`. Always ask the user to push branches manually.
2. **IREE releases API is unreliable**: The GitHub releases API (`/releases`) may not list recent rc tags. Always use the git tags API (`/git/refs/tags`) with `--paginate`.
3. **TheRock version prefix may change**: Don't hardcode the version prefix (e.g., `7.12.0a`). Read it from the current `THEROCK_GIT_TAG` in entrypoint.sh and only replace the date portion.
4. **Fusilli repo branch state**: The fusilli repo may be on a feature branch when this skill runs. Always stash and checkout main first.

---
name: build-test-lint
description: Build the Fusilli project, run tests, and execute lint checks. Use after making code changes to verify build integrity, test results, and code quality.
---

# Build, Test, and Lint Skill

Executes the full build, test, and lint pipeline for the Fusilli project and reports results.

## Usage

```
/build-test-lint [options]
```

Options:
- `cpu` - Build for CPU instead of AMDGPU (default: AMDGPU)
- `skip-lint` - Skip the lint step
- `skip-test` - Skip the test step

## Critical Environment Pre-Check

**ALWAYS** verify you're in the development docker container before building. Building outside docker will fail due to missing dependencies.

Run this check first:
```bash
[ -f /.dockerenv ] && echo "In Docker" || echo "Not in Docker"
```

If NOT in the container, immediately stop and report:
> **ENVIRONMENT ERROR**: Not running inside docker dev-container. Launch a dev-container on Cursor then launch Claude from there.

## Workflow

### Step 1: Build

Navigate to `projects/fusilli` and configure the `cmake` build following `projects/fusilli/README.md` with these flags:
- `-DIREE_SOURCE_DIR=<path/to/claude-workspace>/.cache/docker/iree` (local docker cache)
- `-DFUSILLI_SYSTEMS_AMDGPU=ON` for AMDGPU (default) or `-DFUSILLI_SYSTEMS_AMDGPU=OFF` for CPU
- `-DCMAKE_BUILD_TYPE=RelWithDebInfo` (default) unless debug build is requested
- `-DFUSILLI_ENABLE_CLANG_TIDY=OFF` as this will be enabled later in the lint step

Capture all build output including warnings and errors.

**If the build fails, stop immediately and report the build failure. Do not proceed to test or lint.**

### Step 2: Test and Lint

After a successful build, run test and lint steps. These are independent of each other - if one fails, continue with the other and report both results.

#### Test

Run `ctest` following `projects/fusilli/README.md`:
- Use `-j $(nproc)` for parallel execution
- Use `--rerun-failed --output-on-failure --verbose` if there are failures

Report:
- Total tests run
- Tests passed
- Tests failed (with names and failure reasons)
- Tests skipped

#### Lint

Two stages:

**Stage 1: Pre-commit hooks**
```bash
pre-commit run --all-files
```
Capture lint warnings and errors with file locations.

**Stage 2: Clang-tidy**
Build Fusilli with `-DFUSILLI_ENABLE_CLANG_TIDY=ON` and report any clang-tidy failures.

## Reporting Format

After completing all steps, provide a structured report:

```
## Build-Test-Lint Report

### Build Status: [PASS/FAIL]
[If failed, list specific errors with file:line references]
[Include any warnings even if build succeeded]

### Test Status: [PASS/FAIL]
- Total: X
- Passed: X
- Failed: X
- Skipped: X

[If any failed, list each failed test with its failure reason]

### Lint Status: [PASS/FAIL]
[List all lint issues (pre-commit and clang-tidy) with file:line:column and the specific violation]

### Summary
[One-line summary: e.g., "Build succeeded, 2 tests failed, 5 lint warnings"]
```

## Critical Rules

1. **DO NOT attempt to fix any issues** - Reporting only
2. **DO NOT modify any source files**
3. **DO NOT disable or skip tests** to make them pass
4. **DO NOT ignore lint warnings** - Report all of them
5. **Stop on build failure** - Do not run tests or lint if build fails
6. **Test and lint are independent** - Run both even if one fails
7. **Be precise** - Include exact error messages, file paths, and line numbers
8. **Be concise** - Focus on actionable information

## Error Handling

- **Build failure**: Stop immediately, report the build error, do not proceed
- **Test or lint failure**: Continue with the other step, report both results
- **Command execution failure**: Report the command and error message

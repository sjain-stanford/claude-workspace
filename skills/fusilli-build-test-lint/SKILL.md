---
name: fusilli-build-test-lint
description: Build, test, and lint the archived Fusilli project. Use only for explicit Fusilli work; use rocjitsu-build-test for rocjitsu.
---

# Fusilli Build, Test, and Lint

Fusilli is retained as an archival project in this workspace. Do not invoke this
skill for rocjitsu or general C++ work.

Executes the full build, test, and lint pipeline for the Fusilli project using the scripts in the active Fusilli checkout and reports results. The active checkout may be the canonical `projects/fusilli` directory or a per-task worktree under `projects/worktrees/fusilli/`.

## Usage

```
/fusilli-build-test-lint [options]
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

## Scripts Reference

All build, test, and coverage operations use scripts in the active Fusilli checkout:

| Script | Purpose |
|--------|---------|
| `build.sh` | CMake configure + build with named configs |
| `test.sh` | CTest runner with filtering, backend selection |
| `coverage.sh` | Code coverage report generation (lcov/genhtml) |

### build.sh configs

| Config | Compiler | Build Type | AMDGPU | Extras |
|--------|----------|------------|--------|--------|
| `cpu-debug` | clang-18 | Debug | OFF | logging |
| `cpu-debug-tidy` | clang-18 | Debug | OFF | logging, clang-tidy |
| `cpu-release` | clang-18 | Release | OFF | logging |
| `cpu-asan` | clang-18 | Debug | OFF | ASAN + UBSAN |
| `cpu-codecov` | gcc-13 | Debug | OFF | code coverage |
| `gpu-debug` | clang-22 | Debug | ON | logging |
| `gpu-debug-tidy` | clang-22 | Debug | ON | logging, clang-tidy |
| `gpu-release` | clang-22 | Release | ON | logging |
| `gpu-asan` | clang-18 | Debug | ON | ASAN + UBSAN |

## Workflow

### Step 1: Build

Run the build from the active Fusilli checkout directory using `build.sh`:

```bash
# GPU build (default)
./build_tools/scripts/build.sh gpu-debug \
  --iree-source-dir <path/to/claude-workspace>/.cache/docker/iree

# CPU build (when 'cpu' option is specified)
./build_tools/scripts/build.sh cpu-debug \
  --iree-source-dir <path/to/claude-workspace>/.cache/docker/iree
```

Default config selection:
- GPU: `gpu-debug` (or `gpu-release` if release build is requested)
- CPU: `cpu-debug` (or `cpu-release` if release build is requested)

The `--iree-source-dir` flag should point to the local docker cache at `<path/to/claude-workspace>/.cache/docker/iree`.

Extra CMake options can be passed after `--`:
```bash
./build_tools/scripts/build.sh gpu-debug --iree-source-dir ... -- -DSOME_OPTION=ON
```

Capture all build output including warnings and errors.

**IMPORTANT: Build output verification**
- **NEVER** pipe build output through `tail`, `head`, or other truncating commands. Errors early in the output will be hidden.
- **ALWAYS** explicitly verify the build exit code using `echo $?` or `&&` chaining after the build command.
- Do not assume a build succeeded from lack of visible output — always confirm with the exit code.

**If the build fails, stop immediately and report the build failure. Do not proceed to test or lint.**

### Step 2: Test and Lint

After a successful build, run test and lint steps. These are independent of each other - if one fails, continue with the other and report both results.

#### Test

Run tests using `test.sh` from the active Fusilli checkout directory:

```bash
./build_tools/scripts/test.sh --build-dir build
```

Key options:
- `--build-dir DIR` - Build directory (default: `build/`)
- `--timeout SECS` - Test timeout in seconds (default: 120)
- `--parallel N` - Number of parallel tests (default: `$(nproc)`)
- `--backend capi|cli` - Compile backend (default: `capi`)
- `-R REGEX` - Only run tests matching regex
- `-E REGEX` - Exclude tests matching regex
- `--extra-verbose` - Print extra test output
- `--validate-cache-cleanup` - Run cache cleanup validation after tests

If tests fail, re-run the failed tests with extra verbosity:
```bash
./build_tools/scripts/test.sh --build-dir build --extra-verbose -R "failed_test_regex"
```

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
Run a clang-tidy build using the `-tidy` config variant:
```bash
# GPU
./build_tools/scripts/build.sh gpu-debug-tidy \
  --iree-source-dir <path/to/claude-workspace>/.cache/docker/iree

# CPU
./build_tools/scripts/build.sh cpu-debug-tidy \
  --iree-source-dir <path/to/claude-workspace>/.cache/docker/iree
```

Report any clang-tidy failures.

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

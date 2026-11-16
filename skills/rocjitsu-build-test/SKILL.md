---
name: rocjitsu-build-test
description: Build and verify rocjitsu changes with focused CMake/Ninja targets, CTest, amdisa pytest, formatting, sanitizers, or corpus tests selected by affected subsystem and risk.
---

# rocjitsu Build and Test

Resolve the source repository and qualification branch using the workspace's
`LOCAL_CONTEXT.md` (if present) and `rocjitsu-project` guidance. NPI
qualification must use the designated internal base and task worktree.

Run commands from the active rocjitsu source directory
(`.../rocm-systems/emulation/rocjitsu`), using a build directory inside that
same task worktree. Do not modify source while performing a report-only build
or test request.

## Verification philosophy

Use the narrowest test that can falsify the change quickly, then widen coverage
as confidence grows. A normal sequence is:

1. Configure once for the intended compiler/build mode.
2. Build the smallest affected target, then the default target.
3. Run focused tests by exact name or regex with failure output.
4. Run the full local CTest suite when dependencies and time permit.
5. Run Python tests for `amdisa` or corpus tooling changes.
6. Run formatting on changed files.
7. Add sanitizer, corpus, install-tree, or benchmark coverage only when the
   change or user request justifies its cost.

Never hide failures by disabling tests, broadening exclusions, or increasing
timeouts without diagnosing the reason. Distinguish sanitizer findings from
ordinary assertion failures, hangs, resource contention, external ROCr issues,
and known instrumentation blind spots.

## Configure and build

Default developer/review build on the workspace's Linux GCC/Clang toolchain:
set `WORKSPACE_ROOT` to the enclosing meta-workspace, then use the
[compressed-debug initial cache](references/compressed-debug.cmake) for a new
build directory. It preserves full debug information and compresses both
objects and linked binaries; rocjitsu's many statically linked test programs
otherwise repeat large uncompressed debug sections.

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -C "$WORKSPACE_ROOT/skills/rocjitsu-build-test/references/compressed-debug.cmake"
cmake --build build -j "$(nproc)"
```

The initializer applies only to new cache entries. Preserve an existing build's
flags, and do not reconfigure or clean a build while reviewers or tests use it.
On another toolchain, verify compiler, linker and debugger support for zstd
debug sections before using it; zlib compression is an alternative. Explicit
CI reproduction flags take precedence.

Prepare one build per revision/compiler/sanitizer mode and let reviewers reuse
its binaries. A separate build is justified for a changed source snapshot,
mutation test, sanitizer, or compiler comparison, not merely a new reviewer.
Keep output directories isolated across different revisions; a shared writable
build tree cannot safely serve several worktrees. A bounded shared `ccache`
can save compilation time but does not eliminate linked binaries on disk.

Release is appropriate for performance/corpus qualification; Debug is useful
for assertions and debugging. If the machine is memory constrained, follow CI's
conservative worker policy instead of using every core:

```bash
cmake --build build -j "$(( ($(nproc) + 1) / 2 ))"
```

Inspect configure output. HIP and daemon tests are conditionally enabled; a
green suite with HIP disabled does not qualify HIP/KFD/daemon behavior. ROCm may
be selected with `ROCM_PATH` when it is not in the default location.

## Focused and full tests

List tests before guessing names:

```bash
ctest --test-dir build --show-only
```

Run the smallest relevant set, then widen:

```bash
ctest --test-dir build -R '<regex>' --output-on-failure
ctest --test-dir build --output-on-failure -j "$(( ($(nproc) + 1) / 2 ))"
```

For a GoogleTest binary, listing and filtering directly is useful while
iterating:

```bash
build/tests/<test-binary> --gtest_list_tests
build/tests/<test-binary> --gtest_filter='<Suite.Case>'
```

Read [references/verification-matrix.md](references/verification-matrix.md) to
choose subsystem-specific tests and higher-cost checks.

## Python and generated ISA

For generator/parser/semantic changes:

```bash
python -m pip install -e lib/python/ pre-commit
python -m pytest lib/python/amdisa/tests -x
```

Regenerate from the `rocm-systems` repository root, not from the generated
directory:

```bash
./emulation/rocjitsu/scripts/generate-amdisa.sh
```

Review the entire generated diff, ensure every generated output is included,
rerun the Python suite, and build/test affected C++ targets. Never patch
generated output merely to make a test pass.

## Formatting and static analysis

Read and follow `docs/style.md` in the active rocjitsu task worktree when
adding or changing code, and check changed code against it during verification.
Passing formatting and static analysis does not replace checking the guide's
rules that automated tools do not enforce.

Run pre-commit from the `rocm-systems` repository root. Prefer changed files
for routine iteration; use all files only when requested or when changing the
format configuration:

```bash
pre-commit run --files <changed-file>...
```

For clang-tidy qualification, use a separate build directory:

```bash
cmake -S . -B build-tidy -G Ninja -DRJ_CLANG_TIDY=ON \
  -C "$WORKSPACE_ROOT/skills/rocjitsu-build-test/references/compressed-debug.cmake"
cmake --build build-tidy -j "$(( ($(nproc) + 1) / 2 ))"
```

## Sanitizers

Use separate build directories so modes never contaminate one another:

```bash
cmake -S . -B build-asan -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -C "$WORKSPACE_ROOT/skills/rocjitsu-build-test/references/compressed-debug.cmake" \
  -DRJ_ENABLE_ASAN=ON -DRJ_ENABLE_UBSAN=ON
cmake --build build-asan -j "$(( ($(nproc) + 1) / 2 ))"
ctest --test-dir build-asan -R '<affected-regex>' --output-on-failure
```

Available options are `RJ_ENABLE_ASAN`, `RJ_ENABLE_UBSAN`, `RJ_ENABLE_TSAN`,
and `RJ_ENABLE_MSAN`; `RJ_SANITIZER_RUNTIME` accepts `AUTO`, `SHARED`, or
`STATIC`. Do not combine incompatible modes. TSan cannot model synchronization
through distinct shared-memory aliases used at the simulator/client boundary;
inspect stacks and ownership before classifying or suppressing a report.

## Report

Report the checkout and commit, configure mode, whether ROCm/HIP tests were
enabled, commands run, passed/failed/skipped tests, and warnings or diagnostics.
State explicitly which higher-cost checks were not run and why. A focused pass
is evidence for the affected contract, not a claim that the whole project is
green.

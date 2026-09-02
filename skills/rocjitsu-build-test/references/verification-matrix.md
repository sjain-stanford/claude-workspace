# rocjitsu verification matrix

Select checks from the affected behavior. Confirm exact current test names with
`ctest --show-only` or the test binary's `--gtest_list_tests`.

| Change area | First-line verification | Wider verification |
|---|---|---|
| Utilities | Owning unit-test binary | Full CTest; scalar/SIMD variants if applicable |
| ISA decode/execute | Decode or instruction execution harness; target-specific exact correctness tests | Related scalar and SIMD correctness suites across affected architectures |
| `amdisa` generator/parser | Focused `pytest` module, then all `lib/python/amdisa/tests` | Regeneration diff plus affected C++ build/tests |
| VM/CU/waves/cache/memory | Nearest VM component and architecture test | HIP smoke tests and relevant simulator corpus |
| KFD/interposer | Focused ioctl, mmap, lifecycle, or preload tests | HIP memcpy/vector-add; local and daemon modes |
| Simdojo/concurrency | Component/event/topology tests | Scaling and stress repetition; TSan where its memory model applies |
| DBT | Translator/legalization/unit test for the rule | Translation-and-dispatch test; relevant DBT corpus and idempotence checks |
| DBI/patching | Analysis, builder, spill, trampoline, or probe test | Patched-kernel dispatch and plugin-observable behavior |
| Config/schema | Config parsing/validation test | Representative CLI launch with matching KMD/non-KMD config |
| CLI/daemon/RPC | Focused CLI/daemon/API test | Lifecycle, concurrent clients, cleanup, and RCCL only when available |
| Plugins/race detector | Plugin unit test and exact expected event/log | Small end-to-end simulated kernel |
| Packaging/install | Normal build tests | Configure with `RJ_INSTALL_TESTS=ON`, install, then run installed CTest tree |
| Performance-sensitive path | Correctness test | Protocol in `docs/benchmarking.md`; compare repeated samples and memory |

## Important distinctions

- Plain configs support lower-level simulation; unmodified HIP applications
  generally require a matching `_kmd.json` configuration.
- The compiled code-object target must match the simulated guest target unless
  the test intentionally exercises DBT.
- HIP and RCCL tests depend on the ROCm toolchain/runtime and may be disabled at
  configure time. Record that fact rather than treating absence as a skip.
- Corpus tests live in a separate repository and are expensive. Use them for
  broad ISA/simulator/DBT qualification, not every local edit.
- Sanitized corpus timeouts may be load-sensitive. Reproduce individually and
  at lower parallelism before changing timeouts or expected-failure lists.
- Benchmarks establish a performance claim only when run using
  `docs/benchmarking.md`; a single timing is diagnostic, not evidence.

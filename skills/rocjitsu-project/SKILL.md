---
name: rocjitsu-project
description: Work on, debug, review, or explain ROCm rocjitsu in rocm-systems/emulation/rocjitsu, including GPU simulation, DBT, DBI, KFD interposition, ISA semantics/codegen, plugins, and configuration.
---

# rocjitsu Project

Use the active `rocm-systems` checkout. In this workspace the canonical checkout is
`projects/rocm-systems`, and implementation work belongs in a branch-backed
worktree under `projects/worktrees/rocm-systems/<task-slug>/` unless the user
explicitly asks to modify the canonical checkout.

Paths below are relative to `emulation/rocjitsu/` unless stated otherwise.

## Establish context

1. Read `CONTRIBUTING.md` and the nearest applicable docs before designing or
   editing. They are the project source of truth and override generic workspace
   C++ guidance.
2. Inspect the current branch, diff, and local changes. Preserve unrelated work.
3. Identify the affected execution strategy: simulation, dynamic binary
   translation (DBT), or dynamic binary instrumentation (DBI). Do not assume a
   behavior or test from one path covers another.
4. Read [references/technical-map.md](references/technical-map.md) when locating
   a subsystem, tracing cross-layer behavior, or assessing architectural impact.

## Engineering invariants

- rocjitsu is a C++20 project inside the `ROCm/rocm-systems` monorepo. It runs
  unmodified HIP/ROCR applications by interposing at the KFD/DRM boundary, or
  rewrites already-compiled AMDGPU code objects through DBT/DBI.
- Extend `lib/util`, `lib/simdojo`, and existing rocjitsu components before
  adding libraries, dependencies, abstractions, or duplicate helpers.
- Never edit generated ISA decoders, encoders, execute bodies, legalization
  tables, or encoding translators directly. Change the `amdisa` generator,
  regenerate with `scripts/generate-amdisa.sh`, and keep generator and generated
  output in the same change.
- Preserve ISA identity distinctions. Architecture families, concrete `gfx`
  targets, ELF/code-object identities, and configured simulated devices are
  related but not interchangeable.
- Translation must fail closed for unsupported or ambiguous instructions.
  Preserve diagnostics and avoid silently emitting guessed semantics.
- Treat the daemon RPC transport as a trusted, local, version-matched transport,
  not a security boundary or network-facing protocol.
- Simulation hot paths are sensitive to allocations, exceptions, logging, and
  synchronization. Use project utilities and measure performance changes.
- Follow the project's error model: `Result`/`FailureOr<T>` plus
  `DiagnosticEmitter` for expected failures; exceptions only for unrecoverable
  initialization, configuration, or execution failures. Catch only at a boundary
  that translates the failure.
- Use `util/log.h` in libraries. Trace groups may compile out; use
  `Logger::warn()` for always-visible warnings. Respect the documented CLI and
  ROCR-hook `stderr` carve-outs.
- For config changes, update the FlatBuffers schema, parsing/validation, topology
  construction, representative configs, and tests together.
- Large public API, subsystem, translation-pair, KFD/RPC, or dependency changes
  require the design-proposal process in `CONTRIBUTING.md`; localized fixes and
  tests do not.

## Change strategy

- Start with the smallest focused regression or characterization test that
  observes the contract at the affected layer.
- Mirror source structure under `tests/` (`dbt/`, `patch/`, `analysis/`,
  `race-detector/`, and so on).
- For instruction semantics, prefer decode/execute harness tests and exact
  scalar/SIMD correctness checks. Include edge operands, masks, modifiers,
  widths, and architecture gates relevant to the encoding.
- For DBT/DBI, verify both transformed structure and executable behavior when
  practical. Check branches, relocations, symbols, descriptors, scratch/LDS,
  register liveness, and unsupported-case diagnostics.
- For KFD, daemon, queue, or memory changes, test lifecycle, cleanup, error
  paths, concurrency, and both local and daemon mode when the contract spans
  them.
- Keep simulated workloads deliberately small. CPU simulation can be orders of
  magnitude slower than hardware.
- Use the `rocjitsu-build-test` skill after changes and choose verification in
  proportion to the affected layer.

## Primary project references

- `README.md`: supported architectures, feature maturity, entry points
- `CONTRIBUTING.md`: contribution rules, code placement, style, error handling
- `docs/architecture.md`: layer and component map
- `docs/vm-design.md`, `docs/simdojo.md`: simulation and scheduling
- `docs/dbt-design.md`, `docs/dbi-design.md`: binary transformation
- `docs/codegen.md`, `docs/isa-target-providers.md`: ISA generation/registration
- `docs/configuration.md`, `docs/plugins.md`, `docs/rocjitsu-cli.md`: user/runtime contracts
- `docs/benchmarking.md`: performance and memory measurement protocol

# rocjitsu technical map

Read this reference when a task crosses components or its correct ownership is
unclear. Prefer the checked-out project docs and source over this summary when
details disagree.

## Execution paths

```text
Unmodified HIP / ROCR process
        |
        +-- simulation: LD_PRELOAD -> KFD/DRM interposer -> simulated driver
        |               -> AQL queues -> command processor -> compute units
        |               -> decode/execute -> memory/cache/plugin model
        |
        +-- DBT guest: HSA hook -> load guest code object -> decode/CFG/liveness
        |              -> legalize/translate -> repair ELF metadata/relocations
        |              -> load host code object -> hardware or simulated host
        |
        `-- DBI: load code object -> analyze/register plan -> insert probes and
                 trampolines -> repair object -> execute with sidecar metadata
```

## Ownership by directory

| Concern | Location |
|---|---|
| Public C API | `lib/rocjitsu/include/rocjitsu/` |
| GPU VM, queues, CUs, waves, memory, caches | `lib/rocjitsu/src/rocjitsu/vm/amdgpu/` |
| KFD/DRM emulation and interposition | `lib/rocjitsu/src/rocjitsu/kmd/linux/` |
| ISA decoding/execution | `lib/rocjitsu/src/rocjitsu/isa/` |
| Hand-written AMDGPU semantics | `lib/rocjitsu/src/rocjitsu/isa/arch/amdgpu/<target-or-shared>/` |
| Generated ISA sources | `lib/rocjitsu/src/rocjitsu/isa/arch/amdgpu/generated/` |
| ISA generator and Python tests | `lib/python/amdisa/` |
| ELF/code-object loading and mutation | `lib/rocjitsu/src/rocjitsu/code/` |
| DBT translation | `lib/rocjitsu/src/rocjitsu/code/dbt/` |
| DBI patching and spill planning | `lib/rocjitsu/src/rocjitsu/code/patch/` |
| CFG, liveness, def-use | `lib/rocjitsu/src/rocjitsu/analysis/` |
| Simulation engine and PDES | `lib/simdojo/` |
| Shared low-level utilities | `lib/util/` |
| Plugins | `lib/rocjitsu/src/rocjitsu/vm/plugins/` |
| CLI and daemon | `tools/rocjitsu/` |
| DBT/decode command-line tools | `tools/` |
| FlatBuffers schemas and config loading | `schemas/`, `lib/rocjitsu/src/rocjitsu/config/` |
| Device/topology configurations | `configs/` |

## Cross-layer review prompts

### ISA and execution semantics

- Is the source generated or hand-written, and was the correct source changed?
- Are decode, encode, disassembly, and execution consistent for every affected
  target?
- Are EXEC/lane masks, sub-dword writes, modifiers, signedness, special floating
  values, wave size, and scalar versus SIMD behavior covered?
- Does a semantic change affect plugin-observed register access contracts?

### Simulation and concurrency

- Is simulated time distinct from wall-clock synchronization?
- Are event ownership, ordering, queue retirement, and completion signals
  deterministic?
- Are shared mappings intentionally accessed through aliases? ThreadSanitizer
  cannot infer HSA/doorbell happens-before relationships across distinct
  `MAP_SHARED` aliases, so diagnose the ownership and addresses before
  classifying a report as a rocjitsu race or suppressing it.
- Does the behavior work in-process and through daemon RPC where applicable?

### DBT and DBI

- Does analysis use the right kernel-scoped CFG and account for implicit
  operands?
- Are register allocation, spills, scratch/LDS, branches, relocations, symbols,
  instruction growth, and kernel descriptor resources repaired together?
- Are unsupported encodings rejected with useful diagnostics?
- Does output remain stable/idempotent where the tool promises it?

### KFD, hooks, and loader boundaries

- Are errno, ioctl ABI layouts, file descriptors, mappings, fork/dup lifecycle,
  runtime directory isolation, and cleanup preserved?
- Could a hook execute during loader/runtime initialization, or from a signal
  handler, where allocation, locking, iostreams, or non-async-signal-safe calls
  are unsafe?
- Are daemon peers local, trusted, and version compatible?

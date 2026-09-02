---
name: fusilli-project
description: Work with the archived Fusilli C++ Graph API and JIT frontend for IREE. Use only when the user explicitly asks about Fusilli; rocjitsu is the workspace's active project.
---

# Fusilli Project Knowledge Base

Fusilli is retained for archival and occasional maintenance work. Do not use
this skill for rocjitsu or infer Fusilli dependencies in active workspace tasks.

Fusilli is a C++ Graph API and JIT Frontend for IREE that leverages just-in-time compiled and code-generated kernels to accelerate training and inference workloads. Inspired by cuDNN's graph API, it exposes cuDNN-like primitives backed by the IREE compiler and runtime stack.

Note: All paths in this document are relative within the active Fusilli checkout unless specified otherwise. Use `projects/fusilli` for reading, planning, debugging, and gathering context. Before making implementation edits, create or switch to a task worktree under `projects/worktrees/fusilli/<task-slug>/` and work there unless the user explicitly asks to modify the canonical checkout.

## Architecture Overview

Fusilli is a **header-only library** (`libfusilli` is a CMake INTERFACE target) using **C++20** standard. It follows LLVM coding standards for consistency with IREE.

### Core Components

```
include/fusilli/
├── graph/        # Graph construction and execution
├── node/         # Operation primitives
├── attributes/   # Operation configuration
├── backend/      # Compilation and runtime
└── support/      # Utilities and infrastructure
```

#### Graph API (`include/fusilli/graph/`)

| Component | Purpose |
|-----------|---------|
| `Context` | Manages graph execution context |
| `Graph` | Main graph construction interface, holds nodes and edges |

#### Nodes (`include/fusilli/node/`)

Operation primitives representing computation units:
- `conv_node` - Convolution operations
- `matmul_node` - Matrix multiplication
- `layernorm_node` - Layer normalization
- `pointwise_node` - Element-wise operations
- `reduction_node` - Reduction operations
- Additional node types for specific operations

Each node type has corresponding attributes in `include/fusilli/attributes/`.

#### Attributes (`include/fusilli/attributes/`)

Configuration structures for each operation type:
- Define operation-specific parameters (strides, padding, dimensions, etc.)
- Strongly typed per-operation attribute classes
- Parameters map directly to MLIR operation attributes

#### Backend (`include/fusilli/backend/`)

| Component | Purpose |
|-----------|---------|
| `Backend` | Backend configurations and device selection |
| `Buffer` | Memory management for tensors |
| `Handle` | Handle and device management |
| `CompileSession` | IREE compiler interface (C-API) |
| `CompileCommand` | IREE compiler invocation (CLI) |
| `Runtime` | IREE runtime interface (C-API) |

#### Support (`include/fusilli/support/`)

| Component | Purpose |
|-----------|---------|
| `asm_emitter.h` | MLIR assembly generation utilities |
| `logging.h` | Logging infrastructure |
| `cache.h` | Compilation artifact caching |
| `external_tools.h` | External tool detection (iree-compile, rocm tools) |
| `extras.h` | Shared support utilities |

## Dependencies

### IREE Integration

Fusilli has a **source dependency on IREE runtime** but expects the **compiler to be pre-built**.

| Component | Integration Method |
|-----------|-------------------|
| **Runtime** | Built from source and statically linked |
| **Compiler** | Side-loaded as prebuilt binary (`iree-compile`) or shared library (`libIREECompiler.so`) |

**Compiler interface selection:**
- CLI mode: Uses `iree-compile` binary
- C-API mode: Uses `libIREECompiler.so` shared library
- Controlled by `FUSILLI_COMPILE_BACKEND_USE_CLI` environment variable

**Why this design?**
- IREE compiler is heavy to build (depends on MLIR/LLVM)
- IREE runtime is lightweight and optimized for static linking
- Prebuilt compiler can come from pip packages or shared library distributions

### Test Framework

- **Unit tests**: Based on Catch2 framework
- **Lit tests**: Located in `tests/lit/`, use LLVM's lit + FileCheck for verifying ASM emitter output IR
- **Integration tests**: Samples in `samples/` serve as end-to-end integration tests
- Standalone test binaries in `build/bin/tests/` for isolated debugging

### Benchmark Framework

- **C++ benchmark driver**: Located in `benchmarks/`, provides CLI for running operation-specific benchmarks
- **Python benchmark runner**: `benchmarks/run_benchmark.py` wrapper for batch execution and result aggregation
- **Profiling**: Depends on `rocprofv3` for capturing kernel profile traces on AMD GPUs

## Development Workflow

### Worktree Discipline

- Treat `projects/fusilli/` as the canonical checkout for reading context, inspecting history, and understanding the codebase.
- Before modifying Fusilli source, tests, samples, benchmarks, or build files, create or switch to a task-specific worktree under `projects/worktrees/fusilli/...`.
- Run build, test, lint, commit, and PR commands from the worktree, not from `projects/fusilli/`.
- At handoff, include the worktree path, branch name, verification performed, and remaining follow-up.
- Only edit `projects/fusilli/` directly when the user explicitly asks for that checkout to be modified.

### Adding a New Operation

1. **Create attribute struct** in `include/fusilli/attributes/`
   - Define operation-specific parameters
   - Follow existing attribute patterns

2. **Create node class** in `include/fusilli/node/`
   - Inherit from appropriate base class
   - Implement shape/stride/type inference logic

3. **Implement ASM emitter methods** in `include/fusilli/support/asm_emitter.h`
   - Implement MLIR emission logic for the operation

4. **Register with Graph API** in `include/fusilli/graph/`
   - Add method to `Graph` class for creating the node

5. **Add tests**
   - Catch2 unit test for the operation
   - Lit test for MLIR output verification
   - Integration tests (samples) for end to end validation
   - Never change or disable a test just to make it pass, instead triage and propose a solution

6. **Update benchmarks** (if applicable)
   - Add sub-command to benchmark driver


## API Compatibility

Fusilli aims to match the frontend API of:
- **cudnn-frontend** (NVIDIA) - Primary API reference
- **hipdnn** (AMD ROCm) - Secondary reference, integration target

When adding or modifying user-facing API (especially `fusilli::Graph`), ensure consistency with these libraries for portability.

Fusilli generated Torch MLIR ASM as the interface with IREE, so ensure any changes to the ASM emitter are compatible with the `torch` dialect spec.

Fusilli calls into the IREE compiler and runtime C-API, so ensure any changes to the backend interface are compatible with IREE.


## Plan Mode

When entering plan mode for Fusilli feature development, save implementation plans to the `plans/` directory at the claude-workspace root.

**Plan file naming convention:** `plans/<feature-or-task-name>.md`

Example: `plans/external-transient-buffer-support.md`

## Related Resources (paths are relative to claude-workspace root)

- IREE codebase: `projects/iree`
- Torch-MLIR codebase: `projects/torch-mlir`
- cuDNN frontend codebase: `projects/cudnn-frontend`
- hipDNN codebase: `projects/hipdnn`
- LLVM coding standards: `skills/llvm-coding-standards.md`

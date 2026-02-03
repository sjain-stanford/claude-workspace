---
name: fusilli-project
description: Comprehensive knowledge base for the Fusilli project - a C++ Graph API and JIT frontend for IREE. Use when exploring the codebase, adding new features, debugging issues, or understanding the architecture.
---

# Fusilli Project Knowledge Base

Fusilli is a C++ Graph API and JIT Frontend for IREE that leverages just-in-time compiled and code-generated kernels to accelerate training and inference workloads. Inspired by cuDNN's graph API, it exposes cuDNN-like primitives backed by the IREE compiler and runtime stack.

Note: All paths in this document are relative within the `projects/fusilli` directory.

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

Fusilli calls into the IREE compiler and runtime C-API, so ensure any changes to the backend interface are compatible with IREE.

## Related Resources

- IREE documentation: https://iree.dev/
- IREE codebase: `projects/iree`
- cuDNN frontend codebase: `projects/cudnn-frontend`
- hipDNN codebase: `projects/hipdnn`
- LLVM coding standards: `skills/llvm-coding-standards.md`

# Fusilli Skills

## Build Commands

### Standard Build
```shell
cmake -GNinja -S. -Bbuild \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DFUSILLI_SYSTEMS_AMDGPU=ON` \
    -DIREE_SOURCE_DIR=/home/sambhav/claude-workspace/.cache/docker/iree
cmake --build build --target all
```

For CPU only builds: `-DFUSILLI_SYSTEMS_AMDGPU=OFF`
Skip tests/samples: `-DFUSILLI_BUILD_TESTS=OFF`
Skip benchmarks: `-DFUSILLI_BUILD_BENCHMARKS=OFF`

### Testing
```shell
# Run all tests in parallel
ctest --test-dir build --output-on-failure -j $(nproc)

# Run failed tests verbosely
ctest --test-dir build --rerun-failed --output-on-failure --verbose
```

Individual tests are built as standalone binaries in `build/bin/`.

### Linting
```shell
# Pre-commit hooks (auto-runs on git commit after `pre-commit install`)
pre-commit run --all-files

# Standalone clang-format
find . -path ./build -prune -o \( -type f \( -name "*.cpp" -o -name "*.h" \) -print \) | xargs clang-format -i

# Enable clang-tidy during build
cmake ... -DFUSILLI_ENABLE_CLANG_TIDY=ON
```

### Benchmarks
```shell
# Basic benchmark
build/bin/benchmarks/fusilli_benchmark_driver <ARGS> <SUB-COMMAND> <SUB-ARGS>

# Dump compilation artifacts to disk
build/bin/benchmarks/fusilli_benchmark_driver --dump <ARGS> <SUB-COMMAND> <SUB-ARGS>

# Specify GPU device (for multi-GPU systems)
build/bin/benchmarks/fusilli_benchmark_driver --device <N> <ARGS> <SUB-COMMAND> <SUB-ARGS>

# Profile with rocprofv3 (generates pftrace file for Perfetto)
rocprofv3 --output-format pftrace -r -- build/bin/benchmarks/fusilli_benchmark_driver --iter 10 conv <ARGS>
```

## Architecture

### Core Components

**Graph API** (`include/fusilli/graph/`):
- `Context`: Manages graph execution context
- `Graph`: Main graph construction interface, holds nodes and edges

**Nodes** (`include/fusilli/node/`):
- Operation primitives: `conv_node`, `matmul_node`, `layernorm_node`, `pointwise_node`, `reduction_node` etc.
- Each node has corresponding attributes in `include/fusilli/attributes/`

**Attributes** (`include/fusilli/attributes/`):
- Configuration structures for each operation type
- Define operation-specific parameters (strides, padding, dimensions, etc.)
- Strongly typed per-operation attribute classes

**Backend** (`include/fusilli/backend/`):
- `Backend`: Backend configurations
- `Buffer`: Memory management
- `Handle`: Handle and device management
- `CompileSession`: IREE compiler interface (C-API)
- `CompileCommand`: IREE compiler invocation (CLI)
- `Runtime`: IREE runtime interface (C-API)

**Support** (`include/fusilli/support/`):
- `asm_emitter.h`: MLIR assembly generation utilities
- `logging.h`: Logging infrastructure
- `cache.h`: Compilation artifact caching
- `external_tools.h`: External tool detection (iree-compile, rocm tools)
- `extras.h`: Shared support utilities


### Dependencies

**IREE**: Fusilli has a source dependency on IREE runtime but NOT the compiler.
- Runtime: Built from source and statically linked
- Compiler: Side-loaded as prebuilt binary (`iree-compile`) or shared library
- Controlled by env vars: `FUSILLI_EXTERNAL_IREE_COMPILE`, `FUSILLI_EXTERNAL_IREE_COMPILER_LIB`
- Compiler interface: CLI or C-API (toggled by `FUSILLI_COMPILE_BACKEND_USE_CLI`)

## Development Notes

- Fusilli is header-only library (`libfusilli` is INTERFACE target)
- Tests use Catch2 framework
- Lit tests in `tests/lit/` use FileCheck for output verification
- C++20 standard
- Follow LLVM coding standards for consistency with IREE

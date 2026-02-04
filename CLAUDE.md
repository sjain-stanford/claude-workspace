# Claude Workspace

Meta workspace for Claude-assisted development across multiple repositories.

## Workspace Structure

Each subdirectory under `projects/` is an independent git repository. Sub-repos are gitignored in the meta workspace repo and are cloned locally for development and/or to serve as context for Claude.

- `projects/fusilli/` - C++ graph API and JIT engine powered by IREE
  - This is the main project that depends on IREE compiler and runtime
  - Refer `projects/fusilli/README.md` for technical documentation
- `projects/fusilli-benchmarks/` - Central location for Fusilli benchmarks
  - **CRITICAL**: Contains sensitive information (never make public)
  - Refer `projects/fusilli-benchmarks/README.md` for benchmarking instructions
- `projects/iree/` - MLIR enabled compiler and runtime stack
  - This serves as a reference for the compiler and runtime C API interfaces used in Fusilli
- `projects/torch-mlir/` - Torch MLIR dialect and lowering passes
  - This serves as reference for the Torch ASM emitter in Fusilli
- `projects/cudnn-frontend/` - cudNN frontend library for NVIDIA GPU acceleration
  - Fusilli tries to match the frontend API for portability reasons so treat this as the C++ graph API reference
- `projects/hipdnn/` - ROCm hipDNN library for AMD GPU acceleration
  - This is a sparse checkout of the `ROCm/rocm-libraries` monorepo
  - This also serves as reference for the C++ graph API
  - Fusilli gets integrated as a plugin into the hipDNN kernel provider ecosystem
- `projects/docker/` - Docker for ML compiler development environment
  - This is the unified development docker for all builds and tests
  - Use as reference but expect Claude is launched from a dev-container already

## Skills

- `skills/build-test-lint/` - Build, test, and lint for Fusilli; use after code changes to verify integrity
- `skills/fusilli-project/` - Use when adding new features or debugging issues in Fusilli
- `skills/pr-review/` - Use when asked to review a PR from GitHub
- `skills/self-review/` - Use when asked to self-review local branch changes (before creating a PR)
- `skills/stage-and-commit/` - Use when asked to commit local changes (enforces signed commits and agent co-authorship)
- `skills/review-criteria.md` - Shared review checklist and standards (used by pr-review and self-review)
- `skills/llvm-coding-standards.md` - Reference for C++ coding standards from LLVM (shared across skills)

> **Note**: Skills are symlinked from `.claude/` (`.claude/skills` -> `../skills`) so Claude Code can discover them while keeping the source files at the repo root for easier editing.

## Plans

Implementation plans created during plan mode are saved to `plans/` at claude-workspace root. These provide a record of design decisions and implementation strategies for non-trivial tasks.

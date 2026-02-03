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
- `projects/cudnn-frontend/` - cudNN frontend library for NVIDIA GPU acceleration
  - Fusilli tries to match the frontend API for portability reasons so treat this as the C++ graph API reference
- `projects/hipdnn/` - ROCm hipDNN library for AMD GPU acceleration
  - This is a sparse checkout of the `ROCm/rocm-libraries` monorepo
  - This also serves as reference for the C++ graph API
  - Fusilli gets integrated as a plugin into the hipDNN kernel provider ecosystem
- `projects/docker/` - Docker for ML compiler development environment
  - This is the unified development docker for all builds and tests
  - Use as reference but expect Claude is launched from a dev-container already

## Agents

- `agents/build-test-lint.md` - Sub-agent for running builds, tests, and lint checks on Fusilli

## Skills

- `skills/fusilli-project/` - Use when adding new features or debugging issues to fusilli
- `skills/pr-review/` - Use when asked to review a PR from GitHub
- `skills/self-review/` - Use when asked to self-review local branch changes (before creating a PR)
- `skills/stage-and-commit/` - Use when asked to commit changes (enforces signed commits and agent co-authorship)
- `skills/review-criteria.md` - Shared review checklist and standards (used by pr-review and self-review)
- `skills/llvm-coding-standards.md` - Reference for C++ coding standards from LLVM (shared across skills)

> **Note**: Skills and agents are symlinked from `.claude/` (`.claude/skills` -> `../skills`, `.claude/agents` -> `../agents`) so Claude Code can discover them while keeping the source files at the repo root for easier editing.

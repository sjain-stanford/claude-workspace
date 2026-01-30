# Claude Workspace

Meta workspace for Claude-assisted development across multiple repositories.

## Workspace Structure

Each subdirectory under `projects/` is an independent git repository. Sub-repos are gitignored in the meta workspace repo.

- `projects/fusilli/` - C++ graph API and JIT engine powered by IREE
  - This is the main project that depends on IREE compiler and runtime
  - Check `skills/fusilli_skills.md` for build, test, benchmark and lint commands
  - Check `projects/fusilli/README.md` for anything else
- `projects/fusilli-benchmarks/` - Central location for running Fusilli benchmarks and tracking progress
  - **CRITICAL**: Contains sensitive information, never make public
  - See `projects/fusilli-benchmarks/README.md` for detailed benchmarking instructions
- `projects/iree/` - MLIR enabled compiler and runtime stack
  - This serves as a reference for the compiler and runtime C API interfaces used in Fusilli
- `projects/cudnn-frontend/` - cudNN frontend library for NVIDIA GPU acceleration
  - Fusilli tries to match the frontend API for portability reasons so treat this as the C++ graph API reference
- `projects/hipdnn/` - ROCm hipDNN library for AMD GPU acceleration
  - This is a sparse checkout of the `ROCm/rocm-libraries` monorepo
  - Apart from serving as reference for the C++ graph API, we also integrate Fusilli as a plugin into the hipDNN kernel provider ecosystem.
- `projects/docker/` - Docker for ML compiler development environment
  - This is the unified development docker for all builds and tests
  - Use as reference but expect agent is launched from a dev-container already


## Execution Environment
- **CRITICAL**: Always verify you're in the docker container before attempting to build
- Building outside the docker container will fail due to missing dependencies
- If not in a docker container, just display this message and stop: "Launch a dev-container on Cursor then launch Claude from there".

## Code style
- Reference LLVM coding standards (https://llvm.org/docs/CodingStandards.html) for any code in Fusilli / IREE
- Always use punctuation for comments and docstrings (periods after sentences, start with uppercase)
- Follow style of neighboring code when in doubt
- Follow clang-tidy settings for naming conventions

## Testing
- Always add unit and/or integration tests for new or modified code
- Never change or disable a test just to make it pass, instead triage why it's failing and propose a solution

## Commits
- Always use signed commits (git commit -s ...)
- Always mention co-authorship if LLM assistance is used
- Never `git push` commits without my explicit permission

## PR Reviews
- When asked to review a PR, fetch the PR details and diff (preferably using `gh` CLI)
- Look for consistency, correctness, simplicity, presence of tests, and conformity to code standards
- If the PR touches user-facing API (e.g. adds a new operation or method on fusilli::Graph), make sure it is consistent with cudnn-frontend / hipdnn API
- Look for opportunities to replace verbose and unreadable code with simple and elegant constructs (C++20)
- Please save the PR review comments and recommendations to an .md file for continuity
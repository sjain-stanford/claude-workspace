# Claude Workspace

Meta workspace for Claude-assisted development across multiple repositories.

## Workspace Structure

Each subdirectory under `projects/` is an independent git repository. Sub-repos are gitignored in the meta workspace repo and are cloned locally to serve as context for Claude.

- `projects/fusilli/` - C++ graph API and JIT engine powered by IREE
  - This is the main project that depends on IREE compiler and runtime
  - Refer `skills/fusilli_skills.md` for build, test, benchmark and lint commands
  - Refer `projects/fusilli/README.md` for anything else
- `projects/fusilli-benchmarks/` - Central location for Fusilli benchmarks
  - **CRITICAL**: Contains sensitive information (never make public)
  - Refer `projects/fusilli-benchmarks/README.md` for detailed benchmarking instructions
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


## Execution Environment
- **CRITICAL**: Always verify you're in the docker container before attempting to build
- Building outside the docker container will fail due to missing dependencies
- If not in a docker container simply display this message and stop: "Launch a dev-container on Cursor then launch Claude from there"

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
- Always mention co-authorship if Claude (or any other LLM agent) assistance is used
- Never `git push` without my explicit permission

## PR Reviews
- When asked to review a PR, fetch the PR details and diff (preferably using `gh` CLI)
- Look for consistency, correctness, simplicity, presence of tests, and conformity to code standards
- If the PR touches user-facing API (e.g. adds a new operation or method on fusilli::Graph), make sure it is consistent with cudnn-frontend / hipdnn API
- Look for opportunities to replace verbose and unreadable code with simple and elegant constructs (C++20)
- Ensure any remaining work is documented with a `TODO` linking to the issue
- Ensure `TODO`s follow the convention: `TODO(org/repo#issue)`, example: `TODO(iree-org/iree#123)` unless it's an issue in the same repo in which case just use the issue number: `TODO(#issue)`
- Please save the detailed PR review summary as a markdown file the `reviews/` directory (add PR number in the format: `pr-repo-number.md`, example: `pr-fusilli-123.md`)
# Claude Workspace

Meta workspace for Claude-assisted development across multiple repositories.

## Workspace Structure

Each subdirectory is an independent git repository. Sub-repos are gitignored in the meta workspace repo.

- `fusilli/` - C++ graph API and JIT engine powered by IREE
  - This is the main project that depends on IREE compiler and runtime
  - Check fusilli_skills.md for build, test, benchmark and lint commands
  - Check fusilli/README.md for anything else
- `iree/` - MLIR enabled compiler and runtime stack
  - This serves as a reference for the compiler and runtime C API interfaces used in Fusilli
- `docker/` - Docker for ML compiler development environment
  - This is the unified development docker for all builds and tests
  - Use as reference but expect agent is launched from a dev-container already
- `cudnn-frontend/` - Reference for C++ graph API
  - cuDNN frontend library for NVIDIA GPU acceleration
  - Fusilli tries to match the frontend graph API as close as possible for portability reasons
- `hipdnn/` - Reference for C++ graph API
  - ROCm hipDNN library for AMD GPU acceleration (sparse checkout of projects/hipdnn)
- `dot-files/` - System configuration files
  - System configuration files (.bashrc, .gitconfig) that are copied to $HOME


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
- When asked to review a PR, check if the branch is checked-out locally first (and if not, might need to add fork as remote first then fetch)
- Look for consistency, correctness, simplicity, presence of tests, and conformity to code standards
- If the PR touches user-facing API (e.g. adds a new operation or method on fusilli::Graph), make sure it is consistent with cudnn-frontend / hipdnn API
- Look for opportunities to replace verbose and unreadable code with simple and elegant constructs (C++20)

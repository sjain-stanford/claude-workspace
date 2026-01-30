# Claude Workspace

Meta workspace for Claude-assisted development across multiple repositories.

## Workspace Structure

Each subdirectory is an independent git repository (sub-repos are gitignored in the meta workspace repo):
- `fusilli/` - C++ graph API and JIT engine powered by IREE
- `iree/` - MLIR enabled compiler and runtime stack
- `docker/` - Docker for ML compiler development environment
- `cudnn-frontend/` - Reference for C++ graph API
- `hipdnn/` - Reference for C++ graph API
- `dot-files/` - System configuration files

## Repository Overview

### fusilli
- This is the main project that depends on IREE compiler and runtime
- **Key Commands**: Check fusilli/README.md

### docker
- This is the unified development docker for all ML compiler builds and tests

### iree
- This is a good reference for C API interfaces used in Fusilli

### cudnn-frontend
- cuDNN frontend library for NVIDIA GPU acceleration

### hipdnn
- ROCm hipDNN library for AMD GPU acceleration (sparse checkout of projects/hipdnn)

### dot-files
- System configuration files (.bashrc, .gitconfig) that are copied to $HOME


## Execution Environment
- **CRITICAL**: Always verify you're in the docker container before attempting to build
- Building outside the docker container will fail due to missing dependencies
- If not in a docker container, just display this message and stop: "Launch a dev-container on Cursor/VSCode then launch Claude from there".

## Code style
- Reference LLVM coding standards (https://llvm.org/docs/CodingStandards.html) for any code in Fusilli / IREE
- Always use punctuation for comments and docstrings (periods after sentences, start with uppercase)
- Follow style of neighboring code when in doubt

## Testing
- Always add tests for new or modified code
- Never change or disable a test to make it pass, instead triage why it's failing and propose a solution

## Commits
- Always use signed commits (git commit -s ...)
- Always mention co-authorship if LLM assistance is used
- Never `git push` commits without my explicit permission

## PR Reviews
- When asked to review a PR, check if the branch is checked-out locally first and if not do it (might need to add fork as remote first)
- Look for consistency, correctness, simplicity, presence of tests, and conformity to code standards
- If the PR is to add a new operation or method on fusilli::Graph, make sure any user-facing API is consistent with cudnn-frontend / hipdnn

# Claude Workspace

Meta workspace for Claude-assisted development across multiple repositories.

## Workspace Structure

Each subdirectory is an independent git repository (sub-repos are gitignored in the meta workspace repo):
- `fusilli/` - Development repo
- `iree/` - Dependency repo
- `docker/` - Docker for development environment
- `cudnn-frontend/` - Reference for C++ graph API
- `dot-files/` - System configuration files

## Repository Overview

### fusilli
- **Purpose**: This is the main project that depends on IREE compiler and runtime
- **Key Commands**: Check fusilli/README.md

### docker
- **Purpose**: This is the unified development docker for all builds, tests
- **Key Commands**: Check docker/README.md

### iree
- **Purpose**: This is a good reference for C API interfaces used in Fusilli

### cudnn-frontend
- **Purpose**: This is a reference for the C++ graph API in Fusilli

### dot-files
- **Purpose**: System configuration files (.bashrc, .gitconfig) that are copied to $HOME


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
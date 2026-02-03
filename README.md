# Claude Workspace

A meta workspace for Claude-assisted development across my current ML compiler projects.

## Overview

This workspace serves as a unified development environment for working on my current ML compiler projects (such as Fusilli, IREE) alongside their dependencies and reference implementations.

## Structure

```
claude-workspace/
├── projects/        # Relevant sub-repositories are cloned here
│   ├── fusilli/
│   ├── fusilli-benchmarks/
│   ├── iree/
│   ├── cudnn-frontend/
│   ├── hipdnn/
│   ├── docker/
│   └── ...
├── skills/          # Project specific skills and shared references
│   ├── fusilli-project/
│   ├── pr-review/
│   ├── self-review/
│   ├── stage-and-commit/
│   ├── review-criteria.md
│   └── llvm-coding-standards.md
├── agents/          # Sub-agent definitions
│   └── build-test-lint.md
├── reviews/         # Saved PR and self reviews
├── .claude/         # Claude Code configuration
│   ├── settings.json
│   ├── skills -> ../skills    # Symlink for skill discovery
│   └── agents -> ../agents    # Symlink for agent discovery
├── CLAUDE.md        # Top level context for agents
└── README.md
```

## Getting Started

### Prerequisites

- Cursor IDE (recommended) or VS Code IDE
- Docker
- Extensions:
   - Claude Code for VSCode
   - Dev Containers

### Setup

1. **Clone the workspace:**
   ```bash
   git clone https://github.com/sjain-stanford/claude-workspace.git
   cd claude-workspace
   ```

2. **Clone sub-repositories:**
   ```bash
   cd projects/

   # Main project
   git clone --single-branch --branch main https://github.com/iree-org/fusilli.git

   # Benchmarks (private repo)
   git clone --single-branch --branch main https://github.com/nod-ai/fusilli-benchmarks.git

   # Dependencies and references
   git clone --single-branch --branch main https://github.com/iree-org/iree.git
   git clone --single-branch --branch main https://github.com/NVIDIA/cudnn-frontend.git
   git clone --single-branch --branch main https://github.com/sjain-stanford/docker.git

   # Sparse checkout of hipdnn from rocm-libraries (hipdnn is on develop branch)
   git clone --single-branch --branch develop --filter=blob:none --sparse https://github.com/ROCm/rocm-libraries.git hipdnn
   cd hipdnn
   git sparse-checkout set projects/hipdnn
   cd ..
   ```

3. **Launch development container:**
   - Open Cursor IDE rooted at `claude-workspace` then launch the development docker container (`./projects/docker/run_docker.sh`)
   - `Ctrl + Shift + P` and select  `Dev Containers: Attach to Running Container`
   - From the new window again open `claude-workspace` and launch Claude Code from Cursor: `Claude Code: Open in Terminal`

4. **Start developing:**
   - Use Claude Code for AI-assisted development

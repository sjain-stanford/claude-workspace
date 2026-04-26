# Claude Workspace

A meta workspace for Claude Code and Codex-assisted development across my current ML compiler projects.

## Overview

This workspace is the shared root for local agent configuration, reusable skills, saved plans/reviews, and the independent git repositories cloned under `projects/`. The main active project is Fusilli, with IREE, Torch-MLIR, cuDNN frontend, hipDNN, and related tooling checked out as dependencies or API references.

## Structure

```
claude-workspace/
├── projects/        # Independent git repositories cloned locally
│   ├── fusilli/
│   ├── fusilli-benchmarks/
│   ├── cudnn-frontend/
│   ├── docker/
│   ├── dot-files/
│   ├── hipdnn/
│   ├── iree/
│   └── torch-mlir/
├── scripts/         # Workspace utility scripts
│   └── git-in.sh
├── skills/          # Project specific skills and shared references
│   ├── build-test-lint/
│   ├── bump-fusilli-deps/
│   ├── fusilli-project/
│   ├── pr-create/
│   ├── pr-review/
│   ├── self-review/
│   ├── stage-and-commit/
│   ├── review-criteria.md
│   └── llvm-coding-standards.md
├── plans/           # Saved implementation plans
├── reviews/         # Saved PR and self-review outputs
├── .agents/         # Agent configuration
│   └── skills -> ../skills
├── .beads/          # Local issue tracker state
├── .claude/         # Claude Code configuration
│   ├── settings.json
│   ├── settings.local.json
│   └── skills -> ../skills
├── .codex/          # Codex rules and local configuration
│   └── rules/
├── .cursor/         # Cursor local configuration
├── AGENTS.md        # Top-level instructions for agents
├── CLAUDE.md        # Top-level context for Claude Code
├── LICENSE
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
   git clone https://github.com/iree-org/fusilli.git

   # Benchmarks (private repo)
   git clone https://github.com/nod-ai/fusilli-benchmarks.git

   # Dependencies and references
   git clone https://github.com/iree-org/iree.git
   git clone https://github.com/llvm/torch-mlir.git
   git clone https://github.com/NVIDIA/cudnn-frontend.git

   # Workspace support repos
   git clone https://github.com/sjain-stanford/docker.git
   git clone https://github.com/sjain-stanford/dot-files.git

   # Sparse checkout of hipdnn from rocm-libraries (hipdnn is on develop branch)
   git clone --filter=blob:none --sparse https://github.com/ROCm/rocm-libraries.git hipdnn
   cd hipdnn
   git sparse-checkout set projects/hipdnn
   cd ..
   ```

3. **Launch development container:**
   - Open Cursor IDE rooted at `claude-workspace` then launch the development docker container (`./projects/docker/run_docker.sh`)
   - `Ctrl + Shift + P` and select  `Dev Containers: Attach to Running Container`
   - From the new window again open `claude-workspace` and launch Claude Code from Cursor: `Claude Code: Open in Terminal`

4. **Start developing:**
   - Use Claude Code or Codex for AI-assisted development
   - Use `./scripts/git-in.sh <repo> <git-args...>` for git commands inside sub-repositories

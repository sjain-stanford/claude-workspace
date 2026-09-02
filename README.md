# Claude Workspace

A meta workspace for Claude Code and Codex-assisted development across my current ML compiler projects.

## Overview

This workspace is the shared root for local agent configuration, reusable
skills, saved plans/reviews, local Beads task state, git worktrees, and the
independent repositories cloned under `projects/`. The primary active project
is `projects/rocm-systems/emulation/rocjitsu`, an AMD GPU simulation, dynamic
binary translation, and dynamic binary instrumentation toolkit. Older Fusilli
material is retained only as archival context.

## Structure

```
claude-workspace/
├── projects/        # Independent git repositories cloned locally
│   ├── rocm-systems/ # Active ROCm monorepo sparse checkout; rocjitsu lives here
│   ├── docker/
│   └── worktrees/   # Local per-task git worktrees for parallel agents
├── skills/          # Project specific skills and shared references
│   ├── rocjitsu-project/
│   ├── rocjitsu-build-test/
│   ├── fusilli-build-test-lint/
│   ├── bump-fusilli-deps/
│   ├── fusilli-project/
│   ├── gh-address-comments/
│   ├── gh-fix-ci/
│   ├── peanut-review/
│   ├── pr-create/
│   ├── pr-review/
│   ├── self-review/
│   ├── stage-and-commit/
│   ├── review-criteria.md
│   └── llvm-coding-standards.md
├── tools/           # Workspace tools
│   └── peanut-review/
├── plans/           # Mandatory saved implementation plans for larger work
├── reviews/         # Saved PR and self-review outputs
├── .agents/         # Agent configuration
│   └── skills -> ../skills
├── .beads/          # Local-only issue tracker state
├── .claude/         # Claude Code configuration
│   ├── settings.json
│   ├── settings.local.json
│   └── skills -> ../skills
├── .codex/          # Codex local configuration and rules
│   ├── config.toml
│   └── rules/
├── .cursor/         # Cursor local configuration
│   └── cli.json
├── .cache/          # Local caches for workspace tooling and docker/dependency artifacts
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

2. **Clone the required development repositories:**

   ```bash
   # Development image and container launchers
   git clone https://github.com/sjain-stanford/docker.git projects/docker

   # rocjitsu source and required monorepo context
   git clone --filter=blob:none --sparse \
     https://github.com/ROCm/rocm-systems.git projects/rocm-systems
   cd projects/rocm-systems
   git switch develop
   git sparse-checkout set \
     emulation/rocjitsu \
     shared/machine-readable-isa/isa \
     .github
   cd ../..
   ```

   The Docker checkout is required to create the workspace's development
   environment. The machine-readable ISA tree is needed for regeneration, and
   `.github/` provides the current rocjitsu CI and corpus qualification
   workflows. Clone archival repositories separately only when needed.

3. **Launch development container:**
   - Open Cursor or VS Code rooted at `claude-workspace` then launch the development docker container (`./projects/docker/run_docker.sh`)
   - `Ctrl + Shift + P` and select  `Dev Containers: Attach to Running Container`
   - From the new window again open `claude-workspace` and launch the agent (Claude Code or Codex)

4. **Start developing:**

   - Read `projects/rocm-systems/emulation/rocjitsu/CONTRIBUTING.md`.
   - Use `skills/rocjitsu-project/` for project work and
     `skills/rocjitsu-build-test/` for verification.
   - Create branch-backed task worktrees under
     `projects/worktrees/rocm-systems/`; rocjitsu's base branch is `develop`.

## Agent Workflow

For non-trivial feature work, write or reference a plan in `plans/`, decompose it into local Beads tasks, and have worker agents claim tasks with `br update <id> --claim`. Implementation agents should use per-task git worktrees under `projects/worktrees/<repo>/` instead of sharing the canonical `projects/<repo>/` checkout.

Beads state is intentionally local to this machine and is not tracked in git. Plans and reviews are the durable human-readable record; Beads is the executable queue and session handoff memory for short-lived agents.

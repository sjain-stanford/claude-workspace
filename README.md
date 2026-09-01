# Claude Workspace

A meta workspace for Claude Code and Codex-assisted development across my current ML compiler projects.

## Overview

This workspace is the shared root for local agent configuration, reusable skills, saved plans/reviews, local Beads task state, git worktrees, and the independent git repositories cloned under `projects/`. The main active project is Fusilli, with IREE, Torch-MLIR, cuDNN frontend, hipDNN, TheRock, and related tooling checked out as dependencies or API references.

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
│   ├── TheRock/
│   ├── torch-mlir/
│   └── worktrees/   # Local per-task git worktrees for parallel agents
├── skills/          # Project specific skills and shared references
│   ├── build-test-lint/
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
├── tools/           # Workspace tools and upstream synchronization helpers
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
   git clone git@github.com:ROCm/TheRock.git

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
   - Open Cursor or VS Code rooted at `claude-workspace` then launch the development docker container (`./projects/docker/run_docker.sh`)
   - `Ctrl + Shift + P` and select  `Dev Containers: Attach to Running Container`
   - From the new window again open `claude-workspace` and launch the agent (Claude Code or Codex)

4. **Start developing:**
   - Use Claude Code or Codex for AI-assisted development

### peanut-review

Use `skills/peanut-review/` for explicit multi-agent review sessions and
`tools/peanut-review/bin/peanut-review` for the CLI. The imported tool and skill
are ordinary tracked files rather than a submodule. Upstream provenance and
synchronization instructions live in `tools/README.md`.

Create peanut-review PR worktrees under
`.cache/peanut-review/worktrees/<repo>/pr-<number>-<change>/`, name sessions
`<repo>-pr-<number>-<change>`, and run the CLI from inside the worktree. The
shared `.cache/peanut-review/.peanut-review.json` uses the current `$PWD` as
the source checkout and writes persistent session data to
`.cache/peanut-review/sessions/`.

Start the web UI from the `claude-workspace` root, setting `PR_ROOT` to the
configured review root when it differs from the launcher's `$HOME/reviews`
default:

```bash
PR_ROOT="$PWD/.cache/peanut-review/sessions" \
  tools/peanut-review/bin/peanut_review_serve.sh
```

Open `http://127.0.0.1:27183/`. Keep `PR_ROOT` aligned with the `reviewRoot` in
`.peanut-review.json` so the CLI and web UI use the same sessions.

Inside the development container, the launcher binds to `0.0.0.0` so Docker's
published port can reach it. Launch the container with peanut-review forwarding
enabled:

```bash
DOCKER_ENABLE_PEANUT_REVIEW_WEB=1 ./projects/docker/run_docker.sh
```

The Docker launcher publishes port `27183` only on the SSH host's loopback
interface, allowing VSCode Remote SSH to forward it without exposing the UI on
the host's external interfaces. Outside Docker, the peanut-review launcher
binds directly to `127.0.0.1`. Set `PR_HOST` or `PR_PORT` to override these
defaults. `PR_BASE_URL` should only be set when a reverse proxy strips the same
path prefix before forwarding requests.

## Agent Workflow

For non-trivial feature work, write or reference a plan in `plans/`, decompose it into local Beads tasks, and have worker agents claim tasks with `br update <id> --claim`. Implementation agents should use per-task git worktrees under `projects/worktrees/<repo>/` instead of sharing the canonical `projects/<repo>/` checkout.

Beads state is intentionally local to this machine and is not tracked in git. Plans and reviews are the durable human-readable record; Beads is the executable queue and session handoff memory for short-lived agents.

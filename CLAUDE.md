# Claude Workspace

Meta workspace for Claude Code and Codex-assisted development across multiple repositories.

## Workspace Structure

Each subdirectory under `projects/` is an independent git repository. Sub-repos are gitignored in the meta workspace repo and are cloned locally for development and/or to serve as context for local agents.

- `projects/fusilli/` - C++ graph API and JIT engine powered by IREE
  - This is the main project that depends on IREE compiler and runtime
  - Refer `projects/fusilli/README.md` for technical documentation
- `projects/fusilli-benchmarks/` - Central location for Fusilli benchmarks
  - **CRITICAL**: Contains sensitive information (never make public)
  - Refer `projects/fusilli-benchmarks/README.md` for benchmarking instructions
- `projects/iree/` - MLIR enabled compiler and runtime stack
  - This serves as a reference for the compiler and runtime C API interfaces used in Fusilli
- `projects/torch-mlir/` - Torch MLIR dialect and lowering passes
  - This serves as reference for the Torch ASM emitter in Fusilli
- `projects/cudnn-frontend/` - cudNN frontend library for NVIDIA GPU acceleration
  - Fusilli tries to match the frontend API for portability reasons so treat this as the C++ graph API reference
- `projects/hipdnn/` - ROCm hipDNN library for AMD GPU acceleration
  - This is a sparse checkout of the `ROCm/rocm-libraries` monorepo
  - This also serves as reference for the C++ graph API
  - Fusilli gets integrated as a plugin into the hipDNN kernel provider ecosystem
- `projects/TheRock/` - ROCm TheRock source checkout
  - This is the upstream `ROCm/TheRock` repository for ROCm build, packaging, and nightly artifact workflows
  - Use as reference for TheRock releases, ROCm source builds, and Fusilli dependency bump context
- `projects/docker/` - Docker for ML compiler development environment
  - This is the unified development docker for all builds and tests
  - Use as reference but expect Claude/Codex is launched from a dev-container already
- `projects/dot-files/` - Personal configuration files (shell, editor, git, etc.)
  - Setup scripts and dotfile management
- `projects/worktrees/` - Local git worktrees for parallel agent work
  - This directory is intentionally gitignored by `projects/*`
  - Create per-task worktrees here instead of editing the main checkout for feature work
- `plans/` - Saved implementation plans from plan mode (gitignored contents, tracked directory)
- `reviews/` - Saved PR and self-review outputs (gitignored contents, tracked directory)
- `skills/` - Project-specific skills and shared references
- `.agents/` - Agent configuration; includes `skills -> ../skills` symlink for Codex skill discovery
- `.claude/` - Claude Code configuration; includes settings and `skills -> ../skills` symlink
- `.codex/` - Codex local configuration and rules
- `.cursor/` - Cursor local configuration
- `.cache/` - Local caches for workspace tooling and docker/dependency artifacts (gitignored)
- `.beads/` - Local issue tracker state for this workspace
- `CLAUDE.md` - Top-level context for Claude Code
- `AGENTS.md` - Top-level instructions shared with agents (symlink to CLAUDE.md)
- `README.md` - Human-facing workspace overview and setup guide

## Skills

- `skills/build-test-lint/` - Build, test, and lint for Fusilli; use after code changes to verify integrity
- `skills/bump-fusilli-deps/` - Automate bumping IREE and TheRock to latest nightly versions
- `skills/fusilli-project/` - Use when adding new features or debugging issues in Fusilli
- `skills/gh-address-comments/` - Use when addressing GitHub PR or issue comments on the current branch
- `skills/gh-fix-ci/` - Use when debugging and fixing failing GitHub Actions checks for a PR
- `skills/pr-create/` - Use when asked to create a PR (enforces succinct descriptions and PR-body agent attribution)
- `skills/pr-review/` - Use when asked to review a PR from GitHub
- `skills/self-review/` - Use when asked to self-review local branch changes (before creating a PR)
- `skills/stage-and-commit/` - Use when asked to commit local changes (enforces signed commits)
- `skills/review-criteria.md` - Shared review checklist and standards (used by pr-review and self-review)
- `skills/llvm-coding-standards.md` - Reference for C++ coding standards from LLVM (shared across skills)

> **Note**: Skills are symlinked from agent-specific config directories (`.claude/skills` -> `../skills`, `.agents/skills` -> `../skills`) so local agents can discover them while keeping the source files at the repo root for easier editing.

## Sub-Repo Git Usage

Run git commands from the relevant repository directory. For sub-repos under `projects/`, set the command working directory to `projects/<repo>` or its task worktree and use plain `git` commands.

The canonical checkouts under `projects/<repo>/` are for reading, planning, debugging, and gathering context. Before making implementation edits, create or switch to a task-specific worktree under `projects/worktrees/<repo>/...` and do the edits, build, test, lint, commit, and PR work there. Only edit a canonical checkout directly when the user explicitly asks for that exact checkout to be modified.

## Parallel Agent Worktrees

Use git worktrees for autonomous feature work so independent agents do not share one mutable checkout. The canonical checkouts under `projects/<repo>/` are for reading, planning, review, and context only unless the user explicitly directs otherwise. For Bead-driven implementation, create a task worktree under `projects/worktrees/<repo>/<bead-id>-<short-slug>/` before modifying files.

Recommended pattern:

```bash
cd projects/<repo>
git fetch origin
git worktree add \
  ../worktrees/<repo>/<bead-id>-<short-slug> \
  -b users/sambhav/<feature> origin/main
```

Use concise, descriptive branch features, for example
`users/sambhav/matmul-semantics`. Run build, test, lint, commit, and PR
commands from the worktree directory. At handoff, leave the Bead with the
worktree path, branch name, commit/PR state, verification performed, and any
remaining follow-up. Remove completed worktrees only after the branch/PR no
longer needs local follow-up.

## PR Preferences

- Do not include a "Test Plan" section in pull request descriptions unless test coverage is not handled by CI.
- Put active-agent attribution in pull request descriptions as a final footer block, not individual commit messages. Use the active tool/model-specific `Co-authored-by: ...` line followed by the matching `Generated with ...` link.

## Plans

Save implementation plans created during plan mode to `plans/` at claude-workspace root. These provide the durable design record for non-trivial work and are mandatory for larger feature efforts before workers fan out.

After a plan is written, create Beads epics/tasks from it. Each task should reference the plan file and relevant section, include dependencies, acceptance criteria, expected repo/worktree, likely file areas, and verification commands. Workers should read the referenced plan context before claiming a task.

## Reviews

Save PR reviews and self-review outputs to `reviews/` at claude-workspace root. These provide a record of findings, review context, and follow-up decisions for reviewed changes.

## Beads Workflow Integration

This project uses [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`) for issue tracking. A single central `.beads/` in claude-workspace tracks work across all sub-repos — there are no per-repo `.beads/` directories. Prefix bead titles with `[repo-name]` (e.g. `[fusilli]`, `[docker]`) to indicate which sub-repo the work relates to.
CRITICAL: NEVER MENTION BEADS IN CODE. The beads are for your local work tracking only and do not persist. Always write proper TODOs or use github issues for long term/persistent tracking. 95% of all work you do should be tracked in beads. Think of it like a memory.

`.beads/` is intentionally local-only and gitignored because all agents run on this one machine. Do not change `.gitignore` to track Beads state unless the workflow explicitly moves to multiple machines.

### Essential Commands

```bash
# View ready issues (unblocked, not deferred)
br ready

# List and search
br list --status=open # All open issues
br show <id>          # Full issue details with dependencies
br search "keyword"   # Full-text search

# Create and update
br create --title="[repo] Title..." --description="..." --type=task --priority=2
br update <id> --claim
br close <id> --reason="Completed"
br close <id1> <id2>  # Close multiple issues at once
```

### Workflow Pattern

1. **Start**: Run `br ready` to find actionable work
2. **Inspect**: Run `br show <id>` and read any referenced plan file
3. **Claim**: Use `br update <id> --claim` for atomic assignment
4. **Isolate**: Create a git worktree under `projects/worktrees/<repo>/...` for implementation tasks
5. **Work**: Implement the task, adding new Beads for discovered follow-up
6. **Handoff**: Add a Bead comment or notes with branch/worktree path, verification, and next steps
7. **Complete**: Use `br close <id> --reason="Completed"` only after the
   work is pushed and a PR exists, unless the user explicitly says local
   worktree state is enough to close it
8. **Sync**: Always run `br sync --flush-only` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `br ready` shows only unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers 0-4, not words)
- **Types**: task, bug, feature, epic, chore, docs, question
- **Blocking**: `br dep add <issue> <depends-on>` to add dependencies
- **Claiming**: `br update <id> --claim` prevents two parallel agents from taking the same ready task. Persistent agent names are optional; disposable session identity is fine.

### Best Practices

- Check `br ready` at session start to find available work
- Claim with `br update <id> --claim` before editing
- Use one worktree per independent implementation task
- Create new issues with `br create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Keep Beads focused on executable state; keep durable design in `plans/`
- Do not close implementation Beads while code is only present as uncommitted
  or unpushed local work; leave them open/in progress with handoff notes
- Always sync before ending session

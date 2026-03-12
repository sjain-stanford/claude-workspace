# Claude Workspace

Meta workspace for Claude-assisted development across multiple repositories.

## Workspace Structure

Each subdirectory under `projects/` is an independent git repository. Sub-repos are gitignored in the meta workspace repo and are cloned locally for development and/or to serve as context for Claude.

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
- `projects/docker/` - Docker for ML compiler development environment
  - This is the unified development docker for all builds and tests
  - Use as reference but expect Claude is launched from a dev-container already
- `projects/dot-files/` - Personal configuration files (shell, editor, git, etc.)
  - Setup scripts and dotfile management

## Skills

- `skills/build-test-lint/` - Build, test, and lint for Fusilli; use after code changes to verify integrity
- `skills/bump-fusilli-deps/` - Automate bumping IREE and TheRock to latest nightly versions
- `skills/fusilli-project/` - Use when adding new features or debugging issues in Fusilli
- `skills/pr-review/` - Use when asked to review a PR from GitHub
- `skills/self-review/` - Use when asked to self-review local branch changes (before creating a PR)
- `skills/stage-and-commit/` - Use when asked to commit local changes (enforces signed commits and agent co-authorship)
- `skills/review-criteria.md` - Shared review checklist and standards (used by pr-review and self-review)
- `skills/llvm-coding-standards.md` - Reference for C++ coding standards from LLVM (shared across skills)

> **Note**: Skills are symlinked from `.claude/` (`.claude/skills` -> `../skills`) so Claude Code can discover them while keeping the source files at the repo root for easier editing.

## Tool Usage

- Never chain commands with `&&` or `;` when each individual command is already allowed by `Bash(git:*)` or similar rules. Use separate parallel Bash tool calls instead — they run concurrently and don't trigger permission prompts.

## PR Preferences

- Do not include a "Test Plan" section in pull request descriptions unless test coverage is not handled by CI.

## Plans

Save implementation plans created during plan mode to `plans/` at claude-workspace root. These provide a record of design decisions and implementation strategies for non-trivial tasks.

## Beads Workflow Integration

This project uses [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`/`bd`) for issue tracking. A single central `.beads/` in claude-workspace tracks work across all sub-repos — there are no per-repo `.beads/` directories. Prefix bead titles with `[repo-name]` (e.g. `[fusilli]`, `[docker]`) to indicate which sub-repo the work relates to.
CRITICAL: NEVER MENTION BEADS IN CODE. The beads are for your local work tracking only and do not persist. Always write proper TODOs or use github issues for long term/persistent tracking. 95% of all work you do should be tracked in beads. Think of it like a memory.

### Essential Commands

```bash
# View ready issues (unblocked, not deferred)
br ready              # or: bd ready

# List and search
br list --status=open # All open issues
br show <id>          # Full issue details with dependencies
br search "keyword"   # Full-text search

# Create and update
br create --title="[repo] Title..." --description="..." --type=task --priority=2
br update <id> --status=in_progress
br close <id> --reason="Completed"
br close <id1> <id2>  # Close multiple issues at once
```

### Workflow Pattern

1. **Start**: Run `br ready` to find actionable work
2. **Claim**: Use `br update <id> --status=in_progress`
3. **Work**: Implement the task
4. **Complete**: Use `br close <id>`
5. **Sync**: Always run `br sync --flush-only` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `br ready` shows only unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers 0-4, not words)
- **Types**: task, bug, feature, epic, chore, docs, question
- **Blocking**: `br dep add <issue> <depends-on>` to add dependencies

### Best Practices

- Check `br ready` at session start to find available work
- Update status as you work (in_progress → closed)
- Create new issues with `br create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Always sync before ending session

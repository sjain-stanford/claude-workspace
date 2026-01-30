# Claude Workspace

A meta workspace for Claude-assisted development across multiple ML compiler projects.

## Overview

This workspace serves as a unified development environment for working on ML compiler projects (such as Fusilli, IREE) alongside their dependencies and reference implementations.

## Structure

```
claude-workspace/
├── projects/               # Relevant sub-repositories are cloned here
│   ├── fusilli/
│   ├── iree/
│   ├── docker/
│   ├── cudnn-frontend/
│   ├── hipdnn/
│   ├── dot-files/
│   └── ...
├── skills/                 # Project specific skills for agents
│   ├── fusilli_skills.md
│   └── ...
├── CLAUDE.md               # Top level context for agents
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
   # Clone the projects to work with
   cd projects/
   git clone <fusilli-repo-url> fusilli
   git clone <iree-repo-url> iree
   # ... clone other repos as needed
   ```

3. **Launch development container:**
   - Open Cursor IDE, launch docker container `./docker/run_docker.sh`
   - `Ctrl + Shift + P` and select  `Dev Containers: Attach to Running Container`
   - Open `claude-workspace` in Cursor IDE
   - Launch Claude Code from Cursor: `Claude Code: Open in Terminal`

4. **Start developing:**
   - Use Claude Code for AI-assisted development

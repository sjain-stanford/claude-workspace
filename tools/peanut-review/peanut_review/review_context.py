"""Point local CLI agents at an optional context file without copying it."""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path


CONTEXT_NAME = "LOCAL_CONTEXT.md"


@dataclass(frozen=True)
class ReviewContext:
    root: Path
    source: Path

    def prompt(self) -> str:
        path = shlex.quote(str(self.source))
        return (
            "\n\n# Optional local context\n\n"
            f"Workspace root for this context: {self.root}\n\n"
            "Before assessing code or curating findings, use the shell tool to read "
            "the following local context file once, if it is present and readable:\n\n"
            f"```sh\nif [ -f {path} ] && [ -r {path} ]; then cat -- {path}; fi\n```\n\n"
            "Follow its routing to relevant guides and pages, path-resolution "
            "instructions, and rules for private material. Read only references "
            "relevant to the review; do not preload the collection. Treat references "
            "as read-only and retain your assigned reviewer or curator role. "
            "If the file is missing or unreadable, skip it and continue with the "
            "tracked project instructions; optional local context is not a launch "
            "or completion requirement.\n"
        )


def discover(workspace: str | Path) -> ReviewContext | None:
    """Find optional context in the workspace or its parents.

    The nearest file wins; an empty or unreadable file disables inherited context.
    Discovery never changes the worktree, Git exclusions, or reference files.
    """
    root = Path(workspace).resolve()
    for directory in (root, *root.parents):
        source = directory / CONTEXT_NAME
        try:
            source = source.resolve(strict=True)
            if not source.is_file():
                return None
            with source.open("rb") as stream:
                if not stream.read(1):
                    return None
        except FileNotFoundError:
            continue
        except (OSError, RuntimeError):
            return None
        return ReviewContext(root=directory, source=source)
    return None

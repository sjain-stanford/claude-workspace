# Workspace tools

## peanut-review

`peanut-review/` and `../skills/peanut-review/` are a filtered-history port of
the corresponding paths in
[`kuhar/agent-workspace`](https://github.com/kuhar/agent-workspace). They are
normal files in this repository, not a submodule, and have no runtime dependency
on an `agent-workspace` checkout.

The source revision, filtered tip, retained paths, and downstream patches are
recorded in `peanut-review.upstream.json`. Use `peanut-review-upstream` to manage
the port:

```bash
tools/peanut-review-upstream status
tools/peanut-review-upstream pull --ref origin/main
tools/peanut-review-upstream export \
  --base <base> --head HEAD --output /tmp/peanut-review.patch
```

`status` defaults to the local `projects/agent-workspace` checkout. `pull`
requires a clean claude-workspace task branch and `git-filter-repo`; it repeats
the original two-path filter and creates a signed merge commit. An upstream
history rewrite is reported for manual inspection instead of being merged.

Keep workspace-specific integration outside the two imported paths when
possible. Changes intended for upstream should stay path-local so the exported
patch applies directly to `agent-workspace`.

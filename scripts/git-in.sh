#!/bin/sh
# Run git commands in a subdirectory without cd.
# Usage: ./git-in.sh <dir> <git-args...>
# Example: ./git-in.sh projects/fusilli status
dir="$1"; shift
git -C "$dir" "$@"

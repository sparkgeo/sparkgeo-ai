#!/usr/bin/env bash
#
# cleanup-workspace.sh — Remove a workspace made by prepare-workspace.sh.
#
# Usage:
#   cleanup-workspace.sh <workspace-json-file>
#
# The argument is a file that holds the JSON printed by prepare-workspace.sh.

set -euo pipefail

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    printf 'Usage: cleanup-workspace.sh <workspace-json-file>\n' >&2
    exit 2
fi

path="$(jq -r '.path' "$1")"
mode="$(jq -r '.mode' "$1")"
repo_dir="$(jq -r '.repo_dir' "$1")"

# Refuse to delete anything that is not a spk-code-review workspace.
case "$path" in
    */spk-code-review/*) ;;
    *)
        printf 'Refusing to remove %s: not under a spk-code-review directory.\n' "$path" >&2
        exit 1
        ;;
esac

if [ "$mode" = "worktree" ]; then
    git -C "$repo_dir" worktree remove --force "$path"
else
    rm -rf -- "$path"
fi

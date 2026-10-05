#!/usr/bin/env bash
#
# prepare-workspace.sh — Check out the head commit of a pull request into an
# isolated directory, so reviewers read the code as it is in the PR.
#
# If the current directory is a clone of <owner>/<repo>, the script adds a
# detached git worktree. Otherwise it makes a partial clone with `gh`.
#
# The script never runs code from the PR.
#
# Usage:
#   prepare-workspace.sh <owner/repo> <pr-number> <head-sha> <base-ref> <dest-dir>
#
# On success, prints one JSON object to stdout:
#   {"path": "...", "mode": "worktree|clone", "head_sha": "...", "base_sha": "...", "repo_dir": "..."}
# On failure, prints an error to stderr and exits non-zero.

set -euo pipefail

err() {
    printf '%s\n' "$*" >&2
}

if [ "$#" -ne 5 ]; then
    err "Usage: prepare-workspace.sh <owner/repo> <pr-number> <head-sha> <base-ref> <dest-dir>"
    exit 2
fi

repo="$1"
number="$2"
head_sha="$3"
base_ref="$4"
dest="$5"

if [ -e "$dest" ]; then
    err "Destination already exists: $dest"
    exit 1
fi
mkdir -p "$(dirname "$dest")"

# Find a local remote that points at <owner>/<repo>, if we are inside a clone.
remote=""
repo_dir=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    repo_dir="$(git rev-parse --show-toplevel)"
    while read -r name url; do
        # Match github.com:owner/repo(.git) and github.com/owner/repo(.git), case-insensitive.
        if printf '%s' "$url" | grep -qiE "github\.com[:/]${repo}(\.git)?/?$"; then
            remote="$name"
            break
        fi
    done < <(git remote -v | awk '$3 == "(fetch)" { print $1, $2 }')
fi

if [ -n "$remote" ]; then
    mode="worktree"
    git -C "$repo_dir" fetch --quiet "$remote" "pull/${number}/head" "+refs/heads/${base_ref}:refs/remotes/${remote}/${base_ref}" >&2
    git -C "$repo_dir" worktree add --quiet --detach "$dest" "$head_sha" >&2
    base_tip="refs/remotes/${remote}/${base_ref}"
else
    mode="clone"
    repo_dir="$dest"
    gh repo clone "$repo" "$dest" -- --quiet --filter=blob:none --no-checkout >&2
    git -C "$dest" fetch --quiet origin "pull/${number}/head" "+refs/heads/${base_ref}:refs/remotes/origin/${base_ref}" >&2
    git -C "$dest" checkout --quiet --detach "$head_sha" >&2
    base_tip="refs/remotes/origin/${base_ref}"
fi

actual_sha="$(git -C "$dest" rev-parse HEAD)"
if [ "$actual_sha" != "$head_sha" ]; then
    err "Workspace HEAD ($actual_sha) does not match PR head ($head_sha). The PR may have been updated. Re-run the review."
    exit 1
fi

base_sha="$(git -C "$dest" merge-base HEAD "$base_tip")"

jq -n \
    --arg path "$dest" \
    --arg mode "$mode" \
    --arg head_sha "$actual_sha" \
    --arg base_sha "$base_sha" \
    --arg repo_dir "$repo_dir" \
    '{path: $path, mode: $mode, head_sha: $head_sha, base_sha: $base_sha, repo_dir: $repo_dir}'

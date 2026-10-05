#!/usr/bin/env bash
#
# github-checks.sh — Validate prerequisites for PR review workflows.
#
# Performs three checks:
#   1. GitHub CLI (`gh`) is installed.
#   2. The user is authenticated with `gh`.
#   3. (Optional) A PR number or URL was supplied; extracts and prints the PR
#      number. If no argument is supplied, only checks 1 and 2 are performed.
#
# Usage:
#   github-checks.sh [<pr-number|pr-url>]
#
# On success with an argument, prints the parsed PR number to stdout and exits 0.
# On success without an argument, prints nothing and exits 0.
# On failure, prints an error to stderr and exits non-zero.

set -euo pipefail

err() {
    printf '%s\n' "$*" >&2
}

if ! command -v gh >/dev/null 2>&1; then
    err "The GitHub CLI (\`gh\`) is required but not installed. Install it from https://cli.github.com"
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    err "You are not authenticated with the GitHub CLI. Run \`gh auth login\` and try again."
    exit 1
fi

if [ "$#" -lt 1 ] || [ -z "${1:-}" ]; then
    # No argument supplied: gh installed + authenticated checks already passed.
    exit 0
fi

arg="$1"
pr_number=""

if [[ "$arg" =~ ^[0-9]+$ ]]; then
    pr_number="$arg"
elif [[ "$arg" =~ ^https?://github\.com/[^/]+/[^/]+/pull/([0-9]+)(/.*)?$ ]]; then
    pr_number="${BASH_REMATCH[1]}"
else
    err "Could not parse '$arg' as a PR number or GitHub PR URL."
    err "Expected a number (e.g. 123) or URL (e.g. https://github.com/owner/repo/pull/123)."
    exit 1
fi

printf '%s\n' "$pr_number"

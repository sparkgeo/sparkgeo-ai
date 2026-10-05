#!/usr/bin/env bash
#
# run-scanners.sh — Run the deterministic scanners that are installed on this
# machine against a PR workspace, and write a summary.
#
# Supported scanners (each one is optional):
#   gitleaks  secrets in the commits between base and head
#   semgrep   static analysis on changed files (rules: $SEMGREP_CONFIG, default p/default)
#   trivy     vulnerable dependencies, misconfiguration, and secrets in the workspace
#
# The script never runs the project's own build, tests, or install scripts.
# A missing or failing scanner never fails the script.
#
# Usage:
#   run-scanners.sh <workspace-dir> <base-sha> <out-dir>
#
# Writes <out-dir>/<scanner>.json for each scanner that ran, and
# <out-dir>/summary.json. Prints the summary to stdout.

set -uo pipefail

if [ "$#" -ne 3 ]; then
    printf 'Usage: run-scanners.sh <workspace-dir> <base-sha> <out-dir>\n' >&2
    exit 2
fi

ws="$1"
base="$2"
out="$3"
mkdir -p "$out"

summary='{}'

record() {
    # record <scanner> <status> <findings-count-or-null> <note>
    summary="$(jq -c --arg s "$1" --arg st "$2" --argjson n "$3" --arg note "$4" \
        '. + {($s): {status: $st, findings: $n, note: $note}}' <<<"$summary")"
}

mapfile -t changed < <(git -C "$ws" diff --name-only --diff-filter=ACMR "$base" HEAD)

# gitleaks
if command -v gitleaks >/dev/null 2>&1; then
    report="$out/gitleaks.json"
    if gitleaks git --no-banner --exit-code 0 --log-opts="${base}..HEAD" \
            --report-format json --report-path "$report" "$ws" >/dev/null 2>&1 \
        || gitleaks detect --no-banner --exit-code 0 --source "$ws" --log-opts="${base}..HEAD" \
            --report-format json --report-path "$report" >/dev/null 2>&1; then
        record gitleaks ok "$(jq 'length' "$report" 2>/dev/null || echo null)" ""
    else
        record gitleaks error null "gitleaks exited with an error"
    fi
else
    record gitleaks not_installed null ""
fi

# semgrep
if command -v semgrep >/dev/null 2>&1; then
    if [ "${#changed[@]}" -eq 0 ]; then
        record semgrep skipped null "no added or modified files"
    else
        report="$out/semgrep.json"
        if (cd "$ws" && semgrep scan --quiet --metrics off --config "${SEMGREP_CONFIG:-p/default}" \
                --json --output "$report" -- "${changed[@]}") >/dev/null 2>&1; then
            record semgrep ok "$(jq '.results | length' "$report" 2>/dev/null || echo null)" "config ${SEMGREP_CONFIG:-p/default}"
        else
            record semgrep error null "semgrep exited with an error"
        fi
    fi
else
    record semgrep not_installed null ""
fi

# trivy
if command -v trivy >/dev/null 2>&1; then
    report="$out/trivy.json"
    if trivy fs --quiet --scanners vuln,misconfig,secret --format json --output "$report" "$ws" >/dev/null 2>&1; then
        record trivy ok "$(jq '[.Results[]? | (.Vulnerabilities // []), (.Misconfigurations // []), (.Secrets // []) | length] | add // 0' "$report" 2>/dev/null || echo null)" "whole workspace"
    else
        record trivy error null "trivy exited with an error"
    fi
else
    record trivy not_installed null ""
fi

jq '.' <<<"$summary" | tee "$out/summary.json"

#!/usr/bin/env bash
#
# diff-line-ranges.sh — List the line ranges in a unified diff where GitHub
# accepts inline review comments.
#
# GitHub accepts an inline comment on any line inside a diff hunk. The RIGHT
# side uses new-file line numbers. The LEFT side uses old-file line numbers.
#
# Usage:
#   gh pr diff 123 | diff-line-ranges.sh
#
# Prints one JSON object to stdout:
#   {"path/to/file.py": {"RIGHT": [[10, 24], [80, 95]], "LEFT": [[10, 20]]}, ...}

set -euo pipefail

awk '
    # File headers appear only between "diff --git" and the first hunk.
    # Inside a hunk, a removed line such as "-- comment" looks like "--- comment".
    /^diff --git / { in_header = 1; next }
    in_header && /^--- / {
        old = substr($0, 5); sub(/^a\//, "", old)
        next
    }
    in_header && /^\+\+\+ / {
        new = substr($0, 5); sub(/^b\//, "", new)
        file = (new == "/dev/null") ? old : new
        next
    }
    /^@@ / {
        in_header = 0
        # @@ -a,b +c,d @@
        split($2, o, ","); split($3, n, ",")
        a = substr(o[1], 2) + 0; b = (o[2] == "") ? 1 : o[2] + 0
        c = substr(n[1], 2) + 0; d = (n[2] == "") ? 1 : n[2] + 0
        if (d > 0) printf "%s\tRIGHT\t%d\t%d\n", file, c, c + d - 1
        if (b > 0) printf "%s\tLEFT\t%d\t%d\n", file, a, a + b - 1
    }
' | jq -R -s '
    split("\n")
    | map(select(length > 0) | split("\t"))
    | reduce .[] as [$f, $side, $s, $e] ({};
        .[$f][$side] += [[($s | tonumber), ($e | tonumber)]])
'

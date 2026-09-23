# Structured Review Output Format

This document defines the structured JSON output format that all review agents must follow when reporting findings. It ensures consistent, machine-parseable output that the `spk-reviewer-aggregator` agent can aggregate and that developers can navigate in their IDE.

The canonical JSON Schema is at `${CLAUDE_PLUGIN_ROOT}/templates/review-schema.json`.

Specialist output is treated as **candidate findings**: before anything is posted to GitHub, severe candidates and lower-confidence warnings are independently checked by a verifier agent (`spk-reviewer-verifier` or `spk-reviewer-verifier-deep`, output schema at `${CLAUDE_PLUGIN_ROOT}/templates/verification-schema.json`). Candidates the verifier refutes are dropped. This means specialists should report every genuine concern with honest `confidence` and concrete `evidence` — the evidence is what the verifier starts from — rather than self-censoring or inflating certainty.

## Output Structure

Every specialist agent must return a **single JSON code block** as its complete output. No text outside the JSON block.

```json
{
  "version": "1.0",
  "agent": {
    "name": "<agent-codename>",
    "role": "<functional-role>"
  },
  "summary": {
    "overall_assessment": "1-2 sentence summary of findings",
    "blocking": false,
    "counts": {
      "severe": 0,
      "warning": 0,
      "question": 0,
      "info": 0
    }
  },
  "comments": []
}
```

## Agent Identity

Each agent uses its assigned name and role:

| Codename                     | Role              |
|------------------------------|-------------------|
| spk-reviewer-frontend            | frontend          |
| spk-reviewer-ui                  | ui_design         |
| spk-reviewer-ux                  | ux_accessibility  |
| spk-reviewer-backend-python      | backend           |
| spk-reviewer-python-quality      | code_quality      |
| spk-reviewer-tests               | testing           |
| spk-reviewer-devops              | infrastructure    |
| spk-reviewer-security            | security          |
| spk-reviewer-database            | database          |
| spk-reviewer-docs                | documentation     |
| spk-reviewer-general-purpose     | general           |
| spk-reviewer-aggregator          | aggregator        |

## Comment Types

### Inline Comment — File + Line Range

Use `inline_comment` when the finding points to a specific location in a file. This is the preferred type because it enables direct IDE navigation.

```json
{
  "id": "CR-001",
  "type": "inline_comment",
  "level": "warning",
  "category": "correctness",
  "confidence": "high",
  "blocking": false,
  "summary": "Token expiry check appears inverted",
  "comment": "The new condition returns success when the token has already expired. The success path now executes when isExpired(token) is true.",
  "suggestion": "Reverse the comparison: `if (!isExpired(token))` or rename the helper so its semantics match the call site.",
  "suggestion_consequences": "If other call sites rely on the current (inverted) behavior, reversing the check here will break them too — audit all usages of isExpired() before applying.",
  "why_it_matters": "Expired tokens may be treated as valid, allowing unauthorized access.",
  "evidence": [
    "Line 120: `if (isExpired(token)) { return { valid: true }; }`"
  ],
  "references": ["CWE-613"],
  "location": {
    "file_path": "src/auth/validate.ts",
    "side": "new",
    "start_line": 118,
    "end_line": 124,
    "symbol": "validateToken"
  },
  "dedupe_key": "correctness|token_expiry_inverted|src/auth/validate.ts|validateToken|118-124"
}
```

### Diff Comment — Cross-File or Overall

Use `diff_comment` for findings that span multiple files, concern the overall change, or don't map to a single location.

```json
{
  "id": "CR-002",
  "type": "diff_comment",
  "level": "warning",
  "category": "test_gap",
  "confidence": "medium",
  "blocking": false,
  "summary": "No regression test covers the new expiry branch",
  "comment": "Auth validation logic changed but no test file updates are visible in the diff for expired-token behavior.",
  "suggestion": "Add tests for valid, expired, and boundary-case token timestamps.",
  "why_it_matters": "Without coverage, this branch is easy to regress silently.",
  "applies_to": {
    "file_paths": ["src/auth/validate.ts", "test/auth/validate.test.ts"],
    "symbols": ["validateToken"]
  },
  "related_ids": ["CR-001"],
  "dedupe_key": "test_gap|missing_expiry_tests|src/auth/validate.ts|validateToken"
}
```

## Field Reference

### level — Finding Severity

| Level      | Meaning                                    | blocking | suggestion required |
|------------|--------------------------------------------|----------|---------------------|
| `info`     | Informational note, no action needed       | false    | no                  |
| `question` | Needs clarification from the author        | false    | no                  |
| `warning`  | Should fix, not blocking merge             | false    | **yes**             |
| `severe`   | Must fix before merge                      | true     | **yes**             |

Do not report praise or positive feedback at any level. Every finding must be actionable or informative — if a comment's only purpose is to compliment the code, omit it entirely (do not relabel it as `info`).

### category — Finding Domain

| Category          | When to use                                              |
|-------------------|----------------------------------------------------------|
| `correctness`     | Logic bugs, wrong behavior, edge case failures           |
| `security`        | Vulnerabilities, secrets, injection, auth gaps           |
| `performance`     | Hot paths, N+1 queries, unnecessary allocations          |
| `maintainability` | Brittle coupling, poor abstraction, tech debt            |
| `readability`     | Unclear naming, confusing structure, missing context      |
| `style`           | Formatting, conventions, linting violations               |
| `test_gap`        | Missing or inadequate test coverage                      |
| `docs`            | Missing or inaccurate documentation                      |
| `dependency`      | Package risks, version issues, unnecessary deps          |
| `api_contract`    | Breaking changes, schema mismatches, type misalignment   |
| `concurrency`     | Race conditions, deadlocks, async misuse                 |
| `error_handling`  | Missing error handling, swallowed exceptions, bad UX     |

### confidence

- `high` — Clearly an issue based on the code
- `medium` — Likely an issue but depends on context not visible in the diff
- `low` — Possible concern, worth a second look

### location (inline_comment only)

| Field          | Required | Description                                              |
|----------------|----------|----------------------------------------------------------|
| `file_path`    | yes      | Relative path from repo root                             |
| `start_line`   | yes      | First line of the relevant range                         |
| `end_line`     | yes      | Last line (same as start_line for single-line)           |
| `side`         | no       | `new` (default) for additions, `old` for deletions       |
| `start_column` | no       | Column start (requires end_column)                       |
| `end_column`   | no       | Column end (requires start_column)                       |
| `symbol`       | no       | Function/class/variable name for IDE symbol search       |
| `hunk_header`  | no       | The `@@` hunk header from the diff                       |

### applies_to (diff_comment only)

| Field        | Description                                |
|--------------|--------------------------------------------|
| `file_paths` | Array of files this finding relates to     |
| `symbols`    | Array of function/class/variable names     |

### Other Fields

| Field            | Required       | Description                                                |
|------------------|----------------|------------------------------------------------------------|
| `id`             | yes            | Sequential `CR-NNN`, unique within this agent's review     |
| `blocking`       | yes            | `true` only for severe findings                            |
| `suggestion`     | warning/severe | How to fix the issue (can include code blocks)             |
| `suggestion_consequences` | no    | Trade-offs, side effects, or risks of following the suggestion |
| `why_it_matters` | warning/severe | Impact if not addressed                                    |
| `evidence`       | no             | Array of code quotes or context supporting the finding     |
| `references`     | no             | CWE IDs, OWASP refs, doc URLs                             |
| `related_ids`    | no             | IDs of related findings (same or other agent reviews)      |
| `dedupe_key`     | no             | Stable key for the aggregator to merge duplicates across agents |

## Suggestion Consequences

When your suggestion could itself cause problems, include a `suggestion_consequences` field describing the trade-offs, side effects, or risks. This helps the developer make an informed decision rather than blindly applying a fix that introduces a new issue.

Include `suggestion_consequences` when the suggestion:
- Could break other code (changing a function signature, renaming a column, altering an API contract)
- Has operational impact (table locks during migration, increased memory usage, slower cold starts)
- Involves a trade-off (security vs. usability, performance vs. readability)
- Requires coordinated changes elsewhere (deploy ordering, config changes, downstream consumers)

Omit it when the suggestion is straightforward with no meaningful side effects (e.g., fixing a typo, adding a missing test, correcting indentation).

## Dedupe Key Format

Use a pipe-separated string: `category|issue_slug|primary_file|symbol|line_range`

Examples:
- `correctness|token_expiry_inverted|src/auth/validate.ts|validateToken|118-124`
- `security|sql_injection|src/api/users.py|get_user|45-52`
- `test_gap|missing_expiry_tests|src/auth/validate.ts|validateToken`

The key should be stable enough that two agents flagging the same issue produce the same (or very similar) key for the aggregator agent to merge them.

## IDE Navigation Tips

To help developers jump directly to findings in their IDE:

1. **Always use relative paths** from the repo root (e.g., `src/auth/validate.ts`, not `/home/user/project/src/auth/validate.ts`)
2. **Prefer inline_comment** over diff_comment when a finding maps to a specific location
3. **Include the symbol name** — most IDEs support "Go to Symbol" search
4. **Use tight line ranges** — point to the specific lines, not the whole function
5. **Set start_line = end_line** for single-line findings

## When to Use Each Comment Type

- **inline_comment**: The finding points to specific code at a known file and line range. This is the default — use it whenever possible.
- **diff_comment**: The finding is about a pattern across multiple files, a missing file/test that should exist, an architectural concern, or something that doesn't map to a single location.

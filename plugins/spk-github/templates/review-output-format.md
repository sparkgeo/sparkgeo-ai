# Structured Review Output Format

This document defines the structured JSON output format that all review agents must follow when reporting findings. It ensures consistent, machine-parseable output that the `spk-reviewer-aggregator` agent can aggregate and that developers can navigate in their IDE.

The canonical JSON Schema is at `${CLAUDE_PLUGIN_ROOT}/templates/review-schema.json`.

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
      "question": 0
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
  "summary": "Expired tokens pass validation",
  "comment": "This returns `valid: true` when `isExpired(token)` is true. The check is reversed.",
  "suggestion": "Change the condition to `if (!isExpired(token))`.",
  "suggestion_consequences": "Other callers may depend on the current behavior. Check all uses of `isExpired()` first.",
  "why_it_matters": "Users with expired tokens can get access.",
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
  "summary": "No test for expired tokens",
  "comment": "The token check changed, but no test covers expired tokens.",
  "suggestion": "Add tests for a valid token, an expired token, and a token that expires at the current time.",
  "why_it_matters": "A future change can break this check and no test will fail.",
  "applies_to": {
    "file_paths": ["src/auth/validate.ts", "test/auth/validate.test.ts"],
    "symbols": ["validateToken"]
  },
  "related_ids": ["CR-001"],
  "dedupe_key": "test_gap|missing_expiry_tests|src/auth/validate.ts|validateToken"
}
```

## Writing Style

Developers read these comments on GitHub. Write so a busy reader understands the finding in a few seconds.

- Use short sentences. Put one idea in each sentence.
- Use simple, common words. Write "use", not "utilize". Write "because", not "due to the fact that".
- Use active voice. Write "This function returns null", not "Null is returned by this function".
- Start with the problem. Do not restate what the code does before you get to the problem.
- Name the exact thing: the function, variable, line, or value. Do not write "this logic" or "the implementation".
- Be direct. Do not hedge with "might potentially", "it seems that", or "consider possibly".
- Keep `summary` under 80 characters. Make it a plain statement of the problem, not a category label.
- Keep `comment` to 1-3 sentences. Keep `suggestion` and `why_it_matters` to 1-2 sentences each.
- Do not repeat the same point in `comment`, `suggestion`, and `why_it_matters`. Each field adds new information.
- Do not use filler such as "Great job, but", "It is worth noting that", or "In order to".
- Do not use em dashes. Use a period or a comma.
- Add a diagram to explain a concept when it makes sense.

| Avoid | Prefer |
|-------|--------|
| "The current implementation may potentially fail to adequately handle scenarios in which the input value is null." | "This crashes when `user` is null." |
| "It would be advisable to consider leveraging a parameterized query to mitigate injection risk." | "Use a parameterized query. The current string format allows SQL injection." |

## Field Reference

### level — Finding Severity

| Level      | Meaning                                    | blocking | suggestion required |
|------------|--------------------------------------------|----------|---------------------|
| `question` | Needs clarification from the author        | false    | no                  |
| `warning`  | Should fix, not blocking merge             | false    | **yes**             |
| `severe`   | Must fix before merge                      | true     | **yes**             |

Report only findings the author can act on or must answer. Do not report praise, positive feedback, or notes that need no action. If a finding needs no action, omit it.

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

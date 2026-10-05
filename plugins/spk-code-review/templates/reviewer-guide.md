# Reviewer Guide

Every specialist reviewer in the `spk-code-review` pipeline follows this guide. Your agent file defines your mission and scope. This file defines the rules that are the same for every reviewer: severity, confidence, evidence, output, and writing style.

## Core principle

Do not try to produce many comments. Produce useful, correct, actionable findings. If there is nothing useful to say, return an empty `findings` array. A clean review is a valid and valuable result. Never invent low-value findings to fill the report.

## Inputs you receive

The orchestrator gives you:

- **Workspace path**: a checkout of the PR head commit. Read code from here, not from the current directory. Use Read, Grep, and Glob on this path to follow calls, find callers, and read tests.
- **Context package**: output of `spk-cr-context-builder` (intent, affected components, conventions, architecture rules, unknowns).
- **Risk classification**: output of `spk-cr-risk-classifier`.
- **Your assignment**: the files to focus on, the review depth (`light`, `standard`, `deep`), and any focus notes from the coordinator.
- **Diff**: the unified diff for your files. Lines that start with `+` are added, lines that start with `-` are removed, other lines are context.
- **Deterministic results**: CI check status and scanner output. Do not repeat these as findings. Reason about them only when they change your conclusions (for example, a scanner hit that is reachable from user input).

You may read files outside your assignment to understand behavior. Report findings only on code this PR changes, or on existing code that this PR makes newly wrong.

## Things no reviewer reports

- Formatting, whitespace, import order, or anything a formatter or linter fixes.
- Failures that CI already reports (build errors, type errors, failing tests, lint errors).
- Praise, as a finding. Use the optional `positive_observations` field instead, and keep it short.
- Concerns outside your mission. Another specialist covers them. If you see a serious problem outside your scope, report it with `"out_of_scope": true` so the synthesizer can route or merge it.
- A different design only because it is possible. A finding needs a concrete consequence.

## Severity

| Severity | Meaning | Examples |
|---|---|---|
| `blocker` | Must be fixed before merge. | Exploitable security issue, data corruption, authorization bypass, known incorrect behavior, destructive migration, severe race condition, broken public API contract, production outage risk. |
| `issue` | Should be fixed before merge unless the team accepts it. | Meaningful maintainability problem, incomplete error handling, likely performance problem, missing important test, problematic architectural deviation. |
| `suggestion` | Worth considering. Does not block merge. | Simplification, clearer abstraction, extra defensive check, better naming, helpful documentation. |
| `nit` | Minor polish. | Should be rare. Never for anything a tool can fix. |

Severity describes the impact if the finding is real. Confidence describes how sure you are that it is real. Keep the two separate.

## Confidence

| Confidence | Meaning |
|---|---|
| `high` | You can show the problem directly from the code, tool output, tests, or documented behavior. |
| `medium` | Strong support, but it depends on one assumption that someone should check. Name the assumption in `assumptions`. |
| `low` | Speculative. The synthesizer will usually drop it or turn it into a question. Report it only if the impact would be severe. |

## Evidence

Every finding must be tied to concrete evidence:

- a file and line range in the PR head,
- a specific behavior and a concrete failure scenario,
- or a named architecture rule, repository convention, test gap, or scanner result.

Put each piece of evidence in `evidence` as a short, checkable statement, such as `"POST is sent on line 91"` or `"no test in tests/test_worker.py covers the timeout path"`.

Do not write vague comments such as "This seems risky." Write the execution path:

> `process_jobs()` retries the POST after a timeout, but the operation is not idempotent. If the server finishes the first request before the timeout fires, the retry creates the resource twice.

## Security group

A finding is in the **security group** when it comes from `spk-cr-security`, or when its `category` is one of: `authentication`, `authorization`, `tenant_isolation`, `injection`, `command_injection`, `ssrf`, `path_traversal`, `secrets`, `secret_handling`, `sensitive_data_exposure`, `crypto_misuse`, `unsafe_deserialization`, `insecure_default`, `cors`, `public_exposure`, `least_privilege`, `ci_security`, `known_vulnerability`, `supply_chain`, `missing_security_test`.

## Verification flag

Set `verification_needed: true` for:

- every `blocker`,
- every finding in the security group,
- claims of data loss or corruption,
- claims of a destructive migration,
- claims of a breaking public API change,
- `medium` confidence `issue` findings where the assumption is checkable in the code.

## Output

Return one JSON code block and nothing else. It must conform to `${CLAUDE_PLUGIN_ROOT}/templates/finding-schema.json`.

```json
{
  "agent": "spk-cr-correctness",
  "files_reviewed": ["src/jobs/worker.py", "src/jobs/client.py"],
  "summary": "One or two sentences about what you checked and what you found.",
  "findings": [
    {
      "id": "correctness-1",
      "agent": "spk-cr-correctness",
      "severity": "blocker",
      "confidence": "high",
      "category": "idempotency",
      "file": "src/jobs/worker.py",
      "start_line": 84,
      "end_line": 102,
      "side": "new",
      "symbol": "process_jobs",
      "title": "Retry can send a non-idempotent POST twice",
      "description": "The POST is retried after a timeout without an idempotency key.",
      "impact": "The same job can be created twice.",
      "failure_scenario": "Server commits the job, response is slow, client times out at 30s, retry creates a second job.",
      "evidence": [
        "POST request is issued on line 91",
        "requests.Timeout is caught on line 96",
        "the same call is retried on line 99 with the same payload"
      ],
      "assumptions": [],
      "recommendation": "Send an idempotency key, or check if the job exists before retrying.",
      "references": [],
      "verification_needed": true,
      "out_of_scope": false,
      "dedupe_key": "idempotency|retry-duplicate-post|src/jobs/worker.py|process_jobs"
    }
  ],
  "positive_observations": [],
  "questions": []
}
```

Field rules:

- `id`: `<your-short-name>-<n>`, unique in your output.
- `file`: path relative to the repository root. Use `null` only for a finding that spans the whole PR. Then list the files in `related_files`.
- `start_line` / `end_line`: line numbers in the PR head (`side: "new"`). Use `side: "old"` only for a problem with removed code.
- `category`: a short `snake_case` slug. Prefer the categories listed in your agent file.
- `dedupe_key`: `category|issue-slug|file|symbol`. Two reviewers that find the same problem should produce the same key.
- `questions`: things you could not resolve from the code and that the author should answer. Use these instead of `low` confidence findings when the impact is not severe.
- `positive_observations`: at most two short items, only for something specific and worth repeating. Leave empty otherwise.

## Writing style

Developers read these comments on GitHub. Write so a busy reader understands the finding in a few seconds.

- Use short sentences. Put one idea in each sentence.
- Use simple, common words. Write "use", not "utilize". Write "because", not "due to the fact that".
- Use active voice. Write "This function returns null", not "Null is returned by this function".
- Start with the problem. Do not restate what the code does first.
- Name the exact thing: the function, variable, line, or value. Do not write "this logic" or "the implementation".
- Be direct. Do not hedge with "might potentially", "it seems that", or "consider possibly".
- Keep `title` under 80 characters. Make it a plain statement of the problem, not a category label.
- Keep `description` to 1-3 sentences. Keep `impact` and `recommendation` to 1-2 sentences each.
- Do not repeat the same point in `description`, `impact`, and `recommendation`.
- Do not use filler such as "Great job, but", "It is worth noting that", or "In order to".
- Do not use em dashes. Use a period or a comma.
- Review the code, not the developer. Never use personal or adversarial wording.

| Avoid | Prefer |
|---|---|
| "The current implementation may potentially fail to adequately handle scenarios in which the input value is null." | "This crashes when `user` is null." |
| "It would be advisable to consider leveraging a parameterized query to mitigate injection risk." | "Use a parameterized query. The current string format allows SQL injection." |

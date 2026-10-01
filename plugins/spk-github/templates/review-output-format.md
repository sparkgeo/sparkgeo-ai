# Review Output Contract

Every review agent writes one JSON file. The tool at `${CLAUDE_PLUGIN_ROOT}/scripts/spk_review.py` validates it, merges it, counts it, and renders it. You never write counts, blocking flags, or summaries. You write findings with evidence.

Schemas: `review-schema.json` (specialist output), `review-aggregate-schema.json` (aggregator output), and `review-common-schema.json` (shared definitions).

## What to publish

A finding is published only when all three hold:

1. **Concrete trigger.** You can name the input, state, or call path that causes it.
2. **Demonstrated consequence.** You can say what breaks for users, data, or operators.
3. **Evidence at the reviewed revision.** You quote the code at the snapshot, with path and line.

Do not raise these in the default review:

| Publish | Investigate first or leave out |
|---|---|
| Correctness bugs this PR introduces, with a failing case | Hypothetical edge cases with no reachable trigger |
| API, schema, migration, deployment, or config mismatches across a boundary | Broad architectural preferences with no concrete consequence |
| Proven authorization gaps, data loss, or concurrency failures | Generic security hardening, or CVE claims with no advisory source |
| Broken user flows or evidenced accessibility regressions | Styling preferences and unmeasured visual claims |
| One specific missing regression test that guards a material risk, after reading existing tests | "Add tests" because no test file changed |
| Wrong public instructions, or missing information that makes a changed API unusable | Routine docstring and wording edits |
| A question the author must answer to decide whether a defect exists | Open-ended discussion prompts and team-awareness notices |

Also leave out: issues that existed before this PR (`introduced_by_pr: false` findings are dropped), personal preference, and anything a configured linter or formatter reports. A second agent agreeing with you is not evidence. Reading the code is.

If you find nothing that meets the bar, return an empty `findings` list. That is a correct result.

## Output structure

```json
{
  "version": "2.0",
  "agent": { "name": "spk-reviewer-backend-python", "role": "backend" },
  "files": [
    { "path": "src/api/features.py", "status": "reviewed" },
    { "path": "src/api/legacy.py", "status": "skipped", "note": "deleted file, nothing to read" }
  ],
  "context_unavailable": [
    "web/src/map.ts is outside my assignment; the primary reviewer should confirm the client"
  ],
  "findings": [
    {
      "id": "CR-001",
      "type": "inline_comment",
      "level": "severe",
      "category": "api_contract",
      "confidence": "high",
      "title": "The response rename breaks the map client",
      "problem": "The endpoint now returns `items`, but `loadFeatures()` in web/src/map.ts still reads `features`.",
      "consequence": "The map renders no results after deploy.",
      "fix": "Update the client in this PR and add a contract test.",
      "evidence": [
        "src/api/features.py:48: return {\"items\": rows}",
        "web/src/map.ts:112: const rows = body.features"
      ],
      "introduced_by_pr": true,
      "cross_cutting": true,
      "dedupe_key": "api_contract|response_rename_items|src/api/features.py|list_features|48-48",
      "location": { "file_path": "src/api/features.py", "side": "new", "start_line": 48, "end_line": 48, "symbol": "list_features" }
    }
  ]
}
```

Write the file to the path you are given (`<run_dir>/agents/<your-agent-name>.json`). Reply with one line: the file path, the number of files reviewed, and the number of findings. Do not paste the JSON into your reply.

## Agent identity

| Agent | Role |
|---|---|
| spk-reviewer-primary | primary |
| spk-reviewer-security | security |
| spk-reviewer-frontend | frontend |
| spk-reviewer-ui | ui_design |
| spk-reviewer-ux | ux_accessibility |
| spk-reviewer-backend-python | backend |
| spk-reviewer-python-quality | code_quality |
| spk-reviewer-tests | testing |
| spk-reviewer-devops | infrastructure |
| spk-reviewer-database | database |
| spk-reviewer-docs | documentation |

## Files

List every file you were assigned. `reviewed` means you read the whole change. `partial` means you read some of it; say what you skipped in `note`. `skipped` means you did not review it; say why. A file you do not list counts as not reviewed and makes the coverage report say "incomplete".

## Finding fields

| Field | Required | Rule |
|---|---|---|
| `id` | yes | `CR-001`, `CR-002`, ... unique within your file. The tool renumbers later. |
| `type` | yes | `inline_comment` when the problem sits at known lines. `diff_comment` when it spans files or concerns a missing file. |
| `level` | yes | `severe`: must fix before merge. `warning`: should fix. `question`: the author must answer it to decide whether a defect exists. |
| `category` | yes | One of the shared categories. `style` is never published by default. |
| `confidence` | yes | `high`, `medium`, `low`. Diagnostic only; it is not shown on GitHub. Medium and low warnings get independent verification. |
| `title` | yes | Under 80 characters. A plain statement of the problem, such as "Expired tokens pass validation". Not a label like "Token issue". |
| `problem` | yes | One sentence. The trigger. Name the function, variable, value, or line. |
| `consequence` | yes | One sentence. What goes wrong. |
| `fix` | warning, severe | One sentence. What to change. Code is fine when short. |
| `fix_caveat` | no | Only when the fix changes how it must be applied: deploy order, a table lock, callers to update. Omit when there is nothing to say. |
| `evidence` | warning, severe | Quotes from the reviewed revision as `path:line: code`. At least one. |
| `introduced_by_pr` | yes | `true` only when this PR causes the problem. |
| `cross_cutting` | no | `true` when the finding spans files, services, or deployment steps. |
| `dedupe_key` | yes | `category|issue_slug|primary_file[|symbol|lines]`. The first three segments identify the finding across runs and agents, so keep them stable and free of line numbers. |
| `location` | inline only | `file_path`, `side` (`new` or `old`), `start_line`, `end_line`. `side` is required. Use `old` for deleted lines. |
| `applies_to` | diff only | `file_paths` (at least one) and optional `symbols`. |
| `references`, `related_ids` | no | CWE ids, docs, or related `CR-` ids. |

## Writing rules

The author reads your finding on GitHub in a few seconds. Write for a grade 10 reader.

- `problem`, `consequence`, and `fix` together: 40 to 70 words. The tool rejects anything over 110.
- Short sentences. One idea per sentence. Common words: "use", not "utilize".
- Active voice. "This returns null", not "Null is returned".
- Start with the problem. Do not describe what the code does first.
- Name the exact thing: the function, the variable, the value. Not "this logic".
- No hedging: no "might potentially", "it seems", "consider possibly".
- Each field adds new information. Do not repeat the problem in the consequence or the fix.
- No filler: no "It is worth noting", "In order to", "Great job, but".
- No em dashes. Use a period or a comma.

| Avoid | Prefer |
|---|---|
| "The current implementation may potentially fail to adequately handle scenarios in which the input value is null." | "This crashes when `user` is null." |
| "It would be advisable to consider leveraging a parameterized query to mitigate injection risk." | "Use a parameterized query. The string format allows SQL injection." |

## Reading the code

You get a snapshot path pinned to the PR head commit. Read callers, implementations, and tests there when you need them to establish a finding. Read the minimum that settles the question. If the snapshot is unavailable, use `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/spk_review.py fetch-file <run_dir> <path>` to fetch a file at the head commit. If you still cannot read something you need, list it in `context_unavailable` and lower your confidence. Never state a claim you could not check as if you had checked it.

## How your output is used

1. `ingest` validates your file. A file with structural errors is recorded as a failed agent, and the review is reported as incomplete.
2. Findings with the same `category|slug|file` key are merged across agents. The aggregator then merges findings that describe the same root cause in different words and rewrites them to the word budget.
3. Severe findings, and warnings with medium or low confidence, go to an independent verifier that reads the snapshot.
4. `finalize` drops rejected and pre-existing findings, computes counts and blocking from what is left, keeps every verified severe finding, and publishes up to five findings. The rest are listed by title in a collapsed section.
5. `render` posts the explanation once: inline when the lines are in the diff, otherwise in the review body as a checklist item.

Confidence, attribution, and verification notes stay in the local `final.json`. They are not shown on GitHub.

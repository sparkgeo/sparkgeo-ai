# Evaluating spk-code-review

Change agent prompts only with evidence. This directory holds the format for a regression suite of historical pull requests with known issues, and describes the metrics to track from real runs.

## Regression cases

Add cases to a `cases.yaml` file (start from [cases.example.yaml](cases.example.yaml)). Each case names a PR, the issue it is known to contain, and what the pipeline should do with it.

Run each case with a dry run, so nothing is posted:

```
/spk-code-review https://github.com/<owner>/<repo>/pull/<number> --dry-run
```

Then compare `.reviews/<run>/review.json` against the case:

| Check | Pass when |
|---|---|
| Recall | A finding matches the expected issue (same file, overlapping lines, same root cause). |
| Agent | The matching finding's `found_by` includes `expected_agent`. |
| Severity | The finding's severity equals `expected_severity`. |
| Risk | `risk.level` in `review.json` equals `expected_risk`. |
| Routing | Every agent in `expected_agents` ran, and none in `forbidden_agents` ran. |
| Noise | The number of findings is at most `max_findings`. |
| No false positives | No finding matches an entry in `must_not_report`. |

Run the whole suite before you merge a prompt change, and compare with the results from `main`.

## Per-agent measures

For each agent, track over the suite:

- precision: findings that match a known issue or that a reviewer accepts, divided by all findings,
- recall: known issues found, divided by known issues in the agent's domain,
- severity accuracy,
- evidence quality (does each finding cite checkable lines and a concrete failure),
- false positives (from `stats.per_agent[].rejected` and from human review),
- duplicate rate (`stats.duplicates_merged / stats.raw_findings`),
- usefulness of the recommendation.

## Production metrics

Every run saves all stage outputs in `.reviews/<timestamp>_pr<number>/`. From these and from GitHub, track:

- findings accepted by developers (thread resolved after a code change),
- findings rejected as incorrect (thread resolved with no change, or a reply that disputes it),
- false-positive rate by agent,
- severity accuracy,
- duplicate finding rate,
- average comments per PR,
- review latency and run time,
- defects and security issues found after merge in reviewed code,
- share of PRs that needed human escalation,
- token cost per review,
- agent disagreement rate (disputed findings sent to the verifier).

Use these numbers to tune prompts and routing. A prompt change that raises recall but doubles false positives is usually a regression.

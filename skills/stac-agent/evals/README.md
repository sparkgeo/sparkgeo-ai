# stac-agent evals

Test cases and workspace conventions for evaluating stac-agent output quality.

## Layout

```
skills/stac-agent/
├── SKILL.md
└── evals/
    ├── evals.json          

stac-agent-workspace/       ← created alongside the skill directory per iteration
└── iteration-1/
    ├── eval-basic-catalog/
    │   ├── with_skill/
    │   │   ├── outputs/
    │   │   ├── timing.json
    │   │   └── grading.json
    │   └── without_skill/
    │       ├── outputs/
    │       ├── timing.json
    │       └── grading.json
    ├── eval-multispectral-cogs/
    │   └── ...
    ├── eval-validate-only/
    │   └── ...
    ├── eval-missing-credentials/
    │   └── ...
    ├── feedback.json
    └── benchmark.json
```

## Test buckets

| Bucket  | URI                                 | Access                             |
|---------|-------------------------------------|------------------------------------|
| Public  | `s3://spk-public-data/eo-tests/`    | Public read, no credentials needed |
| Private | `s3://wyvern-closed-data/original/` | Requires valid AWS credentials     |

Evals 1 uses the public bucket. Evals 2 and 4 use the private bucket. Eval 3 is local-only.

## Before running

AWS credentials must be active in the environment for evals that target `s3://wyvern-closed-data/`. No credentials are required to run eval 1 against the public bucket.

## Running a single eval

For a **with-skill** run, provide the agent:

```
Execute this task:
- Skill path: /path/to/skills/stac-agent
- Task: <prompt from evals.json>
- Save outputs to: stac-agent-workspace/iteration-1/<eval-dir>/with_skill/outputs/
```

For a **without-skill** baseline, use the same prompt, no skill path, saving to `without_skill/outputs/`.

Record token count and duration in `timing.json`:

```json
{
  "total_tokens": 0,
  "duration_ms": 0
}
```

## Grading

After each run, evaluate the assertions from `evals.json` against the outputs and write `grading.json`:

```json
{
  "assertion_results": [
    { "text": "...", "passed": true, "evidence": "..." }
  ],
  "summary": { "passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0 }
}
```

## Aggregating

Once all runs in an iteration are graded, compute `benchmark.json`:

```json
{
  "run_summary": {
    "with_skill":    { "pass_rate": { "mean": 0.0, "stddev": 0.0 }, "time_seconds": { "mean": 0.0 }, "tokens": { "mean": 0 } },
    "without_skill": { "pass_rate": { "mean": 0.0, "stddev": 0.0 }, "time_seconds": { "mean": 0.0 }, "tokens": { "mean": 0 } },
    "delta":         { "pass_rate": 0.0, "time_seconds": 0.0, "tokens": 0 }
  }
}
```

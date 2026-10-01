# spk-github

Sparkgeo GitHub workflows for Claude Code: a review team for pull requests (`/spk-github:spk-pr`) and a skill that writes pull requests from the active branch (`spk-pr-writer`).

## The review pipeline

The review runs in two layers. A Python tool does every step that must be deterministic. Agents do the reading and the judgement.

| Step | Who | What |
|---|---|---|
| collect | tool | PR metadata with author and SHAs, all changed files (paginated), the diff, all review threads (paginated), the last AI review. Checks the head did not move. |
| snapshot | tool | Checks out the head SHA into an isolated worktree or shallow clone. Falls back to per-file API reads pinned to the SHA. |
| route | tool | Classifies every file, applies repository exclusions, assigns one primary reviewer plus conditional specialists, and raises behaviour triggers for absences (model change with no migration, behaviour change with no tests, API change with no docs). |
| review | agents | The primary reviewer traces the change across boundaries. Specialists check their domain. Security runs on everything. Each agent writes JSON with per-file completion. |
| ingest | tool | Validates every agent file, records failures, merges exact duplicates, numbers candidates. |
| aggregate | agent | Merges findings by root cause, rewrites to the word budget, links legacy threads. |
| verify | agents | Independent verification of severe findings and context-dependent warnings against the snapshot. |
| finalize | tool | Drops pre-existing and style findings, computes counts and blocking, matches earlier threads by fingerprint, applies the publication budget. |
| render | tool | One explanation per finding: inline when the diff has the line, otherwise a checklist item in the body. Diagnostics go in a collapsed section. |
| post | tool | Rechecks the head SHA, posts with `commit_id`, then supersedes the earlier review. |

### What gets published

A finding needs a concrete trigger, a demonstrated consequence, and evidence at the reviewed revision. Pre-existing issues, preferences, generic hardening, and lint-detectable style are dropped. Up to five findings are published by default. Every independently verified severe finding is always published. The rest are listed by title in the collapsed details.

The review event is `COMMENT` unless the repository opts in to `REQUEST_CHANGES` and a severe finding was verified.

### Earlier review threads

Each posted finding carries a fingerprint (`category|slug|file`). On the next run the tool reads every thread and decides per finding:

| Thread state | Finding found again | Result |
|---|---|---|
| open or author replied | yes | Listed as still open with a link. No new inline thread. Reposted only if severity increased. |
| resolved, author replied | yes, verified | Accepted risk for warnings and questions. Severe findings are reposted with fresh evidence. |
| resolved, no reply | yes, verified | Reopened. |
| any | no | Reported as not found at the reviewed commit. |

A reply is never treated as a fix.

## Repository configuration

Optional. Put `.github/spk-review.json` in the reviewed repository:

```json
{
  "request_changes": false,
  "max_published": 5,
  "exclude": ["fixtures/**", "**/*.snap"],
  "optional_reviewers": ["spk-reviewer-python-quality"],
  "conventions": ["docs/REVIEW.md"],
  "allow_style_findings": false
}
```

| Key | Default | Meaning |
|---|---|---|
| `request_changes` | `false` | Allow `REQUEST_CHANGES` when a verified severe finding exists. |
| `max_published` | `5` | Soft budget for published findings. Verified severe findings always publish. |
| `exclude` | `[]` | Glob patterns excluded from review. Shown in the review with the reason. |
| `optional_reviewers` | `[]` | Opt-in agents. `spk-reviewer-python-quality` runs Ruff and a type checker and reports only tool output. |
| `conventions` | `[]` | Extra files to treat as review policy, in addition to CLAUDE.md, AGENTS.md, REVIEW.md, CONTRIBUTING.md, and `.github/copilot-instructions.md`. |
| `allow_style_findings` | `false` | Publish `style` findings. |

Lockfiles, binaries, and generated files are never line-reviewed. They still go to the security reviewer for dependency and committed-artifact checks. There is no `.gitignore` or `.dockerignore` filtering; the policy is the same in every mode.

## Agents

| Agent | Model | When it runs |
|---|---|---|
| spk-reviewer-primary | opus | Always. Owns cross-cutting findings and uncovered files. |
| spk-reviewer-security | opus | Always. |
| spk-reviewer-backend-python | sonnet | `*.py`, `pyproject.toml` |
| spk-reviewer-database | sonnet | Migrations, SQL, model files, or a model change with no migration |
| spk-reviewer-frontend | sonnet | TypeScript, TSX, CSS, Vite, ESLint, package.json |
| spk-reviewer-ux | opus | TSX that adds interactive elements or ARIA |
| spk-reviewer-ui | sonnet | Stylesheets, theme files, assets, TSX with inline styling |
| spk-reviewer-tests | sonnet | Test files, or a behaviour change with no test change |
| spk-reviewer-devops | sonnet | Terraform, Docker, Compose, workflows, Makefiles, shell |
| spk-reviewer-docs | haiku | Docs, MkDocs, OpenAPI, or an API change with no docs change |
| spk-reviewer-python-quality | haiku | Opt-in only |
| spk-reviewer-aggregator | sonnet | Once per run |
| spk-reviewer-verifier | opus | Once per verification batch |

Model choices for the pre-existing agents were kept. Change them after comparing runs on the same PRs, not before.

## Local output

Each run writes `.reviews/pr<number>/<run_id>/`. `final.json` holds every finding with confidence, attribution, verification notes, publication status, and the reason for each rejection. `review-body.md` and `payload.json` are what was posted. Add `.reviews/` to `.gitignore`.

## Tests

```
python3 -m unittest discover -s plugins/spk-github/tests
```

The tests cover diff parsing (additions, deletions, context, renames, binaries), routing and exclusions, thread normalization (a reply from someone other than the PR author is not an author reply), contract validation, exact-key merging, finalize (budget, blocking, prior-thread states, failed agents), and rendering (anchors, folding, body limit).

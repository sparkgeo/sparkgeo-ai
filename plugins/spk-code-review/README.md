# spk-code-review

A risk-routed, multi-agent code review pipeline for GitHub pull requests.

The pipeline does not send every PR to every reviewer. It classifies the risk of the change, routes it to the smallest set of specialist reviewers that can add value, verifies severe findings, and posts **one** review. It aims for useful, correct, actionable findings, and stays quiet when there is nothing useful to say.

The author stays responsible for the code, whether a person or an AI tool wrote it.

> **Status: experimental (0.x).** The prompts and routing need tuning against real PRs. See [evals/](evals/).

## Usage

```
/spk-code-review                 # pick from open PRs in the current repo
/spk-code-review 123             # review PR #123 in the current repo
/spk-code-review https://github.com/owner/repo/pull/123
/spk-code-review 123 --dry-run   # run everything, post nothing
```

Requirements: `gh` (authenticated), `git`, and `jq`. Optional scanners that run when installed: `gitleaks`, `semgrep`, `trivy`.

Each run saves every stage output to `.reviews/<timestamp>_pr<number>/` in the current directory. Add `.reviews/` to your `.gitignore`.

## How it works

```text
Pull request
   │
   ▼
1. Context builder ───────── intent, affected components, related code, tests, ADRs, conventions
   │   + deterministic ───── CI checks (gh pr checks), gitleaks, semgrep, trivy
   ▼
2. Risk classifier ───────── low | medium | high, minimum review path, human review required?
   ▼
3. Coordinator ───────────── which specialists, which files, what depth
   ▼
4. Specialists (parallel)
   │   core:        architecture · correctness · security · tests · maintainability · performance-ops
   │   conditional: migration · infrastructure · api-compatibility · dependency · docs
   ▼
5. Verifier ──────────────── independently confirms or rejects blockers, security, disputed findings
   ▼
6. Synthesizer ───────────── dedupe, normalize severity, comment budget, merge gate
   ▼
One GitHub review (summary + inline comments)
```

Reviewers read the code from an isolated checkout of the PR head commit (a git worktree, or a partial clone when you pass a URL from outside the repo). The pipeline never runs the project's build, tests, or any code from the PR. Build, lint, type, and test results come from CI.

### Agents

| Agent | Stage | Model | Purpose |
|---|---|---|---|
| `spk-cr-context-builder` | 1 | sonnet | Builds the context package. No review comments. |
| `spk-cr-risk-classifier` | 2 | opus | Assigns low, medium, or high risk based on impact if the change is wrong. |
| `spk-cr-coordinator` | 3 | sonnet | Routes the PR to specialists with files, depth, and focus. |
| `spk-cr-architecture` | 4 | opus | Fit with architecture, boundaries, coupling, reuse. |
| `spk-cr-correctness` | 4 | opus | Adversarial search for wrong results and unsafe failures. |
| `spk-cr-security` | 4 | opus | Trust boundaries, authn/authz, injection, SSRF, secrets. |
| `spk-cr-tests` | 4 | sonnet | Would the tests catch the bugs that matter? |
| `spk-cr-maintainability` | 4 | sonnet | Readability, complexity, duplication, conventions. |
| `spk-cr-performance-ops` | 4 | sonnet | Scale, N+1, memory, timeouts, observability, cost. |
| `spk-cr-migration` | 5 | sonnet | Schema and data migration safety. |
| `spk-cr-infrastructure` | 5 | sonnet | Terraform, containers, CI/CD, IAM, networking. |
| `spk-cr-api-compatibility` | 5 | sonnet | Breaking changes to public or shared APIs. |
| `spk-cr-dependency` | 5 | sonnet | New and upgraded dependencies, supply chain. |
| `spk-cr-docs` | 5 | haiku | Docs that must change with the code. |
| `spk-cr-verifier` | 6 | opus | Rejects false positives before developers see them. |
| `spk-cr-synthesizer` | 7 | sonnet | Produces the single, prioritized review. |

### Severity and confidence

| Severity | Meaning |
|---|---|
| Blocker | Must be fixed before merge. Always verified. |
| Issue | Should be fixed before merge unless the team accepts it. |
| Suggestion | Worth considering. Does not block. |
| Nit | Rare. Never for anything a tool can fix. |

Confidence is `high` (shown directly by the code or tools), `medium` (depends on one named assumption), or `low` (speculative, usually turned into a question).

Default comment budget: unlimited blockers, 10 issues, 5 suggestions, 0 nits. Extra findings are folded into the summary.

### Risk levels and minimum review paths

| Risk | Minimum path | Human review |
|---|---|---|
| Low | Author review → automated checks → AI review → auto-merge policy | Optional, only if repo policy allows |
| Medium | Author review → automated checks → AI review → 1 human reviewer | Required |
| High | Author review → automated checks → AI specialist review → senior or specialist human review | Required, possibly several reviewers |

Passing tests never lower the risk of an inherently high-risk change, such as authorization or a destructive migration.

### GitHub review event

- Any blocker → `REQUEST_CHANGES`.
- `APPROVE` only when the merge gate passes (checks pass, no blockers, no high-confidence security findings, all agents finished, risk is low and policy allows auto-merge) **and** the repo config sets `allow_approve: true`.
- Otherwise `COMMENT`.

On re-runs, the pipeline suppresses findings from earlier runs that the author resolved or replied to, except blockers, which it re-raises while they are still in the code.

## Repository configuration

Copy [templates/review-config.example.yaml](templates/review-config.example.yaml) to `.github/spk-code-review.yaml` in the reviewed repository to set architecture documents, standards, excluded paths, risk floors by domain or path, extra routing, the comment budget, required checks, and approval policy. Every key is optional.

## Layout

```
spk-code-review/
├── .claude-plugin/plugin.json
├── commands/spk-code-review.md        # the orchestrator
├── agents/spk-cr-*.md                  # 16 agents
├── templates/
│   ├── reviewer-guide.md               # shared rules for all specialists
│   ├── finding-schema.json             # specialist output schema
│   ├── pipeline-contracts.md           # JSON for every other stage
│   └── review-config.example.yaml
├── scripts/
│   ├── github-checks.sh                # gh installed and authenticated
│   ├── prepare-workspace.sh            # PR head checkout (worktree or clone)
│   ├── cleanup-workspace.sh
│   ├── run-scanners.sh                 # gitleaks, semgrep, trivy if installed
│   └── diff-line-ranges.sh             # valid inline comment lines
└── evals/                              # regression cases and metrics
```

## Relation to spk-github

`spk-github` has a file-type-routed review team (`/spk-github:spk-pr`). This plugin is an experimental alternative that routes by risk and domain instead of file type, and adds context building, risk classification, and verification. The two can be installed side by side.

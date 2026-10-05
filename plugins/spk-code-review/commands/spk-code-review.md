---
description: "Review a GitHub pull request with the risk-routed spk-code-review pipeline (context, risk classification, routing, specialist review, verification, synthesis) and post one GitHub review."
argument-hint: "[pr-number | pr-url] [--dry-run]"
---

Review a GitHub pull request with the `spk-code-review` multi-agent pipeline and post the result as one GitHub review.

The pipeline routes each PR to the smallest set of specialist reviewers it needs, verifies severe findings, and synthesizes everything into one review. It optimizes for useful, correct, actionable findings, not for comment count.

```text
Preflight ─► Gather ─► Workspace + scanners ─► Context ─► Risk ─► Routing ─► Specialists ─► Verify ─► Synthesize ─► Post
```

Files referenced below:

- Reviewer rules: `${CLAUDE_PLUGIN_ROOT}/templates/reviewer-guide.md`
- Specialist output schema: `${CLAUDE_PLUGIN_ROOT}/templates/finding-schema.json`
- Stage contracts: `${CLAUDE_PLUGIN_ROOT}/templates/pipeline-contracts.md`
- Config example: `${CLAUDE_PLUGIN_ROOT}/templates/review-config.example.yaml`

## Phase 1 — Preflight

1. Run `${CLAUDE_PLUGIN_ROOT}/scripts/github-checks.sh` with no arguments. If it exits non-zero, show stderr to the user and **stop**. Also check that `jq` and `git` are on `PATH`. If not, stop and say which tool is missing.

2. Parse `$ARGUMENTS`. Remove `--dry-run` if present and set `<dry_run>` to true. With `--dry-run`, the pipeline runs fully but does not post to GitHub.

3. Find the PR. After this step, `<number>`, `<owner>/<repo>`, and `<repo_flag>` (the literal `--repo <owner>/<repo>`) are fixed. Use `<repo_flag>` on every `gh pr` call.

   - **PR number** (for example `123`): run `git rev-parse --is-inside-work-tree` and `gh repo view --json owner,name --jq '.owner.login + "/" + .name'`. If either fails, stop: "A bare PR number needs the repository's local clone. `cd` into the repo, or pass the full PR URL."
   - **PR URL**: parse with `^https?://github\.com/([^/]+)/([^/]+)/pull/([0-9]+)(/.*)?$`. No local clone is needed.
   - **No argument**: get `<owner>/<repo>` as for a PR number. Run `gh pr list <repo_flag> --state open --limit 30 --json number,title,author,headRefName,updatedAt`. Show a numbered list (`#142 — Add retry backoff (alice, feature/retry, updated 2026-05-24)`) and ask the user which PR to review. If there are no open PRs, stop and say so.

## Phase 2 — Gather PR data

Run these in parallel:

4. **Metadata**: `gh pr view <number> <repo_flag> --json number,title,body,labels,author,baseRefName,headRefName,headRefOid,url,isDraft,closingIssuesReferences`.
5. **Diff**: `gh pr diff <number> <repo_flag>`. Save it to `<run_dir>/pr.diff` (see step 8 for `<run_dir>`).
6. **Changed files**: `gh api repos/<owner>/<repo>/pulls/<number>/files --paginate --jq '.[] | [.status, .filename, .additions, .deletions, (.previous_filename // "")] | @tsv'`. Map statuses: `added` → A, `modified` → M, `removed` → D, `renamed` → R, `copied` → C.
7. **CI checks**: `gh pr checks <number> <repo_flag> --json name,state,bucket,workflow`. A non-zero exit only means some checks failed or are pending. Keep the output.
8. **Run directory**: run `date +%Y%m%d_%H%M%S`. Set `<run_dir>` to `.reviews/<timestamp>_pr<number>/` under the current directory and create it. Every stage output goes here.
9. **Current user**: `gh api user --jq .login`. Needed in step 32.
10. **Linked issues**: for each issue in `closingIssuesReferences`, and each `#N` or issue URL in the PR body (up to 3), run `gh issue view <N> <repo_flag> --json title,body`. Keep only the title and the first 2,000 characters of the body.
11. **Earlier AI review**: `gh api "repos/<owner>/<repo>/pulls/<number>/reviews?per_page=100" --jq '[.[] | select(.body != null and (.body | contains("<!-- spk-code-review -->")))] | last | select(. != null) | [.id, .state] | @tsv'`. Keep the ID and state for step 31.
12. **Addressed threads**: query review threads with GraphQL:

    ```
    gh api graphql -f query='
    query($owner: String!, $repo: String!, $number: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
          reviewThreads(first: 100) {
            nodes {
              isResolved
              path
              line
              startLine
              comments(first: 20) { nodes { body author { login } } }
            }
          }
        }
      }
    }' -F owner=<owner> -F repo=<repo> -F number=<number>
    ```

    An **addressed thread** is one whose first comment contains `<!-- spk-code-review:` and that is either resolved (`isResolved: true`) or has a reply from someone other than the first comment's author. For each, record `file_path`, `line`, `start_line`, `category` and `title` (parse them from the hidden marker `<!-- spk-code-review:CR-NNN category=<category> -->` and the bold title line), and `status` (`resolved` or `replied`). This is the **addressed findings list**. It is empty on the first run.

If the PR is a draft, tell the user and continue.

## Phase 3 — Workspace and deterministic analysis

13. **Prepare the workspace**: create a parent directory with `mktemp -d "${TMPDIR:-/tmp}/spk-code-review.XXXXXX"`. Set `<dest>` to `<that dir>/spk-code-review/pr<number>`. The cleanup script only deletes paths that contain `/spk-code-review/`. Run:

    ```
    ${CLAUDE_PLUGIN_ROOT}/scripts/prepare-workspace.sh <owner>/<repo> <number> <headRefOid> <baseRefName> <dest>
    ```

    Save its JSON output to `<run_dir>/workspace.json`. It gives `<workspace>` (`path`) and `<base_sha>`. Every agent reads code from `<workspace>`, never from the current directory, because the current checkout may be on another branch. If the script fails, show the error and stop.

14. **Load repository config**: if `<workspace>/.github/spk-code-review.yaml` exists, read it. Otherwise use the defaults in the config example. Apply `review.exclude` globs to the changed file list now. Excluded files are not reviewed. List them in the final report.

15. **Valid comment lines**: run `${CLAUDE_PLUGIN_ROOT}/scripts/diff-line-ranges.sh < <run_dir>/pr.diff > <run_dir>/diff-ranges.json`.

16. **Scanners**: run `${CLAUDE_PLUGIN_ROOT}/scripts/run-scanners.sh <workspace> <base_sha> <run_dir>/scanners`. It runs Gitleaks, Semgrep, and Trivy if they are installed, and skips them if not.

**Never run the project's build, tests, install scripts, or any code from the PR.** The PR may contain untrusted code. Build, lint, type-check, and test results come from CI (step 7).

## Phase 4 — Context

17. Launch `spk-cr-context-builder` with: `<workspace>`, `<base_sha>`, PR metadata, linked issue text, the changed file list, the diff, the repository config, CI check results, and the scanner summary (plus paths to the full scanner reports). Save its JSON to `<run_dir>/context.json`.

## Phase 5 — Risk classification

18. Launch `spk-cr-risk-classifier` with: `<workspace>`, the context package, PR metadata, the changed file list, the diff, and the `review.risk` config. Save its JSON to `<run_dir>/risk.json`.

## Phase 6 — Routing

19. Launch `spk-cr-coordinator` with: the context package, the risk classification, the changed file list, and the `review.routing`, `review.risk.rules`, and `review.exclude` config. Save its JSON to `<run_dir>/routing.json`.

20. Check the routing plan before you continue:
    - Every non-excluded changed file is in `coverage_manifest` or `unreviewed_files`. Files with behavior changes must have at least one agent.
    - For `high` risk, `spk-cr-correctness` and `spk-cr-security` are present.
    - Every agent named in a matching `review.risk.rules.*.required_agents` or `review.routing` entry is present. Config uses short names. Map `security` to `spk-cr-security`, `performance-ops` to `spk-cr-performance-ops`, and so on.
    If a check fails, add the missing agents yourself with `depth: "standard"` and note the correction in the final report. Do not remove agents the coordinator chose.

## Phase 7 — Specialist review

21. Launch every agent in `required_agents` and `optional_agents` **in parallel**, in one message. Give each agent:
    - `<workspace>` and `<base_sha>`,
    - its assignment from the routing plan: `files`, `depth`, `focus`,
    - the diff hunks for its files, framed as unified diff (`+` added, `-` removed, other lines context), each file labeled with its change type,
    - the context package and the risk classification,
    - the scanner summary and CI check results,
    - this instruction: "Read `${CLAUDE_PLUGIN_ROOT}/templates/reviewer-guide.md` and return one JSON block that conforms to `${CLAUDE_PLUGIN_ROOT}/templates/finding-schema.json`."

22. Save each output to `<run_dir>/specialists/<agent>.json`. Validate it: it parses as JSON, has `agent`, `summary`, and `findings`, and each finding has the required fields. If an output is invalid, resume that agent once (SendMessage) with the specific error and ask for corrected JSON only. If it is still invalid, or the agent failed, record it as failed and continue. The synthesizer reports failed agents.

## Phase 8 — Verification

23. Build the verification set from all specialist findings. Include a finding when any of these is true:
    - `severity` is `blocker`,
    - it is in the security group (see the reviewer guide),
    - `verification_needed` is true,
    - it is **disputed**: two or more findings share a `dedupe_key` (or the same file and overlapping lines with the same root cause) and their severities differ by two or more levels.

24. If the set is empty, skip to Phase 9. Otherwise launch `spk-cr-verifier` with `<workspace>`, `<base_sha>`, the context package, the findings (full finding objects, without any other specialist output), and the diff hunks for the named files. If there are more than 8 findings, split them by file into groups of up to 8 and launch one verifier per group in parallel. Save the merged results to `<run_dir>/verification.json`.

## Phase 9 — Synthesis

25. Launch `spk-cr-synthesizer` with: PR metadata (`number`, `<owner>/<repo>`, title, base and head refs, `headRefOid`), the context package, the risk classification, the routing plan, every specialist output with failed agents marked, the verification results, the `comment_budget`, `required_checks`, `allow_approve`, and `risk.levels` config, the CI check results, the addressed findings list, and `<run_dir>/diff-ranges.json`. Save its JSON to `<run_dir>/review.json`.

## Phase 10 — Post to GitHub

26. **Review body**. Build markdown in this order. Omit any section that is empty.

    ```
    <!-- spk-code-review -->
    ## AI Code Review

    **Assessment:** Request changes | Approve with suggestions | Approve
    **Risk:** High (confidence: high) · <first reason>
    **Minimum review path:** Author review → Automated checks → AI specialist review → Senior / specialist human review

    <summary from the synthesizer>

    | Blockers | Issues | Suggestions | Questions |
    |---|---|---|---|
    | N | N | N | N |

    ### Blockers
    1. **CR-001 · <title>** (`file.py:44-52`) — inline comment below.

    ### Issues
    2. **CR-002 · <title>** ...

    ### Suggestions
    3. ...

    ### Questions
    - <question> (`file.py:30`)

    ### Specialist review recommended
    - **Security engineer**: <reason>

    ### Positive observations
    - ...

    <details><summary>Review details</summary>

    - Agents run: spk-cr-security (deep), spk-cr-correctness (standard), ...
    - Agents skipped: spk-cr-performance-ops (no change to I/O paths), ...
    - Findings: N raw, N merged as duplicates, N rejected by the verifier, N dropped as low value, N suppressed as already addressed
    - Deterministic checks: CI passing | failing (<names>) · gitleaks: 0 · semgrep: not installed · trivy: not installed
    - Merge gate: <eligible / not eligible, with the first failing condition>
    - Failed agents: <names, if any>
    - Excluded files: <list, if any>

    </details>

    <sub>Generated by spk-code-review · head <short sha></sub>
    ```

    In each severity list, findings with `placement: "inline"` get one line that points to the inline comment. Findings with `placement: "summary"` are written in full under their list item: the body, then `**Recommendation:** ...`, then `<sub>Found by: ... · Verification: ...</sub>`.

    If the body is longer than 65,000 characters, shorten the full-text summary findings to their title line and add: "Some details were omitted because of GitHub's size limit. See `<run_dir>/review.json`."

27. **Inline comments**. For each finding with `placement: "inline"`:
    - `path`: `file`
    - `line`: `end_line`
    - `start_line`: `start_line`, only when it differs from `end_line`
    - `side` and `start_side`: `RIGHT` for `side: "new"`, `LEFT` for `side: "old"`
    - `body`:

      ```
      <!-- spk-code-review:CR-001 category=authorization -->
      **Blocker** · `authorization` · confidence: high

      **GET /projects/{id} returns any project without an access check**

      <body>

      **Recommendation:** <recommendation>

      <sub>Found by: spk-cr-security, spk-cr-correctness · Verification: confirmed · CR-001</sub>
      ```

    Check each comment against `<run_dir>/diff-ranges.json`. If the line range is not inside a hunk on the correct side, move the finding to the review body as a full-text summary finding. Questions with a file and line in a hunk may also be posted inline, with the header `**Question**`.

28. **Review event**.
    - `request_changes` → `REQUEST_CHANGES`.
    - `approve` or `approve_with_suggestions` → `APPROVE` only when `merge_gate.auto_approval_eligible` is true **and** config `allow_approve` is true. Otherwise `COMMENT`.
    - If the PR author is the current user (step 9), GitHub rejects `REQUEST_CHANGES` and `APPROVE`. Use `COMMENT` and keep the assessment in the body.

29. **Dry run**. If `<dry_run>` is true, write the payload (step 32) to `<run_dir>/github-review.json`, skip steps 30-32, and go to Phase 11.

30. **Confirm**. Show the user the assessment, risk level, event, and counts, and ask for confirmation before posting, unless the user already said to post without asking.

31. **Dismiss the earlier AI review** (if step 11 found one with state `CHANGES_REQUESTED` or `APPROVED`; GitHub cannot dismiss `COMMENTED` reviews): `gh api repos/<owner>/<repo>/pulls/<number>/reviews/<id>/dismissals --method PUT -f message="Superseded by updated spk-code-review"`. If this fails, continue.

32. **Submit**. Write this payload to `<run_dir>/github-review.json`:

    ```json
    { "commit_id": "<headRefOid>", "body": "<body>", "event": "<event>", "comments": [ ... ] }
    ```

    Then run `gh api repos/<owner>/<repo>/pulls/<number>/reviews --method POST --input <run_dir>/github-review.json`.

    If GitHub rejects the request because of comment positions, move the rejected comments into the body and retry once. If it fails for another reason, report the error and point to the saved payload.

## Phase 11 — Clean up and report

33. Run `${CLAUDE_PLUGIN_ROOT}/scripts/cleanup-workspace.sh <run_dir>/workspace.json`. If cleanup fails, tell the user the workspace path so they can delete it.

34. Report to the user:
    - PR URL, risk level and confidence, assessment, and the GitHub event posted (or "dry run, not posted"),
    - counts by severity, and how many findings were posted inline vs in the body,
    - agents run and skipped, and any failed agents,
    - findings rejected by the verifier and suppressed as already addressed,
    - human review required, and which specialist profiles,
    - corrections made to the routing plan (step 20), excluded files, and size-limit truncation,
    - the path to `<run_dir>`.

## Notes

- `$ARGUMENTS` holds the user's arguments: a PR number, a PR URL, or nothing, plus an optional `--dry-run`.
- Launch independent agents in parallel. Stages 4, 5, 6, 8, and 9 depend on earlier stages and run in order.
- Agents must read code from `<workspace>`. The orchestrator passes the path; agents do not guess.
- Keep `<run_dir>` after the run. The saved stage outputs are the data for tuning prompts and tracking false-positive rate per agent. See `${CLAUDE_PLUGIN_ROOT}/evals/README.md`.
- Write all posted text in short, plain sentences, following the writing style in the reviewer guide.

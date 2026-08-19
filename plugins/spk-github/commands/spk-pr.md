Review a GitHub Pull Request using the multi-agent code review pipeline and post findings as a GitHub review with inline comments.

## Instructions

### Phase 1 — Preflight & Mode Selection

The command supports three modes, dispatched on `$ARGUMENTS`:

1. **Check GitHub CLI auth**: Run `${CLAUDE_PLUGIN_ROOT}/scripts/github-checks.sh` (with no arguments). If exit code is non-zero, report stderr to the user and **stop**.

2. **Determine mode** based on `$ARGUMENTS`. After this step you must have two values fixed for the rest of the run:
   - `<number>` — the PR number to review.
   - `<owner>/<repo>` — the target repository in `OWNER/REPO` form.

   And one derived value:
   - `<repo_flag>` — the literal string `--repo <owner>/<repo>` (used to make every `gh` call work from any directory). Always include this flag on `gh pr view`, `gh pr diff`, and `gh pr list` calls below.

   #### Mode A — PR number passed (e.g. `123`)
   - Verify the current directory is inside a git/GitHub repo:
     - Run `git rev-parse --is-inside-work-tree`. If this fails, stop and tell the user: "A bare PR number requires you to be inside the repository's local clone. Either `cd` into the repo, or pass the full PR URL instead."
     - Run `gh repo view --json owner,name --jq '.owner.login + "/" + .name'` to get `<owner>/<repo>`. If this fails, stop with the same message.
   - Set `<number>` from `$ARGUMENTS`.

   #### Mode B — PR URL passed (e.g. `https://github.com/foo/bar/pull/123`)
   - Parse the URL with this regex: `^https?://github\.com/([^/]+)/([^/]+)/pull/([0-9]+)(/.*)?$`. The captured groups give `<owner>`, `<repo>`, and `<number>`.
   - Do **not** require a git repo in the current directory. The local `.reviews/` output directory will be created under the current working directory.
   - **Note**: `.gitignore` / `.dockerignore` filtering in Phase 3 step 10 cannot run without the local working tree — skip that step in this mode and mention the skip in the final report.

   #### Mode C — No arguments
   - Verify the current directory is inside a git/GitHub repo (same check as Mode A). If not, stop and tell the user: "No PR specified. Either `cd` into a repo, pass a PR number, or pass a PR URL."
   - Run `gh repo view --json owner,name --jq '.owner.login + "/" + .name'` to get `<owner>/<repo>`.
   - Run `gh pr list --state open --limit 30 --json number,title,author,headRefName,updatedAt` and present the open PRs to the user as a numbered list, e.g.:
     ```
     1. #142 — Add retry backoff to ingestion (alice, feature/retry, updated 2026-05-24)
     2. #138 — Fix flaky scheduler test (bob, fix/scheduler, updated 2026-05-23)
     ...
     ```
     Then ask the user which PR number to review and wait for their answer. Set `<number>` from their response.
   - If `gh pr list` returns zero open PRs, stop and report that there are no open PRs to review.

### Phase 2 — Gather PR Data

Run these commands in parallel (always include `<repo_flag>` so they work from any directory):

4. **Get PR metadata**: Run `gh pr view <number> <repo_flag> --json number,title,body,baseRefName,headRefName,headRefOid,url,changedFiles` to get PR details. Save these for the aggregator schema's `pr` field. Record `<changed_files_count>` from `changedFiles` — it is used in step 7 to verify the file list is complete.

5. **Repo identity**: `<owner>/<repo>` was already established in Phase 1. Use it directly for API calls; no extra `gh repo view` is needed here.

6. **Get the diff**: Run `gh pr diff <number> <repo_flag>` to get the unified diff content. GitHub refuses or truncates diffs for very large PRs (roughly >20,000 changed lines or >300 files in the diff media type). If this command fails or returns an obviously truncated diff, do not stop: fall back to the per-file `patch` fields from the paginated files response in step 7 (`gh api --paginate "repos/{owner}/{repo}/pulls/<number>/files?per_page=100" --jq '.[] | "--- " + .filename, .patch'`), record that the diff was incomplete, and carry an **incomplete-review flag** into Phase 5 and Phase 6.

7. **Get changed files with status**: Run `gh api --paginate "repos/{owner}/{repo}/pulls/<number>/files?per_page=100" --jq '.[] | .status + "\t" + .filename'`. The `--paginate` flag is required — without it GitHub returns only the first page and large PRs get silently truncated. Map GitHub statuses to change type labels: `added` → **A**, `modified` → **M**, `removed` → **D**, `renamed` → **R**, `copied` → **C**.

   **Completeness check**: Count the returned files and compare against `<changed_files_count>` from step 4. GitHub also caps this endpoint at 3,000 files per PR. If the counts differ, or `<changed_files_count>` exceeds 3,000, set the **incomplete-review flag**: the review must report which files could not be enumerated and must not claim full coverage in Phase 5 or Phase 6.

8. **Check for existing AI review**: Run `gh api --paginate --slurp "repos/{owner}/{repo}/pulls/<number>/reviews?per_page=100" --jq '[.[][] | select(.body != null) | select(.body | contains("<!-- ai-review-team -->"))] | last | .id // empty'` (with `--slurp`, pages arrive as an array of arrays, hence `.[][]`). Note the review ID if found — it will be handled in Phase 5.

9. **Fetch prior AI review threads**: Query the GitHub GraphQL API for the PR author's login and the inline review threads created by previous AI review runs. The aggregator uses these to avoid posting duplicate inline threads and to decide which prior findings are genuinely settled. A reply on a thread is engagement, not evidence that the code was fixed — the aggregator verifies against the current head before suppressing anything. If the user has responded to the comment and the sentiment is that the issue won't be fixed or they have resolved the comment, that the issue can be considered addressed.

   Run:
   ```
   gh api graphql --paginate -f query='
   query($owner: String!, $repo: String!, $number: Int!, $endCursor: String) {
     repository(owner: $owner, name: $repo) {
       pullRequest(number: $number) {
         author { login }
         reviewThreads(first: 100, after: $endCursor) {
           pageInfo {
             hasNextPage
             endCursor
           }
           nodes {
             isResolved
             isOutdated
             path
             line
             startLine
             diffSide
             comments(first: 100) {
               pageInfo {
                 hasNextPage
               }
               nodes {
                 body
                 author { login }
                 createdAt
               }
             }
           }
         }
       }
     }
   }' -F owner=OWNER -F repo=REPO -F number=NUMBER
   ```

   The `--paginate` flag makes `gh` follow `reviewThreads.pageInfo` cursors automatically (it requires the `$endCursor` variable name and the `pageInfo { hasNextPage endCursor }` selection exactly as written above), so PRs with more than 100 review threads are read completely. Merge the `nodes` arrays from all returned pages before proceeding.

   If any thread reports `comments.pageInfo.hasNextPage: true` (more than 100 comments), its later replies were not fetched. This errs in the safe direction — a missed author reply leaves the thread `"open"` instead of `"acknowledged"`, so the finding stays visible rather than being wrongly suppressed. Note any such thread in the final report.

   Record `<pr_author>` from `pullRequest.author.login` (identical on every page).

   From the results, identify **prior AI review threads** — threads whose first comment matches the AI review format (body contains `Found by:` with a `CR-` ID, or the severity/category pattern like `**warning** · \`category\``).

   For each prior AI thread, extract and record:
   - `file_path`: the thread's `path` field
   - `line`: the thread's `line` field (end line of the comment anchor)
   - `start_line`: the thread's `startLine` field (if present)
   - `level`: parsed from the first comment body (the bold severity word, e.g. `warning` from `**warning** · \`security\``)
   - `category`: parsed from the first comment body (the text between backticks after the severity level, e.g. `security` from `**warning** · \`security\``)
   - `summary`: parsed from the first comment body (the bold text on the second line)
   - `status`, exactly one of:
     - `"resolved"` — `isResolved` is `true`
     - `"acknowledged"` — not resolved, and at least one comment after the first has `author.login` exactly equal to `<pr_author>`. Replies from other reviewers, maintainers, or bots do **not** count as acknowledgement.
     - `"open"` — anything else
   - `author_replies`: for acknowledged threads, the body text of every reply whose `author.login` equals `<pr_author>` — the aggregator interprets these to distinguish "will fix" / "good catch" from "won't fix" / "working as intended"

   Save this as the **prior findings list**. On a first review run the list is empty and no reconciliation occurs.

### Phase 3 — Multi-Agent Review Pipeline

10. **Filter excluded files**: Remove any files matched by `.gitignore` or `.dockerignore` from the changed file list before dispatching. **Skip this step in Mode B (PR URL)** — the local working tree is not available, so these files cannot be read. Note the skip in the final report.

11. **Route files deterministically**: Routing is decided by file paths, by a script — not by an agent reading the diff. Pipe the (filtered) changed file list from step 7 (`status\tfilename` lines) into:

    ```
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/route-files.py [--no-checkout]
    ```

    Pass `--no-checkout` in Mode B (no local clone) — it drops `spk-reviewer-python-quality`, which is only useful when it can run Ruff and the type checker locally; note the skip in the final report. The script is the **single source of truth** for the routing map. It prints a JSON manifest with per-file agent assignments (`files`), the inverse per-agent file lists (`agents`), and `unreviewed_files`. A file matching multiple patterns gets the union of all matching agents; files matching no specialist pattern fall back to `spk-reviewer-general-purpose` — nothing goes unreviewed.

    In the script's map, `spk-reviewer-security` is **risk-routed**, not universal: it is assigned only to patterns with security surface (application code, dependency manifests, IaC, workflows, shell scripts, SQL, `.env*`). Docs-only and asset-only changes do not invoke it — the deterministic secrets scan in step 11c still covers their full diff.

    11a. **Adopt the manifest as the coverage manifest**: The script's `files` output is the coverage manifest used in step 14c. Confirm `unreviewed_files` is empty.

    11b. **Apply conditional routing rules**:
    - **UI/UX specialists for substantive changes only**: Add `spk-reviewer-ui` to `.tsx`/`.css` files when the PR adds new components, changes theme/token files, or significantly restyles existing components. Add `spk-reviewer-ux` when the PR adds or significantly changes forms, routes, modals, navigation, or interaction flows. Judge this from file statuses (new files, file names) and diff size; the semantic dispatch check in step 11d can correct the call in either direction. Routine TSX edits stay with `spk-reviewer-frontend` alone.
    - **Migrations**: `alembic/**` routes to `spk-reviewer-database` alone by default. Also add `spk-reviewer-backend-python` only when the migration diff contains data operations (`op.execute`, `op.bulk_insert`, raw `UPDATE`/`INSERT`/`DELETE`) or the PR couples the migration to application-code changes with deployment-ordering risk — grep the migration hunks to decide.
    - **Security escalation**: If any changed file's path or diff suggests auth, session, crypto, permission, or upload logic and `spk-reviewer-security` is not yet assigned to it, add it.

    11c. **Deterministic secrets scan (every PR, all files)**: Run this scan over the full diff regardless of routing — including docs, assets, and files excluded from agent review by step 10:
    - If `gitleaks` is installed, pipe the diff through it (`gh pr diff <number> <repo_flag> | gitleaks stdin --no-banner` or `... | gitleaks detect --pipe --no-banner` depending on version) and collect its findings.
    - Otherwise, grep the **added lines** of the diff for common secret shapes: AWS access keys (`AKIA[0-9A-Z]{16}`), private key blocks (`-----BEGIN .*PRIVATE KEY-----`), GitHub tokens (`gh[pousr]_[A-Za-z0-9]{36,}`), Slack tokens (`xox[baprs]-`), generic assignments like `(api[_-]?key|secret|password|token)\s*[:=]\s*['"][^'"]{16,}` — and review each hit for plausibility (skip obvious placeholders like `changeme`, `<your-key>`, test fixtures with fake values).
    - Each plausible hit becomes a candidate finding: `level: severe`, `category: security`, attributed to `deterministic-secrets-scan`, with the matched line as evidence. These candidates enter the verification stage (step 13) like any other — being `security`, they route to the deep verifier.

    11d. **Semantic dispatch check**: Use the Agent tool to launch `spk-reviewer-dispatch` with: the PR title/description/labels, the changed file list with statuses and per-file line counts, and the routing plan from steps 11–11b. Do **not** send it the full diff — include short diff excerpts only for files whose routing you found ambiguous. It returns a PR summary, cross-cutting concerns (passed to the aggregator in step 14), and routing adjustments. Apply adjustments that name a concrete reason; update the coverage manifest accordingly.

12. **Run specialist agents in parallel**: Based on the routing plan, launch the appropriate specialist review agents in parallel using the Agent tool. Each agent receives:
   - The subset of files assigned to it
   - The relevant diffs for those files, clearly framed as unified diff format: lines prefixed with `+` are additions, lines prefixed with `-` are deletions, and unprefixed lines are unchanged context
   - Each file labeled with its change type: **A** = added, **M** = modified, **D** = deleted, **R** = renamed
   - The PR summary and cross-cutting concerns from the dispatch check (step 11d)
   - Instruction to output structured JSON conforming to `${CLAUDE_PLUGIN_ROOT}/templates/review-schema.json`

   **Extra context for specific agents** (they cannot do their jobs from their own file subset alone):
   - **spk-reviewer-tests** additionally receives the diffs of the changed **production** files — coverage-gap reasoning is impossible from test files alone
   - **spk-reviewer-docs** additionally receives the diffs of related implementation files (endpoints, schemas, CLI code) when the PR changes both docs and implementation, so accuracy checks are grounded in code, not prose
   - Every agent is told whether a local checkout is available (Mode A/C) or not (Mode B), since several run deterministic tools when they can

   Use these agent definitions from `${CLAUDE_PLUGIN_ROOT}/agents/`:
   - **spk-reviewer-security** — risk-routed: application code, dependency manifests, IaC, workflows, shell, SQL, .env (see step 11)
   - **spk-reviewer-frontend** — default pass for .ts, .tsx, .css, vite/eslint config (includes baseline UI/a11y)
   - **spk-reviewer-ui** — specialist, only for substantive visual changes, theme files, and image assets
   - **spk-reviewer-ux** — specialist, only for substantive interaction/accessibility changes
   - **spk-reviewer-backend-python** — for .py, pyproject.toml; migrations only when they carry data/deployment risk
   - **spk-reviewer-python-quality** — for .py files, Mode A/C only (runs Ruff/type-checker locally)
   - **spk-reviewer-tests** — for test/spec files, conftest, vitest config, plus the production diffs
   - **spk-reviewer-devops** — for .tf, Dockerfile, docker-compose, .github/workflows, Makefile
   - **spk-reviewer-database** — for alembic/, .sql, SQLAlchemy models
   - **spk-reviewer-docs** — for .md, mkdocs.yml, openapi specs, plus related implementation diffs
   - **spk-reviewer-general-purpose** — fallback for unmatched files

   Each agent returns a single JSON block with `version`, `agent`, `summary`, and `comments` fields. See `${CLAUDE_PLUGIN_ROOT}/templates/review-output-format.md` for the complete schema reference.

   **Specialist output is candidate findings, not publishable findings.** Nothing a specialist reports is posted to GitHub until it passes step 13.

13. **Verify candidate findings**: Independently verify candidates before aggregation so only findings that survive adversarial checking are published.

    a. **Select candidates that require verification** from the pooled specialist comments plus the deterministic secrets-scan candidates from step 11c (which are `severe`/`security`, so they are always verified and always route to the deep verifier):
       - Every `severe` candidate — always verified, no exceptions
       - Every `warning` candidate with `confidence` of `medium` or `low`
       - `warning` candidates with `high` confidence, and all `info`/`question` candidates, skip verification and pass through to the aggregator marked as verification status `unverified` (they are non-blocking and posted as-is)

       Before dispatching, collapse obvious duplicates: candidates from different agents sharing the same (or near-identical) `dedupe_key` are the same issue — verify it once and apply the verdict to all copies.

    b. **Route each candidate to a verifier**:
       - **spk-reviewer-verifier-deep** (Opus) for candidates in categories `security` or `concurrency`, candidates whose claim spans multiple files (cross-file `diff_comment`s or evidence referencing other files), and `severe` `correctness` candidates
       - **spk-reviewer-verifier** (Sonnet) for all other candidates

    c. **Launch verifiers in parallel** using the Agent tool. Give each verifier:
       - The PR title and body (the PR intent)
       - The candidate JSON object(s) verbatim, each identified by an agent-qualified id (`<specialist-agent-name>/<CR-NNN>`)
       - The diff hunks for the files each candidate touches
       - Whether a local checkout is available (Mode A/C) or not (Mode B) — in Mode B verifiers can only reason from the provided hunks
       - Instruction to output structured JSON conforming to `${CLAUDE_PLUGIN_ROOT}/templates/verification-schema.json`

       Batch up to 3 related candidates in the same file into one verifier invocation; verify `severe` candidates individually.

    d. **Apply the verdicts** to the candidate pool:
       - `confirmed` → keep the candidate; apply `corrected_level` / `corrected_location` if the verifier supplied them; attach the verifier's evidence
       - `rejected` → drop the candidate entirely; record the count and the verifier's reasoning (they appear in the local JSON and the Phase 6 report, never on GitHub)
       - `needs_human_context` → downgrade the candidate to level `question`, non-blocking, and append the verifier's `open_question` to the comment text so the PR author sees exactly what to confirm

       Only confirmed findings may retain `severe` level or a `blocking: true` flag. If a verifier fails to return valid output for a candidate, treat that candidate as `needs_human_context` (never publish an unverified severe finding).

14. **Aggregate results**: Aggregation is split between a semantic agent pass and deterministic assembly done by you (the orchestrator). The agent makes judgment calls; you do the arithmetic, ordering, and schema work — never delegate counting, sorting, numbering, coverage, or schema enforcement to the agent.

    a. **Parse and pool (deterministic)**: Extract the JSON block from each specialist's response and validate it against `${CLAUDE_PLUGIN_ROOT}/templates/review-schema.json`. If an agent's output fails to parse, note it — its files count as unreviewed for the coverage check. Pool all comments into a single array with agent-qualified IDs, verification verdicts already applied per step 13d.

    b. **Semantic aggregation (agent)**: Use the Agent tool to launch `spk-reviewer-aggregator` (from `${CLAUDE_PLUGIN_ROOT}/agents/spk-reviewer-aggregator.md`) with: the pooled comment array, the cross-cutting concerns from step 11d, the PR metadata (title, description), **the prior findings list from step 9, `<owner>/<repo>`, and the head commit SHA (`headRefOid`)**. The aggregator does only the semantic work: deduplicates (same root cause only — never merging distinct issues that merely share a category and file), reconciles prior review threads (verifying against the code at the head commit before suppressing anything — a reply or a resolved thread alone never suppresses a finding), arbitrates severity disagreements, filters cross-cutting concerns to those the findings support (it never invents new findings), and writes the overall assessment. It returns merged `comments` (with `source_ids`), a `suppressed` list with reasons, `cross_cutting_concerns`, and `overall_assessment`.

    c. **Deterministic assembly (orchestrator)**: From the aggregator's output, build the final aggregate JSON conforming to `${CLAUDE_PLUGIN_ROOT}/templates/review-aggregate-schema.json` yourself:
    - **Enforce the trust boundary**: a comment may keep `level: "severe"` or `blocking: true` only if its verification status is `confirmed`; otherwise downgrade to `warning`, set `blocking: false`, and note the missing verification in the comment text
    - **Sort** comments by severity (`severe` > `warning` > `question` > `info`), then confidence
    - **Assign** sequential `CR-NNN` IDs in sorted order; update any `related_ids`
    - **Count** findings per level from the actual comment array — never trust agent-reported arithmetic
    - **Verify coverage**: confirm via the coverage manifest (step 11a) that every changed file was reviewed by at least one agent whose output parsed; compute `files_reviewed`/`files_total` and build the per-agent `coverage` array from the manifest and the pooled comments
    - **Set summary fields**: `blocking` (true only if a confirmed `severe` comment exists), `suppressed_as_addressed` (length of the aggregator's `suppressed` list), `rejected_by_verification` and `needs_human_context` (from step 13d — do not recount), and the `pr` block from Phase 2 metadata
    - Validate the assembled JSON against the aggregate schema before proceeding

### Phase 4 — Save Review Locally

15. **Save the review JSON**: Generate a timestamp using `date +%Y%m%d_%H%M%S`. Create `.reviews/` if needed. Write the final aggregate JSON (assembled in step 14c) to `.reviews/<timestamp>_pr<number>_review.json`. The file conforms to `${CLAUDE_PLUGIN_ROOT}/templates/review-aggregate-schema.json`. Alongside it, write the raw verification verdicts (including rejected candidates and their reasoning) to `.reviews/<timestamp>_pr<number>_verification.json` so dropped candidates remain auditable.

### Phase 5 — Post to GitHub

16. **Build the review body** (the top-level summary comment for the review). Format it as markdown:

    ```
    <!-- ai-review-team -->
    ## AI Code Review

    **Assessment:** <overall_assessment from aggregator>

    | Severe | Warning | Question | Info |
    |--------|---------|----------|------|
    | N | N | N | N |

    **Files reviewed:** X / Y
    ```

    If any candidates went through verification (step 13), add after the files reviewed line (omit any zero part):
    ```
    **Verification:** N confirmed · M rejected before posting · K need author input
    ```

    If the **incomplete-review flag** is set (file list truncated, diff unavailable/truncated, or the PR exceeds GitHub's 3,000-file limit — see Phase 2 steps 6–7), add immediately after the files reviewed line:
    ```
    > ⚠️ **Incomplete review**: GitHub API limits prevented fetching the complete change set (<reason>). Files not enumerated were not reviewed.
    ```
    Never present an incomplete review as full coverage.

    If the aggregator's `suppressed` list is non-empty, count its entries by `reason` (`verified_fixed` vs `wont_fix`) and add after the files reviewed line (omit any zero part):
    ```
    **Previously addressed:** N verified fixed · M declined by author (won't fix)
    ```

    If there are **cross-cutting concerns**, add:
    ```
    ### Cross-Cutting Concerns
    - concern 1
    - concern 2
    ```

    Then add all **diff_comment** findings (general/cross-file findings) to the body. For each `diff_comment`, format as a collapsible section:
    ```
    <details>
    <summary><strong>CR-NNN</strong> &middot; Level &middot; <code>category</code> — Summary text</summary>

    Comment text here.

    > **Suggestion:** suggestion text

    > **Why it matters:** why_it_matters text

    Applies to: `file1.py`, `file2.py`

    <sub>Found by: agent1, agent2</sub>
    </details>
    ```

    Then add a **coverage table**:
    ```
    ### Agent Coverage
    | Agent | Role | Files | Findings | Blocking |
    |-------|------|-------|----------|----------|
    | spk-reviewer-security | security | 5 | 2 | 0 |
    ```

    End with:
    ```
    <sub>Generated by AI Review Team</sub>
    ```

    **Character limit**: If the body exceeds 65,000 characters, truncate the diff_comment sections (keeping the summary table and coverage) and append a note: "Some findings were omitted due to GitHub's character limit. See the full review in the local JSON file."

17. **Build inline review comments**: For each `inline_comment` from the aggregator output, create a review comment object:

    - `path`: the `location.file_path`
    - `line`: the `location.end_line` (GitHub uses this as the comment anchor)
    - `start_line`: the `location.start_line` — only include if `start_line != end_line` (multi-line comment)
    - `side`: map `location.side` — `"new"` or default → `"RIGHT"`, `"old"` → `"LEFT"`
    - `start_side`: same mapping as `side` — only include when `start_line` is included
    - `body`: format the comment as markdown:
      ```
      **Level** · `category` · confidence: X

      **Summary text**

      Comment text here.

      > **Suggestion:** suggestion text

      > **Why it matters:** why_it_matters text

      <sub>Found by: agent1, agent2 · CR-NNN</sub>
      ```

    **Important — line validation**: Inline comments can only reference lines that appear in the PR diff (added lines, removed lines, or context lines within diff hunks). Parse the diff from step 6 to determine valid line ranges for each file. For any `inline_comment` whose line range falls outside the diff hunks for that file, do NOT include it as an inline comment — instead fold it into the review body as an additional finding (formatted like the diff_comments above).

    **Comment limit**: If there are more than 50 inline comments, keep only the top 50 sorted by severity (severe > warning > question > info), then by confidence (high > medium > low). Fold the remaining comments into the review body. This stays well within GitHub's rate limits.

18. **Determine the review event**:
    - If the aggregator `summary.blocking` is `true` → `"REQUEST_CHANGES"`. `blocking` may only be true when at least one `severe` finding was **confirmed by a verifier** (step 13) — never on the strength of unverified specialist output.
    - Otherwise → `"COMMENT"`

19. **Dismiss existing AI review** (if one was found in step 8): Run `gh api repos/{owner}/{repo}/pulls/<number>/reviews/<review_id>/dismissals --method PUT -f message="Superseded by updated AI review"`. If this fails (e.g., insufficient permissions), continue anyway — the new review will still be posted.

20. **Submit the review**: Build a JSON payload file containing:
    ```json
    {
      "body": "<review body from step 16>",
      "event": "<event from step 18>",
      "comments": [<inline comment objects from step 17>]
    }
    ```
    Write this to a temporary file (e.g., `/tmp/ai-review-payload.json`). Then submit:
    ```
    gh api repos/{owner}/{repo}/pulls/<number>/reviews --method POST --input /tmp/ai-review-payload.json
    ```

    **Error handling**: If the API call fails due to invalid inline comment positions (lines not in the diff), remove the offending comments from the payload, fold them into the review body, and retry. If it fails for other reasons, report the error to the user and note that the review JSON was saved locally.

    Clean up the temporary payload file after submission.

### Phase 6 — Report

21. **Present results**: Output a summary to the user including:
    - The PR URL
    - The review event type (COMMENT or REQUEST_CHANGES)
    - Count of inline comments posted vs. total findings
    - Count of findings by severity
    - Verification outcome: how many candidates were confirmed, rejected (with one-line reasons), downgraded to `needs_human_context`, or passed through unverified
    - Counts of prior findings verified fixed or declined by the author, and of previously flagged findings still present at the head (if any)
    - The local path where the JSON review was saved
    - Any warnings (e.g., comments that couldn't be posted inline, character limit truncation)
    - Whether the review was incomplete due to GitHub API limits (truncated file list or diff, threads with more than 100 comments), and which files or threads were affected

## Notes

- **File exclusions**: Files matched by `.gitignore` or `.dockerignore` must NOT be reviewed by any agent unless the user explicitly includes them. The deterministic secrets scan (step 11c) still covers their diff hunks — a committed secret is a finding even in an ignored-pattern file.
- The deterministic secrets scan (step 11c) runs for **every** PR over the full diff. The `spk-reviewer-security` agent is risk-routed per step 11 — it is not invoked for docs-only or asset-only changes.
- Routing (step 11) is deterministic: `scripts/route-files.py` is the single source of truth for the path-based routing map; the dispatch agent only checks the plan semantically and flags cross-cutting concerns. Mechanical aggregation work (parsing, counting, sorting, numbering, coverage, schema validation) is done by the orchestrator in step 14, not by an agent.
- Launch as many specialist agents in parallel as possible for speed.
- Specialist findings are candidates until verified. A `severe` finding or a `REQUEST_CHANGES` event must always be backed by a `confirmed` verdict from a verifier agent (step 13) — never post unverified severe findings.
- The `$ARGUMENTS` variable contains any arguments the user passed: a PR number, a PR URL, or empty (the three modes in Phase 1 step 2).
- Do not post praise or positive feedback anywhere in the review — not as inline comments and not in the review body. Report only actionable or informative findings.

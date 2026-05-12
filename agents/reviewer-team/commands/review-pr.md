Review a GitHub Pull Request using the multi-agent code review pipeline and post findings as a GitHub review with inline comments.

## Instructions

### Phase 1 — Preflight

1. **Check GitHub CLI**: Run `../scripts/github-checks.sh`. If the script runs and doesn't have an exit code of 0 then report the script stdout to the suer and **stop**.

### Phase 2 — Gather PR Data

Run these commands in parallel:

4. **Get PR metadata**: Run `gh pr view <number> --json number,title,body,baseRefName,headRefName,headRefOid,url` to get PR details. Save these for the aggregator schema's `pr` field.

5. **Get repo identity**: Run `gh repo view --json owner,name --jq '.owner.login + "/" + .name'` to get the `OWNER/REPO` string needed for API calls.

6. **Get the diff**: Run `gh pr diff <number>` to get the unified diff content.

7. **Get changed files with status**: Run `gh api repos/{owner}/{repo}/pulls/<number>/files --jq '.[] | .status + "\t" + .filename'`. Map GitHub statuses to change type labels: `added` → **A**, `modified` → **M**, `removed` → **D**, `renamed` → **R**, `copied` → **C**.

8. **Check for existing AI review**: Run `gh api repos/{owner}/{repo}/pulls/<number>/reviews --jq '[.[] | select(.body != null) | select(.body | contains("<!-- ai-review-team -->"))] | last | .id // empty'`. Note the review ID if found — it will be handled in Phase 5.

9. **Fetch addressed review threads**: Query the GitHub GraphQL API to find review threads that have already been resolved or acknowledged by the PR author. This prevents the review from re-raising issues that have already been addressed.

   Run:
   ```
   gh api graphql -f query='
   query($owner: String!, $repo: String!, $number: Int!) {
     repository(owner: $owner, name: $repo) {
       pullRequest(number: $number) {
         reviewThreads(first: 100) {
           nodes {
             isResolved
             isOutdated
             path
             line
             startLine
             diffSide
             comments(first: 20) {
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

   From the results, identify **addressed AI review threads** — threads where:
   - The first comment matches AI review format (body contains `Found by:` with a `CR-` ID, or the severity/category pattern like `**warning** · \`category\``)
   - AND the thread meets at least one of these conditions:
     - **Resolved**: `isResolved` is `true`
     - **Author replied**: The thread has a reply from the PR author (a comment other than the first one, posted by a different user than the first comment's author)

   For each addressed thread, extract and record:
   - `file_path`: the thread's `path` field
   - `line`: the thread's `line` field (end line of the comment anchor)
   - `start_line`: the thread's `startLine` field (if present)
   - `category`: parsed from the first comment body (the text between backticks after the severity level, e.g. `security` from `**warning** · \`security\``)
   - `summary`: parsed from the first comment body (the bold text on the second line)
   - `status`: `"resolved"` if `isResolved` is true, `"replied"` if the author replied but did not resolve

   Save this as the **addressed findings list**. If there are no addressed threads (e.g., first review run, or no threads have been engaged with), this list is empty and no filtering will occur.

### Phase 3 — Multi-Agent Review Pipeline

This phase is identical to the `review-diff` pipeline.

10. **Filter excluded files**: Remove any files matched by `.gitignore` or `.dockerignore` from the changed file list before dispatching.

11. **Dispatch**: Use the Agent tool to launch the dispatch agent (subagent_type: `reviewer-dispatch`) with the full diff and changed file list. This agent analyzes the diff and creates a dispatch plan identifying which specialist agents to invoke.

12. **Run specialist agents in parallel**: Based on the dispatch plan, launch the appropriate specialist review agents in parallel using the Agent tool. Each agent receives:
   - The subset of files assigned to it
   - The relevant diffs for those files, clearly framed as unified diff format: lines prefixed with `+` are additions, lines prefixed with `-` are deletions, and unprefixed lines are unchanged context
   - Each file labeled with its change type: **A** = added, **M** = modified, **D** = deleted, **R** = renamed
   - The dispatch plan context
   - Instruction to output structured JSON conforming to `.claude/templates/review-schema.json`

   Use these agent definitions from `.claude/agents/`:
   - **reviewer-security** — ALWAYS run this, for all files
   - **reviewer-frontend** — for .ts, .tsx, .css, vite/eslint config
   - **reviewer-ui** — for .tsx, .css, images, theme files
   - **reviewer-ux** — for .tsx, route/form/nav components
   - **reviewer-backend-python** — for .py, pyproject.toml, alembic
   - **reviewer-python-quality** — for .py files
   - **reviewer-tests** — for test/spec files, conftest, vitest config
   - **reviewer-devops** — for .tf, Dockerfile, docker-compose, .github/workflows, Makefile
   - **reviewer-database** — for alembic/, .sql, SQLAlchemy models
   - **reviewer-docs** — for .md, mkdocs.yml, openapi specs
   - **reviewer-general-purpose** — fallback for unmatched files

   Each agent returns a single JSON block with `version`, `agent`, `summary`, and `comments` fields. See `.claude/templates/review-output-format.md` for the complete schema reference.

13. **Aggregate results**: Once all agents complete, use the Agent tool to launch the `reviewer-aggregator` agent (from `.claude/agents/reviewer-aggregator.md`) with all agent JSON outputs. Pass the PR metadata (title, description, base_ref, head_ref, commit_sha, pull_request_id) so the aggregator output includes the `pr` field. **Also pass the addressed findings list from step 9** — the aggregator will use this to suppress findings that have already been resolved or acknowledged by the PR author. The aggregator will parse, deduplicate (using `dedupe_key`), filter addressed findings, prioritize, and synthesize into the final report.

### Phase 4 — Save Review Locally

14. **Save the review JSON**: Generate a timestamp using `date +%Y%m%d_%H%M%S`. Create `.reviews/` if needed. Write the aggregator JSON to `.reviews/<timestamp>_pr<number>_review.json`. The file conforms to `.claude/templates/review-aggregate-schema.json`.

### Phase 5 — Post to GitHub

15. **Build the review body** (the top-level summary comment for the review). Format it as markdown:

    ```
    <!-- ai-review-team -->
    ## AI Code Review

    **Assessment:** <overall_assessment from aggregator>

    | Severe | Warning | Question | Info | Praise |
    |--------|---------|----------|------|--------|
    | N | N | N | N | N |

    **Files reviewed:** X / Y
    ```

    If `suppressed_as_addressed` is greater than 0 in the aggregator summary, add after the files reviewed line:
    ```
    **Previously addressed:** N finding(s) suppressed (resolved or acknowledged in prior review)
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
    | reviewer-security | security | 5 | 2 | 0 |
    ```

    End with:
    ```
    <sub>Generated by AI Review Team</sub>
    ```

    **Character limit**: If the body exceeds 65,000 characters, truncate the diff_comment sections (keeping the summary table and coverage) and append a note: "Some findings were omitted due to GitHub's character limit. See the full review in the local JSON file."

16. **Build inline review comments**: For each `inline_comment` from the aggregator output, create a review comment object:

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

    **Comment limit**: If there are more than 50 inline comments, keep only the top 50 sorted by severity (severe > warning > question > info > praise), then by confidence (high > medium > low). Fold the remaining comments into the review body. This stays well within GitHub's rate limits.

17. **Determine the review event**:
    - If the aggregator `summary.blocking` is `true` → `"REQUEST_CHANGES"`
    - Otherwise → `"COMMENT"`

18. **Dismiss existing AI review** (if one was found in step 8): Run `gh api repos/{owner}/{repo}/pulls/<number>/reviews/<review_id>/dismissals --method PUT -f message="Superseded by updated AI review"`. If this fails (e.g., insufficient permissions), continue anyway — the new review will still be posted.

19. **Submit the review**: Build a JSON payload file containing:
    ```json
    {
      "body": "<review body from step 15>",
      "event": "<event from step 17>",
      "comments": [<inline comment objects from step 16>]
    }
    ```
    Write this to a temporary file (e.g., `/tmp/ai-review-payload.json`). Then submit:
    ```
    gh api repos/{owner}/{repo}/pulls/<number>/reviews --method POST --input /tmp/ai-review-payload.json
    ```

    **Error handling**: If the API call fails due to invalid inline comment positions (lines not in the diff), remove the offending comments from the payload, fold them into the review body, and retry. If it fails for other reasons, report the error to the user and note that the review JSON was saved locally.

    Clean up the temporary payload file after submission.

### Phase 6 — Report

20. **Present results**: Output a summary to the user including:
    - The PR URL
    - The review event type (COMMENT or REQUEST_CHANGES)
    - Count of inline comments posted vs. total findings
    - Count of findings by severity
    - Count of findings suppressed due to previously addressed threads (if any)
    - The local path where the JSON review was saved
    - Any warnings (e.g., comments that couldn't be posted inline, character limit truncation)

## Notes

- **File exclusions**: Files matched by `.gitignore` or `.dockerignore` must NOT be reviewed by any agent unless the user explicitly includes them.
- Always run `reviewer-security` regardless of file types.
- Launch as many specialist agents in parallel as possible for speed.
- The `$ARGUMENTS` variable contains any arguments the user passed (PR number or URL).
- `praise` level findings should NOT be posted as inline comments — include them only in the review body summary to keep the PR clean.

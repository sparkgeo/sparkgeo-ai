Review a GitHub pull request with the review team and post the result as one GitHub review.

The deterministic steps run through `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/spk_review.py` (call it `TOOL` below). You orchestrate the agents. You do not route files, count findings, decide blocking, build the payload, or judge diff anchors yourself. The tool does those. Every tool command prints a summary; read it and act on its exit code.

## Phase 1: Preflight and mode

1. Run `${CLAUDE_PLUGIN_ROOT}/scripts/github-checks.sh` with no arguments. If it exits non-zero, show its stderr and stop.

2. Fix `<number>` and `<owner>/<repo>` from `$ARGUMENTS`:

   - **A PR number** (`123`): run `git rev-parse --is-inside-work-tree`. If it fails, stop with: "A bare PR number requires you to be inside the repository's local clone. Either `cd` into the repo, or pass the full PR URL instead." Then run `gh repo view --json owner,name --jq '.owner.login + "/" + .name'` for `<owner>/<repo>`.
   - **A PR URL** (`https://github.com/foo/bar/pull/123`): parse with `^https?://github\.com/([^/]+)/([^/]+)/pull/([0-9]+)(/.*)?$`. No local clone is required. The tool makes a shallow clone for the snapshot.
   - **No arguments**: require a local clone as above. Run `gh pr list --state open --limit 30 --json number,title,author,headRefName,updatedAt --repo <owner>/<repo>`, show the open PRs as a numbered list, ask which one to review, and wait. If there are none, stop and say so.

## Phase 2: Collect and snapshot

3. Run `TOOL collect --repo <owner>/<repo> --pr <number>`. It fetches the PR with its author, base and head SHAs, every changed file with pagination, the diff, every review thread with pagination, and the last AI review. It writes them to a run directory under `.reviews/pr<number>/<run_id>/` and prints the path as `run_dir`. Keep `run_dir` for the rest of the run.
   - Exit code 4 means the head moved while collecting. Run `collect` again.
   - Read the `warnings` list. Carry every warning into the final report.

4. Run `TOOL snapshot <run_dir>`. It checks out the head SHA into an isolated directory: a git worktree when you are in the repo's clone, a shallow clone otherwise. It prints `path`, `method`, and `verified`.
   - Exit code 5 means the snapshot could not be verified at the head SHA. Continue, but tell every agent `snapshot: none` and note it in the report. Agents then read pinned files with `TOOL fetch-file <run_dir> <path>`.

5. Run `TOOL route <run_dir>`. It writes `plan.json`: the manifest with change types and per-file reviewers, the excluded files with reasons, the agents to launch with their file lists and behaviour triggers, the repository config from `.github/spk-review.json` at the snapshot, and the convention files found. It prints the plan. Lockfiles, binaries, and generated files are routed to security only, in every mode. There is no `.gitignore` or `.dockerignore` filtering.

## Phase 3: Review

6. Launch every agent in `plan.json` `agents` in parallel with the Agent tool, `subagent_type` equal to the agent name. Give each agent exactly this, nothing more:

   ```
   run_dir: <run_dir>
   snapshot: <snapshot path, or none>
   output: <run_dir>/agents/<agent-name>.json
   PR: #<number> <title> by <author> (<head_ref> -> <base_ref>, head <head_sha>)
   PR description: <body, trimmed to 1500 characters>
   Conventions found at the snapshot: <list of available context_files, or none>
   Your files (A added, M modified, D deleted, R renamed):
   <one line per assigned file: status<TAB>path>
   Triggers: <the agent's triggers from plan.json, or none>
   Read plan.json for the full manifest and diff.patch for the diff. Write your JSON to the output path and reply with one line.
   ```

   Do not paste the diff into the prompt. The agents read `diff.patch` from the run directory. Do not relay agent JSON yourself; agents write their own files.

7. Run `TOOL ingest <run_dir>`. It validates every agent file against the contract, records failed or missing agents, checks each agent's per-file completion against its assignment, merges exact duplicates, numbers the candidates, and writes `merged.json`.
   - Exit code 6 means an agent failed or produced no usable file. Relaunch that agent once with the same prompt plus the validation errors it printed. Run `ingest` again. If it still fails, continue; the report will say the review is incomplete.

8. Launch `spk-reviewer-aggregator` with:

   ```
   run_dir: <run_dir>
   output: <run_dir>/aggregated.json
   Merge candidates in merged.json by root cause, rewrite them to the contract, and link legacy threads from threads.json. Reply with one line.
   ```

9. Run `TOOL verify-plan <run_dir>`. It validates `aggregated.json` and lists the findings that need independent verification: every severe finding, and warnings with medium or low confidence, cross-cutting warnings, and warnings that match a discussed or resolved earlier thread. It writes `verify/plan.json` with batches.
   - Exit code 2 means `aggregated.json` is invalid. Relaunch the aggregator with the printed errors and run `verify-plan` again.
   - If the plan has zero batches, skip step 10.

10. Launch one `spk-reviewer-verifier` per batch in parallel with:

    ```
    run_dir: <run_dir>
    snapshot: <snapshot path, or none>
    batch: <batch name>
    output: <run_dir>/verify/<batch name>.json
    Findings to verify: <the batch's findings copied from aggregated.json, with evidence and location>
    ```

11. Run `TOOL finalize <run_dir>`. It applies verification, drops pre-existing and style findings, computes counts and blocking from what is left, matches earlier threads by fingerprint, applies the publication budget, and writes `final.json`. The event is `COMMENT` unless a verified severe finding exists and the repository set `request_changes: true`.
    - Exit code 2 means a finding is over the word limit or otherwise invalid. Relaunch the aggregator with the printed errors, then run `finalize` again.

## Phase 4: Render and post

12. Run `TOOL render <run_dir>`. It writes `review-body.md` and `payload.json` with the head `commit_id`. Inline comments are built only for lines the diff parser finds in the hunks on the right side. Everything else goes into the body checklist.

13. Run `TOOL post <run_dir>`. It fetches the PR again and compares the head SHA. If the head moved it exits 3 without posting. Tell the user the PR changed during the review and ask whether to rerun from step 3 or post the review against the reviewed commit with `TOOL post <run_dir> --allow-stale`. On success it posts the review pinned to the reviewed commit, then marks the earlier AI review as superseded and dismisses it if it requested changes. It writes `post.json`.
    - Exit code 7 means posting failed after one retry with inline comments folded into the body. Report the error from `post.json` and the local path of `final.json`.

14. Run `TOOL cleanup <run_dir>` to remove the snapshot.

15. Run `TOOL usage <run_dir>`. It reads this session's transcripts, sums the API token usage of every agent launched for this run and your own share since collect, and measures the elapsed time. It prints a table and writes `usage.json`. It never fails the review; if it prints `usage unavailable` or a warning, carry that line into the report.

## Phase 5: Report

16. Tell the user, in plain sentences:
    - The PR URL and the review event.
    - The headline from `final.json` and the published findings as a short list: title and location.
    - How many findings were withheld, still open from earlier reviews, or rejected, with the local path of `final.json` for the details.
    - Whether coverage is complete. If not, every coverage note.
    - Every warning from `collect.json` and `snapshot.json`.
    - The token usage table and the elapsed time exactly as `TOOL usage` printed them, in a code block, as the last part of the report. Do not total or round the numbers yourself.

## Rules

- `$ARGUMENTS` is a PR number, a PR URL, or empty.
- Agents write their own JSON files. Never paste the diff or agent JSON into prompts or replies.
- Never edit `final.json`, `payload.json`, or the review body by hand. If something is wrong, fix the input and rerun the tool step.
- Never post without `TOOL post`. It is the only step that checks the head SHA and sets `commit_id`.
- Do not post praise. The tool renders only published findings.
- Add `.reviews/` to the repository's `.gitignore` if it is not there, and say so.

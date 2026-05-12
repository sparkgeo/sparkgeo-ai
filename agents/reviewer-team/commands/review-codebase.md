Perform a comprehensive review of the entire codebase (or a specified directory) using the multi-agent code review pipeline.

## Instructions

1. **Determine scope**: If `$ARGUMENTS` is provided, use it as the target directory or glob pattern. Otherwise, review the entire project from the repository root.

2. **Discover files**: Use Glob to find all source files in scope. Categorize them by type:
   - Frontend: `*.ts`, `*.tsx`, `*.css`, `*.module.css`, `vite.config.*`, `eslint.*`
   - Backend: `*.py`, `pyproject.toml`, `uv.lock`
   - Database: `alembic/**`, `*.sql`
   - Testing: `*test*`, `*spec*`, `playwright.*`, `conftest.py`, `vitest.config.*`
   - Infrastructure: `*.tf`, `Dockerfile`, `docker-compose.*`, `.github/workflows/**`, `Makefile`
   - Documentation: `*.md`, `mkdocs.yml`, `openapi.*`
   - Configuration: `*.json`, `*.yaml`, `*.yml`, `*.toml`, `*.sh`, `.env*`
   - Other: anything not matching above

3. **Create dispatch plan**: Based on the file categorization, determine which specialist agents to invoke. Use the file routing map from `.claude/agents/reviewer-dispatch.md` to assign files to agents.

4. **Run specialist agents in parallel**: Launch the appropriate review agents in parallel using the Agent tool. Each agent should receive:
   - The full list of files assigned to it
   - Instructions to READ and review each file (not just diffs — this is a full codebase review)
   - Context that this is a holistic codebase review, not a PR review
   - Instruction to output structured JSON conforming to `.claude/templates/review-schema.json` (each agent's definition includes the format)
   - For codebase reviews, `location.side` should be set to `"new"` since there is no diff context

   Use these agent definitions from `.claude/agents/`:
   - **reviewer-security** — ALWAYS run this, for all files
   - **reviewer-frontend** — for frontend files
   - **reviewer-ui** — for UI/styling files
   - **reviewer-ux** — for UX-relevant components
   - **reviewer-backend-python** — for Python/backend files
   - **reviewer-python-quality** — for Python files
   - **reviewer-tests** — for test files
   - **reviewer-devops** — for infrastructure files
   - **reviewer-database** — for database/migration files
   - **reviewer-docs** — for documentation files
   - **reviewer-general-purpose** — for any files not covered by specialists

   Each agent should look for:
   - Code quality issues, anti-patterns, and bugs
   - Architecture and design concerns
   - Missing tests or documentation
   - Security vulnerabilities
   - Performance issues
   - Consistency problems across the codebase
   - Technical debt and maintainability issues

   Each agent will return a single JSON block with `version`, `agent`, `summary`, and `comments` fields. See `.claude/templates/review-output-format.md` for the complete schema reference.

5. **Aggregate results**: Once all agents complete, use the Agent tool to launch the `reviewer-aggregator` agent (from `.claude/agents/reviewer-aggregator.md`) with all agent JSON outputs. Pass the structured JSON from each agent directly — the aggregator will parse, deduplicate (using `dedupe_key`), prioritize, and synthesize into the final report. Adapt the aggregator prompt to note this is a codebase review, not a PR review.

6. **Save the review**: Generate a timestamp using `date +%Y%m%d_%H%M%S`. Create the directory `.reviews/` if it doesn't exist. Write the aggregator JSON output to `.reviews/<timestamp>_codebase_review.json`. The file conforms to `.claude/templates/review-aggregate-schema.json` with `review_type` set to `"codebase"`.

7. **Present the review**: Output a human-readable summary to the user based on the structured JSON — group findings by severity, include file paths and line numbers, and tell them the file path where the full JSON was saved.

## Notes

- **File exclusions**: Files matched by `.gitignore` or `.dockerignore` must NOT be reviewed by any agent unless the user explicitly includes them. During file discovery, filter out all ignored files before categorizing and dispatching.
- This is a full codebase review — agents should READ files, not look at diffs
- Always run `reviewer-security` regardless of file types
- Launch as many specialist agents in parallel as possible for speed
- For large codebases, the `$ARGUMENTS` variable can be used to scope the review (e.g., `/review-codebase src/backend`)
- Each agent should focus on patterns and systemic issues, not just individual line-level findings

# Contributing to the Reviewer Team

This document covers how to add a new reviewer subagent or update an existing one. The reviewer team is a multi-agent pipeline (organizer → specialists → aggregator) that produces structured JSON findings consumed by `commands/review-pr.md` and `commands/review-codebase.md`.

Before adding anything new, check whether an existing reviewer can be extended. Prefer broadening an existing scope over creating a near-duplicate agent.

## Repository layout

```
agents/reviewer-team/
├── reviewer-dispatch.md          # Organizer: routes files to specialists
├── reviewer-<role>.md            # Specialist reviewers (one per file)
├── reviewer-aggregator.md        # Merges findings into the final report
├── commands/                     # Slash-command entry points
├── scripts/                      # Helper scripts (e.g. github-checks.sh)
└── templates/                    # JSON schemas + output format reference
```

## Adding a new reviewer

### 1. Pick a scope and role

Each specialist owns a narrow domain. Look at the existing roles in `templates/review-output-format.md` (`frontend`, `backend`, `ui_design`, `ux_accessibility`, `code_quality`, `security`, `database`, `documentation`, `infrastructure`, `testing`, `general`) — your new role should be distinct from these. If two specialists would overlap heavily on the same files, that is a signal to extend an existing agent instead.

Decide:

- **Codename** — `reviewer-<role>` (kebab-case, matches the filename)
- **Role** — a single snake_case word added to the role table in `templates/review-output-format.md`
- **File patterns** — the globs this reviewer should be routed to
- **Model** — `haiku` for mechanical checks, `sonnet` for typical review work, `opus` only when nuanced judgement (security, UX) is needed

### 2. Create the agent file

Add `reviewer-<role>.md` to this directory. Use this skeleton (mirrors `reviewer-backend-python.md`):

```markdown
---
name: reviewer-<role>
description: "One-line summary of what this reviewer covers and when it is invoked."
model: sonnet
tools: Read, Glob, Grep, Bash
maxTurns: 15
color: <pick one not already used>
---

You are the **<Role> Reviewer** for a code review team.

Your scope covers: <file patterns or domains>

You will be given a set of files and their diffs from a pull request. Review each file for <focus area>.

## Review Checklist

### <Topic 1>
- Specific check
- Specific check

### <Topic 2>
- Specific check

## When No Issues Are Found

If your review finds no meaningful issues, that is a valid and valuable outcome. Return `comments: []` with all severity counts at 0 and `blocking: false`. Write an `overall_assessment` confirming what you reviewed and that no issues were found. Do not fabricate low-value findings to fill the report — a clean review is more useful than manufactured noise.

## Output Format

Read `.claude/templates/review-output-format.md` for the structured JSON output schema, field reference, and examples.

- **agent.name**: `reviewer-<role>`
- **agent.role**: `<role>`
```

Frontmatter rules:

- `name` must match the filename without `.md`.
- `tools` should be the minimum needed. Most reviewers only need `Read, Glob, Grep, Bash`.
- `color` should not collide with another reviewer (`reviewer-dispatch` uses purple, `reviewer-security` uses red, `reviewer-backend-python` uses orange, etc.). Pick something distinct so dispatch logs are scannable.

Body rules:

- Keep the checklist scoped and concrete. If a check is shared with another reviewer, decide which one owns it and remove the duplicate.
- Always include the **When No Issues Are Found** section verbatim — the aggregator relies on agents producing valid empty reports.
- Always include the **Output Format** section pointing at `review-output-format.md` and declaring the agent identity. Do not redefine the schema inline.

### 3. Wire it into the dispatcher

Edit `reviewer-dispatch.md`:

1. Add a row to the **Available Agents** table (codename, model, one-line description).
2. Add entries to the **File Routing Map** for the globs this reviewer should match. Routing entries are arrays — include `reviewer-security` alongside your new reviewer unless your reviewer *is* security.
3. If your reviewer needs to fire under a special condition (e.g. "only when a migration appears alongside an API change"), add or update a rule in the **Dispatch Rules** list.

The routing map is union-based, so a file matching multiple globs is reviewed by all matching agents. Make sure your globs do not accidentally pull in unrelated files.

### 4. Register the agent identity

Edit `templates/review-output-format.md`:

1. Add a row to the **Agent Identity** table mapping your codename to its role.
2. If you introduced a new `category` value (only do this if no existing category fits), add it to the **category** table. Reuse existing categories whenever possible — the aggregator dedupes by `(category, file, summary)` and proliferating categories weakens that.

### 5. Update the run commands

Edit `commands/review-pr.md` and `commands/review-codebase.md`:

- Add your reviewer to the bullet list of agent definitions in step 12 ("Run specialist agents in parallel"), with the file types it handles.
- If your reviewer should ALWAYS run (like `reviewer-security`), say so explicitly in the **Notes** section.

### 6. Validate

Before opening a PR:

- **Lint frontmatter** — confirm `name`, `model`, `tools`, `maxTurns`, `color` are present and valid.
- **Dry-run dispatch** — invoke `/review-pr` against a PR that touches the files your reviewer should match, and confirm `reviewer-dispatch` includes your codename in its `agents` array and the `coverage_manifest`.
- **Confirm structured output** — your reviewer must emit a single JSON block conforming to `templates/review-schema.json`. The aggregator silently drops malformed output, so do not skip this.
- **Confirm aggregation** — check the final aggregator JSON includes your findings (or a coverage row showing your agent ran with zero findings).

## Updating an existing reviewer

The safe surface area for in-place edits:

- **Checklist items** — add, remove, or sharpen review topics inside the existing sections.
- **Wording in the role description, scope statement, or focus areas.**
- **Tools list** — narrow it if a tool is unused, or add one only if a checklist item actually requires it.

Edits that need extra coordination:

- **Changing the agent `name`** — rename the file too, update `reviewer-dispatch.md` (table + routing map + rules), update both command files, and update the identity table in `templates/review-output-format.md`. Old `.reviews/` JSON files will still reference the old name; that is fine.
- **Changing the agent `role`** — update `templates/review-output-format.md` and warn the aggregator coverage table will report the new role on the next run.
- **Changing the `model`** — flag this in the PR description, since it affects cost and latency for every review.
- **Changing the routing globs** — files that previously matched this agent will now be routed differently. Walk the routing map to confirm no files become unreviewed (the dispatch contract requires every file to land on at least one specialist or the general-purpose fallback).
- **Adding or renaming a `category`** — update `templates/review-output-format.md` and consider that the aggregator's dedupe logic uses category as a key.

When you change a reviewer's behavior, run `/review-pr` or `/review-codebase` against a known-quality PR and confirm the output still looks reasonable before merging.

## Style conventions

- **No fabricated findings.** Every reviewer must keep the "When No Issues Are Found" clause. The pipeline treats a clean review as a valid result.
- **Severity discipline.** Reserve `severe` for issues that genuinely block merge. Warnings should fix; questions should clarify; info and praise stay non-blocking.
- **No prose outside the JSON block.** Specialist reviewers must return a single JSON code block as their entire output. The aggregator strips nothing.
- **Reference the templates, do not inline them.** The schema lives in `templates/review-schema.json` and is described in `templates/review-output-format.md`. Reviewers should point at it, not copy it.

## Pull request checklist

When proposing reviewer-team changes:

- [ ] New or renamed reviewers have a matching entry in `reviewer-dispatch.md` (table, routing map, rules as needed).
- [ ] New or renamed reviewers have an identity row in `templates/review-output-format.md`.
- [ ] Both `commands/review-pr.md` and `commands/review-codebase.md` list the reviewer where appropriate.
- [ ] No file pattern is left without a routing target (general-purpose fallback still covers it).
- [ ] You tested the change end-to-end on at least one PR or codebase review.
- [ ] PR description names the reviewer added/changed and the rationale.

Request review from an AI working group member before merging.

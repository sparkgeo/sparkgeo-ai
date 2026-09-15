---
name: create-adr
description: Scaffold a new Architectural Decision Record (ADR) on its own branch. Use when the user asks to "create an ADR", "start a new ADR", "draft an ADR", or invokes /spk-design:create-adr. Finds (or asks for) the repo's ADR directory, determines the next sequential ADR ID, creates a branch, pre-fills the header of the repo's template (or a bundled MADR template), and walks through commit and push with the user's confirmation.
---

# Create ADR

Follow these steps in order. All paths are relative to the repo root.

## 1. Preflight

Run in parallel:
- `git rev-parse --show-toplevel` — confirm CWD is inside a git repo.
- `git status --porcelain` — must be empty. If not, stop and ask the user to commit or stash first; do not create a branch on a dirty tree.
- `git branch --show-current` — should be the default branch (`main` or `master`). If not, ask the user to confirm before continuing (they may be intentionally branching off another base).
- `gh --version` — if missing, warn the user that in-flight ADRs on remote branches cannot be detected and that an ID collision is possible.

## 2. Locate the ADR directory

Glob for existing ADR directories, in this order of preference:
`architectural_decision_records/`, `docs/adr/`, `docs/adrs/`, `docs/decisions/`, `adr/`, `adrs/`, `decisions/`.

- If exactly one exists, use it.
- If several exist, ask the user which one.
- If none exist, ask the user for a directory name, suggesting `adrs/` as the default, and create it.

Call the chosen directory `<adr_dir>` below.

## 3. Determine the next ADR ID

Collect IDs from all of:
- Filenames in `<adr_dir>` matching `adr-NNN-*.md` or `NNN-*.md` (case-insensitive).
- Any `ADR-NNN` entries in an ADR list/index table in `<adr_dir>/README.md`, if that file exists.
- `gh pr list --state open --json headRefName,title --limit 100` — extract `adr-NNN` from `headRefName` or `title` (case-insensitive). Skip if `gh` is unavailable.

`next_id = max(all_ids) + 1`, zero-padded to three digits (e.g. `014`). If no IDs are found anywhere, start at `001`.

## 4. Gather inputs from the user

Use AskUserQuestion or a plain prompt.

First ask whether an existing issue should seed the ADR:
- **Issue** (optional) — a GitHub issue number or URL. If given, fetch it with
  `gh issue view <ref> --json title,body,url` and use it to propose the title and
  context paragraph below (the user can still override both). Record the issue URL
  for the `## More Information` section. If `gh` is unavailable or the fetch fails,
  tell the user and continue without it.

Required:
- **Title** — short, human-readable (e.g. `Adopt OpenTelemetry for tracing`). If an issue was given, offer a title derived from it as the default.
- **Slug** — kebab-case, derived from the title; offer the derived value and let the user override. Used for both branch name and filename.

Optional (defaults: leave the template placeholder):
- **Deciders**, **Consulted**, **Informed** — comma-separated lists.
- **Context paragraph** — one-paragraph problem statement to drop into `## Context and Problem Statement`. If an issue was given, offer a paragraph summarized from its body as the default.

## 5. Create the branch

```
git checkout -b adr-<NNN>-<slug>
```

## 6. Copy and pre-fill the template

- Pick the template: if `<adr_dir>` contains one (a file named like `0_template.md`, `template.md`, or `adr-template.md`), use it. Otherwise copy this skill's bundled `template.md` (in the same directory as this SKILL.md).
- Copy it to `<adr_dir>/adr-<NNN>-<slug>.md`, matching the naming convention of existing ADR files if they use a different pattern.
- Replace the header fields the skill knows:
  - `ID` → `ADR-<NNN>`
  - `Status` → `proposed`
  - `Date` → today (`YYYY-MM-DD`, from `date -u +%Y-%m-%d`)
  - `Deciders` / `Consulted` / `Informed` → user input, or leave placeholder.
- Replace the top-level `# {short title...}` heading with the user's title.
- If the user supplied a context paragraph, replace the `## Context and Problem Statement` placeholder body with it.
- If an issue seeded the ADR, add a link to it under `## More Information` (or the template's equivalent section).
- Leave all other sections as template placeholders for the human to fill in.

## 7. Update the ADR index, if one exists

If `<adr_dir>/README.md` (or an index file the repo uses) contains an ADR list table, append a row for the new ADR immediately after the last existing row. Copy the formatting conventions of the existing rows exactly — including any status colouring (some repos use the `$${\color{...}status}$$` LaTeX hack) — and set the status to `proposed`. Leave any PR-link cell as `TBD`.

If there is no index, skip this step; do not invent one.

## 8. Commit and push

- Stage only the files this skill created or edited, by exact path.
- Show the user the staged diff (`git diff --staged`).
- Before committing, read `git log --oneline -10` to match the repo's commit-message style.
- Confirm with the user before committing, and again before pushing (push affects shared state and may trigger CI):
  ```
  git commit -m "Add ADR-<NNN>: <title>"
  git push -u origin adr-<NNN>-<slug>
  ```

## 9. Report outcome

Print:
- The new branch name and file path.
- If `.github/workflows/` contains a workflow whose triggers match ADR files or branches (grep for `adr` in the workflow files), note that it will likely act on the push (e.g. open a draft PR) and remind the user to update any `TBD` index cell with the PR link. Otherwise, offer to open a PR with `gh pr create`.
- A reminder that the body sections of the new ADR file are still placeholders and need human content.

## Notes / gotchas

- Use the `gh` CLI for all GitHub access — issues, PRs, and anything else remote. Never fetch github.com URLs with curl, web-fetch tools, or the GitHub REST API directly: repos may be private, and `gh` is the only tool carrying the user's authentication. If `gh` is unavailable, skip the remote step and tell the user, as described in each step above.
- Never bypass the dirty-tree check or push hooks. If a pre-commit hook fails, fix the underlying issue and create a new commit — do not `--no-verify`.
- Do not edit the global `MEMORY.md` or any settings during this skill.

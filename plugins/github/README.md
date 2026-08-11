# github

Sparkgeo GitHub workflows for Claude Code: a team of reviewer agents that review a pull request and post the findings to GitHub, plus a skill that writes and opens PRs from your current branch.

## Requirements

- [GitHub CLI](https://cli.github.com) installed and authenticated (`gh auth login`)
- Read access to the private `sparkgeo/sparkgeo-ai` repo

## Install

```
/plugin marketplace add sparkgeo/sparkgeo-ai
/plugin install github@sparkgeo-marketplace
```

The repo is private, so this needs git credentials that can read it — an SSH key on your GitHub account, or `gh auth login` followed by `gh auth setup-git` for HTTPS.

Or from a local clone:

```bash
git clone git@github.com:sparkgeo/sparkgeo-ai.git
```

```
/plugin marketplace add ./sparkgeo-ai
/plugin install github@sparkgeo-marketplace
```

Run `/plugin` any time to browse, enable, disable, or update installed plugins.

## Usage

### Review a pull request — `/pr`

```
/pr                                              # lists open PRs in the current repo, asks which to review
/pr 123                                          # PR number — must be run inside the repo's clone
/pr https://github.com/owner/repo/pull/123       # full URL — works from anywhere
```

Claude routes the diff to the relevant specialist reviewers (security always runs, plus frontend, UI, UX, Python, tests, devops, database, docs as applicable), merges and deduplicates their findings, then posts a single GitHub review with inline comments. The review requests changes if anything blocking was found, otherwise it is a plain comment. A copy of the raw findings is saved to `.reviews/<timestamp>_pr<number>_review.json`.

Re-running `/pr` on the same PR dismisses the previous AI review and skips findings you have already resolved or replied to.

## Notes

- Files matched by `.gitignore` or `.dockerignore` are excluded from review.
- Reviewing by URL from outside the repo skips that exclusion step — there is no local working tree to read.

Sparkgeo AI
-----------

Shared AI assistant configurations for Sparkgeo — agents, commands, rules, and MCP servers. This repo is the single source of truth for AI tooling used across the team. Clone once, run setup, and the configs are available on your machine.

---

## How it works

The repo stores configuration files that AI tools read from your home directory. `script/setup` creates symlinks from those tool directories into your local clone of this repo, so that:

- pulling the latest changes (`script/update`) takes effect immediately — no re-running setup
- nothing in your home directory is ever overwritten if a file already exists there

The mapping between repo directories and tool directories is defined in [`script/links`](/script/links). The current targets are for [Claude Code](https://claude.ai/code):

| Repo directory | Symlinked into | Purpose |
|---|---|---|
| `agents/*.md` | `~/.claude/agents/` | Specialist subagents (e.g. `@django-pro`, `@code-reviewer`) |
| `commands/*.md` | `~/.claude/commands/` | Slash commands available in chat (e.g. `/create-stac`) |
| `skills/*.md` | `~/.claude/commands/` | Additional slash commands sourced from the `skills/` directory |

To add support for another AI tool, add entries to `script/links` pointing at that tool's config directory.

---

## Setup

Requires: `git`, `bash` (v4+). Works on macOS and Linux.

```bash
git clone git@github.com:sparkgeo/sparkgeo-ai.git ~/sparkgeo-ai
cd ~/sparkgeo-ai
script/setup
```

To pull the latest configs and re-apply symlinks:

```bash
script/update
```

`setup` is safe to re-run. It skips files that are already correctly linked and warns about any conflicts without touching them.

---

## Adding content

**New agent** — create `agents/<name>.md`. For Claude Code, include this frontmatter:

```markdown
---
name: my-agent
description: One sentence shown in the agent picker. Be specific about when to use it.
model: opus   # opus | sonnet | haiku
---

System prompt goes here...
```

**New command** — create `commands/<name>.md`. The filename becomes the slash command: `commands/create-stac.md` → `/create-stac`.

After adding either, run `script/setup` to create the symlink.

---

## Scripts

| Script | What it does |
|---|---|
| `script/setup` | Creates symlinks defined in `script/links`. Safe to re-run; never overwrites. |
| `script/update` | `git pull --ff-only` then runs `script/setup`. |
| `script/links` | Manifest of `source_pattern:destination` pairs. Edit to add or remove symlink targets. |

---

## Table of Contents

[Guidelines](/guidelines.md)

[Rules](/rules/)

* [base](/rules/base.md)

[Agents](/agents/)

* [agnt-stac-guide](/agents/agnt-stac-guide.md)
* [architect-review](/agents/architect-review.md)
* [backend-architect](/agents/backend-architect.md)
* [code-reviewer](/agents/code-reviewer.md)
* [django-pro](/agents/django-pro.md)
* [fastapi-pro](/agents/fastapi-pro.md)
* [geospatial-frontend-developer](/agents/geospatial-frontend-developer.md)
* [javascript-pro](/agents/javascript-pro.md)
* [performance-engineer](/agents/performance-engineer.md)
* [security-auditor](/agents/security-auditor.md)
* [ui-ux-designer](/agents/ui-ux-designer.md)
* [ui-visual-validator](/agents/ui-visual-validator.md)

[Commands](/commands/)

* [create-stac](/commands/create-stac.md)

[MCP Servers](/mcp/)

# Sparkgeo AI

A shared repository of reusable AI skills, agent prompts, rules, and workflows for common tasks across Sparkgeo. Use it in Cursor or Claude Code. The goal is to make AI usage more consistent, higher quality, and easier to reuse across teams.

## What lives here

- **[agents/](agents/)**: Agent definitions (system prompts / specialist behaviors). Add one markdown file per agent.
- **[skills/](skills/)**: Reusable skills and step-by-step instructions or checklists for repeatable tasks.
- **[rules/](rules/)**: Baseline rules loaded into AI sessions (coding standards, git habits, org preferences).
- **[mcp/](mcp/)**: Notes, configs, or pointers related to Model Context Protocol servers used at Sparkgeo.
- **[marketplace/](marketplace/)**: Claude Code plugins, packaged for install. See the [github plugin README](marketplace/plugins/github/README.md) for how to add the marketplace and install plugins.

## Installing

Clone the repo, then copy or symlink the pieces you want into place. Use `~/.claude/` (or `~/.cursor/`) to make them available everywhere, or the project's `.claude/` (or `.cursor/`) to scope them to one repo.

```bash
git clone git@github.com:sparkgeo/sparkgeo-ai.git
cd sparkgeo-ai

# everywhere, for you
ln -s "$PWD"/skills/*  ~/.claude/skills/
ln -s "$PWD"/agents/*  ~/.claude/agents/

# or just one project
cp -r skills/some-skill /path/to/project/.claude/skills/
```

Symlinking means a `git pull` updates them in place. Copying means you can edit them locally without touching this repo.

Rules in [rules/](rules/) aren't auto-loaded — paste the parts you want into the project's `CLAUDE.md` (or `.cursor/rules/`).

Plugins under [marketplace/](marketplace/) install through Claude Code's `/plugin` command instead of being copied — see the [github plugin README](marketplace/plugins/github/README.md).

Prefer small, composable pieces: one agent per file, focused rules.

## Contributing

Contributions are welcome from all teams.

Before adding or substantially changing an agent, skill, rule, or workflow:

- Check if something similar already exists.
- Prefer improving existing content over creating duplicates.
- Reference relevant standards where appropriate (security, geospatial, or team-specific).

### Getting your PR reviewed

The repo operates on a community model — assume that no one is actively monitoring for new contributions. If you'd like feedback on your PR, request a review from a relevant team lead or domain expert. For general submissions without an obvious owner, request a review from [@yeelauren](https://github.com/yeelauren) or [@jbants](https://github.com/jbants) to route it for triage.

## Creating a basic skill

Add a folder with a `SKILL.md` file containing instructions. Example structure:

```markdown
---
name: my-skill-name
description: A clear description of what this skill does and when to use it
---

# My Skill Name

[Add your instructions here for the assistant to follow when this skill is active]

## Examples

- Example usage 1
- Example usage 2

## Guidelines

- Guideline 1
- Guideline 2
```

## Creating a basic agent

Add one markdown file under [agents/](agents/). Example outline:

```markdown
---
name: my-agent-name
description: When to invoke this agent and what it is responsible for
---

You are [role in one sentence — e.g. a senior backend reviewer for STAC services].

## Purpose

[What outcomes this agent optimizes for]

## Capabilities

- [Capability or topic area 1]
- [Capability or topic area 2]

## Constraints

- [What the agent should not do, or boundaries]

## How you work

1. [First step or habit — e.g. read surrounding code before suggesting edits]
2. [Second step]
```

# Sparkgeo AI

A shared repository of reusable AI skills, agent prompts, rules, and workflows for common tasks across Sparkgeo. Use it in Cursor, Claude Code, or any AI tool that supports skills and rules. The goal is to make AI usage more consistent, higher quality, and easier to reuse across teams. Skills follow the [agentskills.io](https://agentskills.io) spec.

## What lives here

- **[agents/](agents/)**: Agent definitions (system prompts / specialist behaviors). Add one markdown file per agent.
- **[skills/](skills/)**: Reusable skills and step-by-step instructions or checklists for repeatable tasks.
- **[rules/](rules/)**: Baseline rules loaded into AI sessions (coding standards, git habits, org preferences).
- **[mcp/](mcp/)**: Notes, configs, or pointers related to Model Context Protocol servers used at Sparkgeo.

## Using this repo

1. Add workflows inside the project repo (often `.cursor/` or `.claude/`), or in your editor’s user-level skills or rules folder so they apply globally.
2. Prefer small, composable pieces: one agent per file and focused rules.
3. When adding or improving workflows, open a pull request and request review from at least one AI working group member.

## Installing skills

Copy a skill folder to a location your tool discovers automatically.
Example — install `stac-agent` globally for Claude Code:

```sh
mkdir -p ~/.claude/skills && cp -r skills/stac-agent ~/.claude/skills/
```

Global installs apply to all projects. Project-level installs scope to one repo.

## Contributing

Contributions are welcome from all teams.

Before adding or substantially changing an agent, skill, rule, or workflow:

- Check if something similar already exists.
- Prefer improving existing content over creating duplicates.
- Reference relevant standards where appropriate (security, geospatial, or team-specific).

## Creating a basic skill

Follow the [agentskills.io skill creation guide](https://agentskills.io/skill-creation/) for the full spec. The template below is a minimal starting point.

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

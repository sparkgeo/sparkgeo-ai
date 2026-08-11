# Sparkgeo AI

A Claude Code plugin marketplace for Sparkgeo. It holds reusable skills, agents, and commands, packaged as plugins that you install from one place. The goal is to make AI usage more consistent, higher quality, and easier to reuse across teams.

## Install the marketplace

In Claude Code, add the marketplace:

```
/plugin marketplace add sparkgeo/sparkgeo-ai
```

Then browse and install plugins:

```
/plugin
```

Or install a specific plugin directly:

```
/plugin install github@sparkgeo-marketplace
```

## Plugins

| Plugin | What it provides |
|---|---|
| [github](plugins/github/) | A team of reviewer agents for pull request reviews, and a `/spk-pr` command with a skill to create GitHub pull requests from the active branch. |
| [docs](plugins/docs/) | The `spk-plain-docs` skill: a house style for technical documentation, derived from ASD-STE100 Simplified Technical English. |
| [python](plugins/python/) | Agents for Python development, starting with the `spk-fast-api` agent for designing, building, and reviewing production-ready FastAPI applications. |

## Repository layout

- **[.claude-plugin/marketplace.json](.claude-plugin/marketplace.json)**: The marketplace manifest. Every plugin is listed here.
- **[plugins/](plugins/)**: One directory per plugin. Each plugin has a `.claude-plugin/plugin.json` manifest and any of `skills/`, `agents/`, `commands/`, and supporting files.
- **[rules/](rules/)**: Baseline rules to load into AI sessions (coding standards, git habits, org preferences). These are not part of the marketplace — copy them into your project or user settings.

## Contributing

Contributions are welcome from all teams.

Before adding or substantially changing a plugin:

- Check if something similar already exists.
- Prefer improving an existing plugin over creating a duplicate.
- Reference relevant standards where appropriate (security, geospatial, or team-specific).

### Adding a plugin

1. Create a directory under `plugins/` with a `.claude-plugin/plugin.json` manifest:

   ```json
   {
     "name": "my-plugin",
     "description": "What this plugin does and when to use it",
     "version": "1.0.0",
     "author": {
       "name": "Your Name"
     }
   }
   ```

2. Add content in the standard component directories inside the plugin:
   - `skills/<skill-name>/SKILL.md` — reusable skills with step-by-step instructions.
   - `agents/<agent-name>.md` — agent definitions (system prompts / specialist behaviors).
   - `commands/<command-name>.md` — slash commands.

   Prefix every skill, agent, and command name (and its file or directory name) with `spk-`, e.g. `spk-pr-writer`, `spk-reviewer-security`, `spk-pr`. The prefix marks the component as coming from the Sparkgeo marketplace and avoids collisions with built-ins or components from other marketplaces.

3. Register the plugin in [.claude-plugin/marketplace.json](.claude-plugin/marketplace.json) with a matching `name`, `source`, `description`, and `version`.

4. Open a pull request and request review from at least one AI working group member.

### Getting your PR reviewed

The repo operates on a community model — assume that no one is actively monitoring for new contributions. If you'd like feedback on your PR, request a review from a relevant team lead or domain expert. For general submissions without an obvious owner, request a review from [@yeelauren](https://github.com/yeelauren) or [@jbants](https://github.com/jbants) to route it for triage.

### Creating a basic skill

A skill is a folder with a `SKILL.md` file:

```markdown
---
name: spk-my-skill-name
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

### Creating a basic agent

An agent is one markdown file under the plugin's `agents/` directory:

```markdown
---
name: spk-my-agent-name
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

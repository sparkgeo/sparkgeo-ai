# Sparkgeo AI

A shared repository of reusable AI skills, agent prompts, rules, and workflows for common tasks across Sparkgeo. Use it in Cursor or Claude Code. The goal is to make AI usage more consistent, higher quality, and easier to reuse across teams.

## What lives here

- **[agents/](agents/)**: Agent definitions (system prompts / specialist behaviors). Add one markdown file per agent.
- **[skills/](skills/)**: Reusable skills and step-by-step instructions or checklists for repeatable tasks.
- **[rules/](rules/)**: Baseline rules loaded into AI sessions (coding standards, git habits, org preferences).
- **[mcp/](mcp/)**: Notes, configs, or pointers related to Model Context Protocol servers used at Sparkgeo.
- **[guidelines.md](guidelines.md)**: High-level guidelines for using this repo and AI tooling consistently.

## Using this repo

1. Clone or submodule this repository next to your project, or copy individual files into a project’s `.cursor/`, `.claude/`, or equivalent directory.
2. Prefer small, composable pieces: one agent per file and focused rules.
3. When adding or improving a workflow or agent, add a pr and tag at least one other team member.

## Contributing

Contributions are welcome from all teams.

Before adding a new workflow:

- Check if a similar workflow already exists.
- Prefer improving existing workflows over creating duplicates.
- Ensure workflows reference relevant standards where appropriate.

## Creating a basic skill

Add a folder with a `SKILL.md` file containing instructions. Example structure:

```markdown
---
name: my-skill-name
description: A clear description of what this skill does and when to use it
---

# My Skill Name

[Add your instructions here that Claude will follow when this skill is active]

## Examples

- Example usage 1
- Example usage 2

## Guidelines

- Guideline 1
- Guideline 2
```


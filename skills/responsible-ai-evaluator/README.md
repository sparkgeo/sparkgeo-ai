# Responsible AI Evaluator

A Claude Code skill for evaluating whether a task is suitable for AI assistance based on Sparkgeo's 10 Principles for Responsible AI Use.

## Overview

Use this skill when you need to decide whether a task should involve AI. It guides you through an interactive evaluation that:

- Asks clarifying questions (one at a time)
- Shows a scorecard after each answer (how your task scores against the 10 principles)
- Provides a final recommendation: **Suitable** / **Proceed with Caution** / **Not Suitable**
- Offers guidance on any principle

**Note:** While `SKILL.md` works in any Claude interface (Cursor, Claude Code, Claude.ai, etc.), the usage instructions below focus on Claude Code. The core skill itself is interface-agnostic—you can use it wherever you can paste or load Claude instructions.

## How to Use

### Option 1: Load as a Rule (Easiest)

Copy `SKILL.md` into your `.claude/rules/` folder. Claude will automatically follow it.

### Option 2: Paste Into Context

Copy the content of `SKILL.md` and paste it into your Claude conversation. Then ask:

> "I want to evaluate if [my task] is suitable for AI using the Responsible AI Evaluator"

Claude will see the instructions and guide you through the evaluation.

### Option 3: Add to Project

1. Copy this folder into your project's `.claude/` directory
2. Reference SKILL.md in your Claude Code settings
3. Ask Claude to use the evaluator

## What Happens

You'll go through ~7 questions, one at a time. After each answer, you'll see a scorecard like:

```
| Principle | Status | Notes |
|-----------|--------|-------|
| 1. You own the output | ✅ PASS | Will review and own output |
| 2. Critical evaluation | ✅ PASS | Critical evaluation planned |
| ...
```

At the end, you'll get a recommendation and risk summary.

## Important

**This evaluator is itself an AI tool.** Its recommendations are AI-generated. You own the results. Apply your own judgment—don't blindly follow the recommendation.

See Principle 1: "You own the output" — this applies to the evaluator itself too.

## The 10 Principles

1. **You own the output** — Full responsibility for AI-generated content
2. **All AI-generated work must be critically evaluated by a human** — Review everything
3. **AI does not replace team collaboration and communication** — Talk to your team more than AI
4. **Validate work based on risk and impact** — Review according to importance
5. **Small changes win** — Keep AI-assisted changes focused and reviewable
6. **Never paste secrets or sensitive data** — Protect credentials and PII
7. **Use AI for acceleration, not authority** — AI assists; humans decide
8. **Follow established patterns** — Reinforce existing ways of working
9. **Document intent, not just output** — Explain WHY, not just WHAT
10. **If you don't understand, learn it or ask** — Ensure you can explain it

## Files

- **`SKILL.md`** — Instructions for Claude. This is all you need.
- **`README.md`** — This file.

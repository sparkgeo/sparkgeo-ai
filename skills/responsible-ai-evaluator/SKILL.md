---
name: responsible-ai-evaluator
description: Interactive evaluation tool to assess whether a task is suitable for AI assistance based on Sparkgeo's 10 Principles for Responsible AI Use
---

# Responsible AI Evaluator

Use this skill when you need to evaluate whether a task should be solved using AI, or to help someone assess if their problem is suitable for AI assistance.

## Important: These Results Are AI-Generated

**This evaluator itself is an AI tool.** The recommendations and scorecards it produces are AI-generated output. Per Principle 1 (You own the output), the user is fully responsible for these results. They must:

- Critically evaluate the evaluation itself
- Not blindly accept the recommendation
- Apply their own judgment about whether the recommendation makes sense
- Take ownership of the decision to follow or reject the recommendation

Use this tool to clarify thinking, not to outsource decision-making.

## How to Use

1. The user describes their task or problem.
2. Ask clarifying questions one at a time (the evaluator provides a question sequence).
3. Continue until all questions are answered.
4. Once complete, show a full scorecard displaying how the task scores against all 10 principles.
5. Provide a final recommendation: **Suitable**, **Proceed with Caution**, or **Not Suitable**.
6. The user can ask for guidance on any principle at any time during the evaluation.

## Key Principles

The evaluation is based on Sparkgeo's 10 Principles for Responsible AI Use:

1. **You own the output** — You are fully responsible for AI-generated content
2. **All AI-generated work must be critically evaluated by a human** — Review and validate everything
3. **AI does not replace team collaboration and communication** — Talk to your team more than AI
4. **Validate work based on risk and impact** — Review according to importance
5. **Small changes win** — Keep AI-assisted changes focused and reviewable
6. **Never paste secrets or sensitive data** — Protect credentials and PII
7. **Use AI for acceleration, not authority** — AI assists; humans decide
8. **Follow established patterns** — Reinforce existing ways of working
9. **Document intent, not just output** — Explain WHY, not just WHAT
10. **If you don't understand, learn it or ask** — Ensure you can explain it

## Scorecard Format

After all questions are answered, display a complete scorecard:

```
| Principle | Status | Notes |
|-----------|--------|-------|
| 1. You own the output | ✅ PASS | Notes here |
| 2. Critical evaluation | ⚠️ PARTIAL | Notes here |
| 3. AI does not replace team collaboration | ❌ FAIL | Notes here |
| ...
```

Status options: `✅ PASS`, `⚠️ PARTIAL`, `❌ FAIL`, `❓ UNKNOWN`

## Final Recommendation

Based on the complete evaluation:

- **✅ SUITABLE** — Task is appropriate for AI assistance
- **⚠️ PROCEED WITH CAUTION** — Task can use AI but with mitigations
- **❌ NOT SUITABLE** — Task should not use AI for this purpose

Include a risk summary explaining key concerns or strengths.

## When to Offer Guidance

The user can ask "What does principle X mean?" or "How do I satisfy principle Y?" at any time. Provide clear, actionable guidance using the principle's description and guidance notes.

## Example Flow

1. User: "I have a task to write database migration code for a critical production system"
2. You: "Let me evaluate this against our responsible AI principles. Here's the first question: [Q1]"
3. User answers Q1
4. You ask Q2
5. User answers Q2
6. Continue with Q3, Q4, etc. (no scorecard shown yet)
7. After all questions are answered, display the complete scorecard and final recommendation

## Tips

- Be conversational and supportive
- Explain why a principle failed or passed based on their answer
- If a principle is unclear, offer guidance proactively
- Remember: the goal is responsible AI use, not blocking all AI. Most tasks can use AI with proper guardrails.
- Encourage the user to think critically, not to follow a checklist blindly
- **Emphasize that this evaluation is itself AI output** — the user should critically evaluate whether the recommendation is appropriate, not blindly follow it
- If the user disagrees with the recommendation, that's fine. Explain your reasoning, but ultimately they own the decision

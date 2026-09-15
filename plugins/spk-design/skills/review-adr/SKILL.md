---
name: review-adr
description: Review an Architectural Decision Record (ADR) in two passes — a completeness gate first, then a deep review against the repo. Use when the user asks to "review an ADR", "critique this ADR", "check my ADR", or invokes /spk-design:review-adr. If the ADR is incomplete or its requirements are vague, the skill interviews the user in structured question rounds (design, architecture, security, simplicity, cost, and related lenses) instead of reviewing further, and offers to fold the answers back into the ADR.
---

# Review ADR

Review one ADR in two passes. Pass 1 is a completeness gate: a deep review of a
hollow or vague ADR wastes everyone's time, so do not start Pass 2 until the
gate passes. Only use the `gh` CLI for anything remote (issues, PRs, other
repos) — never curl or web-fetch github.com URLs.

## 1. Locate the ADR and gather context

- The ADR to review: from the user's argument (path, ADR ID, or title), or if
  ambiguous, list the ADR files found (glob the conventional directories:
  `architectural_decision_records/`, `docs/adr/`, `docs/adrs/`,
  `docs/decisions/`, `adr/`, `adrs/`, `decisions/`) and ask which one.
- Read the ADR in full.
- Read for context, in parallel:
  - Other ADRs in the same directory that this one links to, supersedes, or
    overlaps with (scan the index/README if one exists).
  - The repo itself: enough to know the stack and conventions the decision must
    live in — dependency manifests, infra/IaC directories, CI workflows, and
    any code the ADR names. Use sub-agents for broad searches; the reviewer
    needs conclusions, not file dumps.
  - Any issue or PR the ADR links to, via `gh issue view` / `gh pr view`.

## 2. Pass 1 — completeness gate

Judge the ADR against these checks. Quote the ADR when citing a failure.

- **No placeholders.** Template text (`{...}`, "TBD", empty sections) anywhere
  in Context, Decision Drivers, Considered Options, or Decision Outcome fails
  the gate. Placeholders in optional tail sections (e.g. More Information) are
  a note, not a failure.
- **Concrete problem statement.** A reader who knows the repo but not the
  discussion can state the problem back. "We need better observability" fails;
  "traces do not cross the queue boundary, so p95 regressions in the worker
  are invisible" passes.
- **Comprehensive requirements.** The decision drivers cover the forces that
  actually bear on this decision in this repo — including constraints the repo
  context reveals (existing stack, deployment target, team size) that the ADR
  is silent on. A driver list that would fit any decision fails.
- **Real alternatives.** At least two considered options that a reasonable
  team member might have argued for, each with pros and cons — not one option
  plus a straw man.
- **Justified outcome.** The chosen option is traceable to the drivers, and
  the Confirmation section says how compliance will be checked.

**Verdict:**
- **Pass** → tell the user the gate passed in one line, then go to Pass 2.
- **Fail** → do not review deeper. List what failed and why (with quotes),
  then go to step 3 and interview the user.

## 3. Interview mode (on gate failure)

Interview the user until the gaps are closed. Map the missing content as a
**design tree**: every open decision branches into the decisions that hang off
it. Work the tree in **rounds**. The **frontier** is every question whose
prerequisites are already settled — the questions you can ask *now* without
guessing at answers you haven't heard yet. Ask the whole frontier in one
round; a question that depends on another question still open this round
belongs to a later round.

Format every question as:

```
❓ **Q1** - **<question title>**: <question body, may include multiple choices>

➡️ <your recommended answer>
```

Finding *facts* is your job, never the user's. If a question needs a fact from
the repo or an issue, look it up (or dispatch a sub-agent) instead of asking —
only *decisions* go to the user. Draw questions from the lenses below, but only
the ones the gate failures and the repo context make relevant:

- **Design** — what problem is actually being solved, for whom, and what does
  "done" look like? What is explicitly out of scope?
- **Architecture** — where does this sit in the existing system? What does it
  couple to, what contracts change, what breaks if it's wrong?
- **Security** — what new surface, secrets, data flows, or trust boundaries
  does this introduce? Who can now do what they couldn't before?
- **Simplicity** — what is the most boring option that meets the drivers? What
  in the proposal exists for a need nobody has yet?
- **Cost** — build cost, run cost (infra, licences), and carrying cost
  (operations, upgrades, expertise). What does this cost at 10× usage?
- **Operability** — who gets paged, what do they see, and how is it rolled
  back? How is it monitored?
- **Data** — migration path, backwards compatibility, retention, and privacy
  or compliance obligations on the data touched.
- **Reversibility** — how hard is it to undo? What lock-in (vendor, format,
  API) is being accepted, and knowingly?
- **Delivery** — does the team have the expertise to build and own this? What
  is the smallest first slice?

Each round the user answers reshapes the tree — settled decisions push the
frontier outward. Recompute and ask the next round. The interview is done when
the frontier is empty. Then offer to fold the answers back into the ADR file
(edits shown to the user; committing is theirs to decide) and re-run the gate.

## 4. Pass 2 — deep review (only after the gate passes)

Review the ADR through the same lenses as step 3, now as critique rather than
questions, and check it against the repo:

- Does the chosen option fit the existing stack and conventions, or does it
  quietly introduce a second way of doing something the repo already does?
- Does it contradict or overlap an accepted ADR? Say which.
- Are the rejected options rejected for reasons the repo supports?
- Are the consequences (good and bad) honest — anything material missing?
- Is the Confirmation section actually checkable?

Report as:

1. **Verdict** — one line: accept as-is, accept with changes, or needs rework.
2. **Findings** — ordered by severity; each one cites the ADR text or repo
   evidence and says what to change.
3. **Questions** — anything genuinely undecidable from the repo, in the step-3
   question format.

Do not edit the ADR during Pass 2 unless the user asks; the deliverable is the
review.

## Notes

- The interview format in step 3 is adapted from Matt Pocock's `grilling`
  skill (https://github.com/mattpocock/skills), vendored here so this plugin
  has no external dependency.
- Never fetch github.com URLs with curl or web tools; `gh` carries the user's
  authentication and repos may be private.

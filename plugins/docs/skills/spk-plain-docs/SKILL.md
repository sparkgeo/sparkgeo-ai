---
name: spk-plain-docs
description: House style for technical software documentation — READMEs, guides, API docs, tutorials, reference pages, release notes, changelogs, CLI help text, design docs, proposals, ADRs, RFCs, and code comments meant for humans. Derived from ASD-STE100 Simplified Technical English, adapted for software, plus a list of LLM writing tics to remove. Read this before writing or editing any prose documentation, and when asked to make docs clearer, shorter, or less machine-written.
---

# Plain docs

Write so a tired reader who is not a native English speaker gets it on the first pass.

This style is derived from ASD-STE100 but is **not** STE conformance. Do not claim conformance, and do not try to recall the STE dictionary from memory — use the word list below and extend it.

## Which rules apply

Not every rule fits every document. Find the type first, then apply what binds.

| Document type | Apply | Suspend |
|---|---|---|
| Guide, tutorial, how-to, quickstart, CLI help | Everything | — |
| Reference: API docs, config keys, schema docs | Everything | Second person, where the text describes a field rather than instructing a reader |
| Proposal, design doc, ADR, RFC | Sentences, Word choices, LLM tics | Second person, task-shaped headings, hedge-cutting, the 20–25 word target |
| Release notes, changelog | Everything | — |
| Code comments for humans | Sentences, Word choices | Structure (it is about paragraphs and headings) |

**The LLM-tics rules are never suspended.** They apply to every type, including proposals. They are the part that survives whatever else the document needs.

For proposals and design docs specifically:

- **Hedges are load-bearing.** "Proposed", "deferred", "to be confirmed", "expected" mark real uncertainty, and a reader deciding whether to fund the work needs to see it. Cut empty hedges (*generally*, *typically*) and keep calibrated ones.
- **Repetition across sections is legitimate.** The same risk belongs in the summary, the body, and the risk table, because different readers enter at different points. Judge repetition inside a section, not across the document.
- **Headings name the subject, not a task.** "Design principles", not "Establish the design principles".
- **Longer sentences are allowed** where an argument needs a subordinate clause. Split run-ons and stacked nominalisations, not reasoning.
- **Diagrams and tables carry the argument.** Do not paraphrase a diagram in the paragraph under it. Say what the reader should conclude from it.

## Sentences

- One idea per sentence. Aim for 20 words or fewer in procedures, 25 in explanation. A long sentence is a signal to split, not to add commas.
- Active voice with a stated subject. "The server rejects the request", not "the request is rejected".
- One instruction per numbered step. If a step has an "and" joining two actions, make it two steps.
- Present tense. "The command returns a job ID", not "will return".
- Address the reader as "you". Say "the user" only when writing about a third party who is not the reader. (Guides and reference only — see *Which rules apply*.)
- Put the condition first: "If the build fails, check the log." Not "Check the log if the build fails."
- Three words maximum in a noun cluster. Unpack the rest with a preposition: "the config file for user authentication", not "the user authentication config file".
- Keep articles. "Open the file", not "Open file".
- One meaning per word throughout a document. If `key` means an API key, do not also use it for a map key without qualifying it.
- Say what a thing does before naming its options. Definition, then detail.

## Structure

- One topic per paragraph, and no more than about six sentences.
- Lead with the outcome the reader wants, then the steps. Background last, or in a linked page.
- Prose for reasoning, lists for parallel items, tables for lookups, code blocks for anything typed. Do not turn a two-sentence explanation into three bullets.
- Headings state the task: "Run the tests", not "Testing" or "Test execution".
- State prerequisites before step 1, not partway through.
- Note failure modes where they happen, not in a trailing troubleshooting dump.

## Deviations from STE

STE was written for aircraft maintenance manuals. These parts do not transfer:

- **Gerunds are fine in headings and titles.** "Running the tests" is good. Still avoid `-ing` forms as the main verb of an instruction.
- **No WARNING/CAUTION apparatus.** Use a normal note or a short sentence in place, unless the project already has a convention.
- **Keep real technical terms.** Idempotent, mutex, deserialise, backpressure — use them, and define them once at first use.
- **Code is exempt.** Never rewrite identifiers, flags, log lines, or config keys to fit a rule.
- **Sentence limits are targets, not gates.** One 30-word sentence that carries an idea cleanly beats two clumsy short ones.

## Word choices

| Instead of | Use |
|---|---|
| utilise, leverage | use |
| in order to | to |
| prior to / subsequent to | before / after |
| commence, initiate | start |
| terminate | stop, or end |
| attempt | try |
| assist | help |
| facilitate, enable (of a tool) | let, or help |
| ensure | make sure |
| perform a backup | back up |
| additional | more, extra |
| approximately | about |
| sufficient | enough |
| functionality | features, or what it does |
| methodology | method |
| in the event that | if |
| at this point in time | now |

Pick one and hold it: **delete** for data and records, **remove** for files, packages, and config entries.

Cut on sight: simply, just, easily, obviously, of course, note that, please. They add nothing, and they blame the reader when the step fails.

Cut marketing adjectives from docs: robust, seamless, powerful, comprehensive, rich, blazing-fast.

<!-- Add product terms and their approved spellings here. -->

## LLM tics to remove

These are the strongest signals that prose was machine-written. Check for them last, on the finished draft.

- Preamble that restates the task or the heading before answering. Start with the answer.
- "It's important to note that", "It's worth mentioning", "Keep in mind that". Delete the frame and keep the fact.
- "Let's dive in", "In today's fast-paced world", and any warm opener.
- "Not just X, but Y" and "isn't about X, it's about Y".
- Defaulting to three of everything — three bullets, three adjectives, three clauses. Use the number of items that exist.
- Hedges with no content: generally, typically, often, usually. Either state the condition it depends on, or state the fact.
- A closing paragraph that repeats what was just said. Only summarise a document long enough to need it.
- Bold on random mid-sentence phrases for emphasis.
- Every other clause set off with an em dash. Vary the joins.
- A final uplifting sentence about how easy or powerful this now is.

## Before finishing

1. Name the document type, and check you applied the right ruleset.
2. Read the first sentence alone. Does it say something, or introduce something?
3. Check each numbered step has exactly one action.
4. Search the draft for `ing`, `ensure`, `simply`, `utilis`, `note that`.
5. Count the `A, not B` constructions. More than two in a document is a tic.
6. Delete the last paragraph and see whether anything is lost.

---
title: MarkdownFlow Literal Prompts
status: implemented
owner_surface: learner
last_reviewed: 2026-10-26
canonical: true
---

# MarkdownFlow Literal Prompts

This contract applies only to native MarkdownFlow 2.0 course and Profile prompts.
The MarkdownFlow 1.0 SDK, runtime and teacher preview contracts are unchanged.

Scripts, constraints, extras and authored verbatim text retain their original
contents. Ordinary `{{...}}` is never replaced with a value from memory, including
known values, zero, false, unavailable values, inline code, HTML and math. No
`unavailable_learner_value` metadata is introduced in new prompts. To use a
remembered fact, instruct the model to read authorized memory or use `recall`.
Absent memory remains unknown; brace text is not learner evidence.

The memory projection contains whole values within its existing budget. Only
host-priority keys receive priority; brace text does not prioritize a value or
insert a budget-omitted answer into the script. Complete input-budget checks
still include the authored source, memory, history, tool arguments and returns.
A verbatim completion anchor and a focused authored answer reference use the
same literal source. Profile control validation likewise compares literal
option values rather than substituting from the current learner snapshot.

New sessions no longer snapshot values for prompt substitution. Historical
`initial_variables` snapshots remain readable for recognizing old native host
prompts. Deletion and nickname refresh match literal sections or the historical
expanded sections independently, then rebuild only recognized engine-owned
initial memory/script/constraints. The compatibility matcher reproduces old
inline-code, HTML, math, escape-parity, malformed-example and main-script
collection behavior. Unrecognized sections, learner messages, tool returns,
extras and already displayed teaching are preserved. No 1.0 session is migrated.

This change retains native `variable` and `initial_variables` field names and
the existing declaration/admission rules. Question-key naming, interaction
collection semantics and authoring/preview migration are separate work in PR
#3181, which is based on the literal-prompts branch. Neither PR changes the
1.0 execution path or relaxes the release-only dependency gate.

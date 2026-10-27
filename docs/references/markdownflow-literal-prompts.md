---
title: MarkdownFlow Literal Prompts
status: implemented
owner_surface: learner
last_reviewed: 2026-10-27
canonical: true
---

# MarkdownFlow Literal Prompts

Native MarkdownFlow 2.0 sends a new session's authored script and teaching brief
without server-side variable substitution. Script, brief and extra-document bodies
retain their source text inside the existing request envelope. System instructions,
separate memory, tools and learner input are still included through their existing
paths. The model may interpret authored references using memory or recall; this
contract does not require the model to display brace notation literally.

The memory budget, referenced-key priority, collection rules, read/write permissions
and recall limits stay unchanged. The existing variable and initial_variables fields,
substitution utility and Profile interaction protocol also stay unchanged. In
particular, a dynamic Profile option still uses its existing resolved machine value;
this change does not introduce a literal-option protocol.

The initial prompt is assembled only for new sessions. Existing sessions keep saved
prompts, pending controls, accepted answers and learner/tool history. Previously
expanded text is not migrated back to source. Existing nickname/deletion handling
for expanded sessions remains in place. For a prompt whose script already matches
its authored source, those refreshes update the memory envelope without expanding
the script or brief; a recognized explicit brief update also uses source text.

Stopping substitution removes the path that previously embedded a complete memory
value in the script even if it did not fit the bounded memory block. A model may
need recall or may be unable to read an oversized value. Deterministic interpolation
is no longer guaranteed. Existing option-value validation, completion guards and
conservative answer-reference fallbacks remain unchanged.

This work adds no field renaming, history matcher, cache/schema migration, frontend
change, package release or deployment. It does not change the 1.0 SDK/runtime.
Question-key migration remains separate work in PR #3181.

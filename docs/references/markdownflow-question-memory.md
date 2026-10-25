---
title: MarkdownFlow Question Memory
status: implemented
owner_surface: learner
last_reviewed: 2026-10-25
canonical: true
---

# MarkdownFlow Question Memory

This contract applies to the native MarkdownFlow 2.0 runtime and current course
authoring/preview. MarkdownFlow 1.0 retains its existing behavior.

MarkdownFlow 2.0 has questions and remembered answers. It has no variable declarations
or template substitution. In `?[%{{ What is your goal? }} A | B | ...Your answer]`,
`What is your goal?` is the question and the exact key under which memory stores
the accepted answer. The options and placeholder continue to define the controls.
The model's `interact` tool carries this text in its `question` argument.

Trim only surrounding whitespace. Preserve interior spaces, punctuation, Unicode,
quotes and backslashes literally. The first `}}` closes the question marker;
blank questions, internal control characters and embedded closing pairs are
invalid. The existing durable memory key limit is 255 Unicode codepoints;
oversized questions are rejected, never shortened. Questions are not programming identifiers. Do not create a separate
variable definition or an alternative normalized identifier. Repeated identical
questions address the same memory key; different text addresses different keys.

Only the leading `%{{...}}` in a control binds an answer. The existing option
delimiters, escapes and brace grouping remain compatible with the browser
renderer; grouping inside an option never reads or writes memory.

A control without `%{{...}}` can collect an answer without retaining it under a
question key. Confirm controls never write an answer. Existing answer validation,
read-only memory restrictions and host persistence authorization still apply.

Outside an authored interaction, `{{...}}` and `%{{...}}` are ordinary source
text. The engine never replaces them with memory values, never treats them as
memory reads or declarations, and never creates a question from them. Script,
constraints, extras and authored verbatim text retain their original contents.
To use a learner's remembered answer, instruct the model to use the relevant
question from its authorized memory context or the read-only `recall` tool.
Questions being asked again remain unavailable until the current answer arrives.

New native interaction/session data uses `question`. Readers accept historical
pending interactions carrying `variable` and preserve their original memory keys.
The pinned rendering libraries and existing application wire/database contracts
may still carry old field names inside explicit compatibility adapters. Those
names do not introduce a second authoring concept or enable substitution.
Historical teaching and learner messages are not rewritten as new answers.

## Authoring and preview boundaries

The parse response includes `engine_version`. Native 2.0 returns `questions`;
1.0 retains its extracted and saved-definition `variables` for existing preview
values. The editor enables question mode only for 2.0. This compatibility shape
does not change the 1.0 execution engine.

The upstream 0.3.3 editor baseline already removed variable authoring controls.
Do not restore ignored variable-list props when selecting the legacy insertion
mode. Preview memory and legacy visibility remain application-owned behavior.

Every active native question marker is validated before saving or parsing a
lesson or publishing a Profile document. Blank or internally control-bearing
question text is an input error, not an unnamed answer. Controls that omit the
marker and inactive examples remain valid. Course authoring returns the existing
invalid-parameter API code (2001) with localized question guidance.

Native question rows remain visible. Legacy definition-backed hide, unused and
restore actions are unavailable in native previews; old stored visibility flags
cannot hide an authored question. Fixed system-context display exclusions remain.
1.0 retains its existing visibility controls and preferences.

Historical native sessions may contain already-expanded inline code, HTML and
math references. The read-only compatibility matcher recognizes these old host
sections so deletion and nickname refresh can remove stale values. It never
introduces substitution into new authored prompts or rewrites learner/tool history.

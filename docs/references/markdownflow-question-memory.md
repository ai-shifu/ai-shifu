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

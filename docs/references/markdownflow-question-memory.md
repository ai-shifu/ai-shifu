---
title: MarkdownFlow Question Memory
status: implemented
owner_surface: learner
last_reviewed: 2026-10-26
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

Only authored interactions declare question keys. Standalone brace groups never
create a question or authorize an answer binding. Literal prompt assembly and
historical expanded-prompt compatibility are defined by the prerequisite
[literal-prompt contract](markdownflow-literal-prompts.md) in PR #3188.
Questions asked again remain unavailable until the current answer arrives.

New native interaction/session data uses `question`. Readers accept historical
pending interactions carrying `variable` and preserve their original memory keys.
The pinned rendering libraries and existing application wire/database contracts
may still carry old field names inside explicit compatibility adapters. Those
names do not introduce a second authoring concept or enable substitution.
Historical teaching and learner messages are not rewritten as new answers.
Already-issued pending questions retain admission when their unique historical
`interact` call carries the old `variable` binding, including a former standalone
`%{{...}}` declaration. This exception is checked only while accepting that saved
pending answer. New calls continue to use the current question-only allowlist,
and read-only restrictions still apply. The actual answer is persisted normally;
its ownership fingerprint lets later durable edits refresh the stored session.

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

Historical host prompt refresh follows the prerequisite literal-prompt contract.
Question/session readers retain historical answer keys without rewriting learner
or tool history.

---
title: MarkdownFlow Authored Input Hints
status: implemented
owner_surface: learner
last_reviewed: 2026-10-07
canonical: true
---

# MarkdownFlow Authored Input Hints

In `?[%{{path}} First | Second | ...Describe your project]`, the trailing
`...Describe your project` declares a text-input placeholder. It is not an
additional selectable answer. MarkdownFlow 2.0 occasionally emits that hint
both as an option and as the placeholder of its `interact` tool call.

Before deferring an interaction, the engine removes such an extra option only
when the main lesson script uniquely identifies the intended controls:

- The variable must match, including an absent variable.
- After removing hint-only options, every remaining display and stored value
  must match the author's choices in the same order.
- The generated placeholder must be absent or equal to the author's decoded
  placeholder or its exact authored escaped spelling. The extra option must have
  that hint as both display and stored value, using either exact spelling for
  each field, optionally prefixed with the notation's `...` marker. Arbitrary
  model text is not unescaped for this comparison.
- A pair explicitly declared as a real choice is never removed. Distinct
  compatible author questions yielding conflicting repairs are left unchanged.
- Single and multiple choice remain distinct. A repaired question keeps the
  author's input placeholder and permits free text; a question with no choices
  becomes text-only.

Question examples inside fenced or indented code, HTML comments, and Markdown links do not
authorize a repair. Teaching briefs and extra documents do not define the
lesson's controls. Dynamic questions, different variables, reordered or changed
choices, different placeholders, and independently valued real buttons are
unchanged. This is a narrow notation correction, not a general restriction on
adaptive questions or a reinterpretation of arbitrary model text.

The same correction applies to saved pending interactions before resumption.
Conversation history, completed answers, and learner progress are preserved;
old, already answered questions are not rewritten or reset. New answers use
the corrected pending spec and continue through the existing memory and
MarkdownFlow frontend protocols. No provider retry, schema migration, package
release, or additional frontend event is required.

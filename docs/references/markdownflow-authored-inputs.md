---
title: MarkdownFlow Authored Input Hints
status: implemented
owner_surface: learner
last_reviewed: 2026-10-14
canonical: true
---

# MarkdownFlow Authored Input Hints

HTML comments (`<!-- ... -->`) are teacher notes. Teaching requests exclude
them from lesson scripts, teaching constraints, and extra reference documents
before learner-variable substitution. Inline, multiline, repeated, and unclosed
comments are excluded; an unclosed comment ends at its document boundary.
Visible text and line boundaries remain intact, and literal comments in Markdown
code examples remain available to teach. Stored author documents are unchanged.
Indentation that continues a paragraph or list item does not turn an author note
into a code example; those comments are still excluded.
CommonMark block parsing identifies real code ranges inside lists and blockquotes.
Markers and variable reads in those examples remain literal and do not declare
runtime controls, memory keys, or substitution dependencies.

Commented interactions and variable markers do not declare runtime controls,
memory keys, or syntax requirements. Resumed 2.0 feedback references use the same
filtered script. Recognized older first prompts are projected from their exact
initial values before being resent; arbitrary learner messages and memory values
are never globally stripped or regenerated from current values.

Legacy content-block history also projects recognized generation prompts from
their persisted source block and exact original quoted substitutions. Saved rows,
learner literals, and assistant history remain unchanged. Missing or ambiguous
provenance and historical next-interaction notes without their source snapshot
retain their original bytes rather than guessing at learner evidence.

Inline-code delimiters are indexed once per authored document. Unmatched delimiter
lengths cannot trigger repeated scans of the remaining input before a model call.
Delimiter pairs stay within one parsed inline block; headings, separate list
items, quotes, and raw HTML blocks cannot join unrelated backticks to hide notes.
Real code spans can still continue across a paragraph's soft line breaks.
HTML attributes use a bounded state scanner; the block parser also bypasses its
dependency's backtracking generic-tag rule when recognizing raw HTML blocks.

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

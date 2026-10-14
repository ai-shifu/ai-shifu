# Filter MarkdownFlow author comments before model requests

## Purpose / Big Picture

Teachers can keep HTML author notes in MarkdownFlow documents without those
notes reaching the teaching model or declaring interactions and learner variables.
Saved source remains available in the editor. See the durable behavior in
[authored input hints](../../references/markdownflow-authored-inputs.md).

## Progress

- [x] 2026-10-14 11:16 CST: Traced initial prompts, resumed history, feedback references,
  and legacy teaching/preview construction; verified the 1,019-test engine baseline.
- [x] 2026-10-14 11:24 CST: Added the filter, model-bound projections, and nickname
  and deleted-memory compatibility regressions.
- [x] 2026-10-14 11:27 CST: Verified 1,206 offline tests and the repository checks;
  regenerated knowledge indexes for the completed plan before the final gate.

## Surprises & Discoveries

The 2.0 engine sends raw documents initially and quotes authored sections again
on answer resumption. Filtering only the initial prompt misses those references
and old saved first prompts. Legacy preprocessing already hides common comments,
but repeated inline comments and unclosed notes can still reach the model.
The host nickname refresh also reconstructs the initial script and needed the
same filtered-source contract as memory deletion.

## Decision Log

- Keep source documents unchanged; execute a separate filtered bundle.
- Filter each authored document before variable substitution, preserving learner
  values and learner messages even if they contain HTML comment notation.
- Preserve literal examples in fenced, inline, and indented Markdown code. Keep line boundaries so
  legacy block positions remain stable.
- Project old first prompts only when their authored prefix can be reconstructed
  exactly from the initial memory snapshot; never rewrite arbitrary conversation.

## Outcomes & Retrospective

The authored-comment filter is implemented for 2.0 teaching, feedback references,
and recognized old initial prompts, plus legacy teaching/preview construction.
All 1,206 engine and affected host regressions pass, including source preservation,
learner literals, nickname refresh, and memory deletion. The repository-wide gate
also covers the updated documentation indexes. No deployment was performed.

Unknown historical prompt layouts and old bounded prompts whose original
substitutions cannot be recovered remain unchanged rather than guessing at
learner evidence. Legacy library behavior for inline and indented code remains
governed by the currently pinned release; fenced literals are provider-tested.

## Context and Orientation

`src/api/flaskr/service/learn/agent/engine/script.py` composes 2.0 prompts.
`engine.py` derives interaction and memory rules and emits feedback references.
`memory_context.py` recognizes the engine-owned first prompt. Legacy teaching
and preview use `context_v2.py`. Memory deletion may re-render authored sections
and must follow the same filter contract, as must nickname refresh in `nickname.py`.

## Plan of Work

Add a fence-aware HTML comment filter, use a filtered ScriptBundle throughout
2.0 execution, project compatible old prompts, and apply the filter at legacy
model-bound construction. Cover visible content, authored notes, code literals,
learner data, resume, and memory deletion with offline tests.

## Concrete Steps

1. Add the filter and prompt projections without changing stored source.
2. Add request-level and compatibility regression cases.
3. Run the complete engine suite, affected host tests, and lefthook gates.
4. Commit to the task branch and open a ready PR; never merge into main.

## Validation and Acceptance

Model requests contain visible authored instructions and code examples, while
author comments do not appear in initial documents or focused answer references.
Commented markers grant no runtime authority. Old recognized first prompts are
filtered without altering initial values, later messages, or appended learner
text. Comment filtering remains compatible with memory deletion. Required
engine tests and repository checks pass.

## Idempotence and Recovery

Filtering is idempotent and runs on copies. No data migration, dependency release,
environment change, or source-document rewrite is required. Reverting this PR
restores previous request composition.

## Interfaces and Dependencies

Use the existing ScriptBundle, session initial-variable snapshot, model-history
projection, and MarkdownFlow constructors. No frontend protocol or analytics
contract changes are needed.

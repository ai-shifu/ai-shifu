---
title: Filter only authored lesson comments
status: active
owner_surface: learner
last_reviewed: 2026-10-14
---

# Filter only authored lesson comments

## Purpose / Big Picture

Implement the authored-comment boundary in
[MarkdownFlow authored inputs](../../references/markdownflow-authored-inputs.md)
without filtering arbitrary model messages.

## Progress

- [x] 2026-10-14 UTC: Confirm source-only filtering and preservation of code examples.
- [x] 2026-10-14 UTC: Remove gateway filtering and reuse existing source-rendering paths.
- [x] 2026-10-14 UTC: Pass offline engine tests, complete learn-service host tests, and repository gates.
- [ ] 2026-10-14 UTC: External acceptance remains tracked in PR #3133, including CI/review and maintainer approval.

## Surprises & Discoveries

Native 1.0 parsing fixes block positions before variable substitution. Filtering
its input document would change those positions; execution copies must retain
them. The native dependency already has its own comment/code preprocessing.

## Decision Log

Use CommonMark parsing with marked copies to identify original comment ranges;
do not rebuild Markdown or introduce separate lexer modules. Apply filtering
before variable substitution. Reuse exact script-section matching for existing
nickname/deletion refresh and request-only history projection.
For legacy saved prompts, reuse the native message assembler to restore code,
output instructions, and next-interaction context before exact source matching.

## Outcomes & Retrospective

Local verification passed, including 2,671 host tests (93 skipped) and the full
offline engine suite. Live CI/review and external maintainer acceptance are
tracked in PR #3133; this plan remains active until that acceptance. No merge
has been authorized.

## Context and Orientation

`context_v2.py` wraps the legacy runtime. `agent/engine/script.py` renders 2.0
prompts; `memory_context.py`, `nickname.py`, and `deleted_memory.py` maintain the
known initial prompt during resume and profile refresh.

## Plan of Work

Filter authored source, preserve dynamic values, verify original block positions
and stored history, then follow CI and live review on the pushed head.

## Concrete Steps

Run the full offline engine suite and affected host tests separately, check
development tools, and run `lefthook run pre-commit --all-files`. Commit and push
to the existing PR branch, update its description, and recheck review after five minutes.

## Validation and Acceptance

Actual model payloads omit authored notes while retaining learner/profile values,
code examples and assistant/tool history. Fresh and resumed sessions, nickname
updates and deletion refresh preserve this boundary. Legacy indexes/types and
public source remain identical. Current applicable CI checks must finish.

## Idempotence and Recovery

The filter does not write source or database migrations. Unknown saved prompt
formats are retained. Changes can be reverted through the feature branch.

## Interfaces and Dependencies

Use `markdown-it-py==4.0.0` and the standard-library HTML parser for source
recognition. Keep the existing MarkdownFlow pins and model gateway contract.

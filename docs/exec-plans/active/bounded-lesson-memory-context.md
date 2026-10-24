# Bound Lesson Memory Context

## Purpose / Big Picture

After merged #3028, bounded supplementary reads still leave canonical/profile and
session memory unbounded in the initial model prompt. Give the complete memory
JSON section one shared budget while preserving exact named answers and stored
history. This is a focused next step in the workspace's MDF 2.0 memory milestone.

## Progress

- [x] 2026-10-07 10:14 UTC: Verified #3028 main 02b5f60d2 matches validated sim
      50cf2952e. All technical CI passed; CodeRabbit incremental review stopped after
      manual merge without extending coverage beyond 0552dba4b. All existing independent findings have replies.
- [x] 2026-10-07 10:19 UTC: Inspected rendering, scope merging, pending responses,
      host construction and pydantic-ai new-message behavior. Implemented optional
      bounded memory rendering and request-local projection of old initial prompts.
- [x] 2026-10-07 10:25 UTC: Added 15 real-engine / SQLite cases. Engine plus host
      contracts: 317 passed; complete learning/profile: 2406 passed, one skipped,
      four subtests. Disabling projection causes 11 failures. Developer tooling and
      all-files gates passed.
- [x] 2026-10-07 10:21 UTC: Published PR #3029 at 4bbff7658; integrated the exact
      tested tree into sim ac260ffee.
- [x] 2026-10-07 10:28 UTC: Reproduced both Devin compatibility findings (three
      regression failures before fixes). Share structured parsing with nickname
      refresh and preserve omission notices using selection metadata. Focused
      regressions: 28 passed; complete engine: 292 passed. Complete learning/profile:
      2409 passed, one skipped, four subtests. All-files gates passed.
- [x] 2026-10-07 10:30 UTC: Pushed d8a80fb86 and replied to both Devin findings
      with verification results; integrated exact tree into sim ebca41d74. Both API
      replicas matched all five changed runtime files. All 29 isolated engine probes
      and normal read/backfill/listen completion passed; profile unchanged.
- [x] 2026-10-07 10:33 UTC: Added independent-document fence regression after
      observing that an unclosed script fence suppressed brief reference priority.
      The regression fails before the fix. Final engine: 293 passed; learning/profile:
      2410 passed, one skipped, four subtests. Final all-files gates passed.
- [ ] Push the final reference-boundary fix after complete validation,
      and validate final sim / CI.
      Main merge remains user-owned.

## Surprises & Discoveries

The engine injects `<memory>` only in its initial user prompt. Merely limiting new
sessions leaves legacy sessions' oversized blocks in every resumed request.
The saved initial prompt is also conversation evidence; replacing it in durable
history would silently rewrite the snapshot. pydantic-ai exposes `new_messages()`
separately from history, allowing the host to save original history plus new results.
Exact substitution and long tool-return answers can still make a request large.
An omission notice changes the initial layout understood by the nickname refresher;
a shared JSON-aware parser must serve both consumers. A literal `<memory_context>`
in a retained value cannot indicate whether the renderer emitted a notice.

## Decision Log

- Use 32768 JSON characters, consistent with existing memory budgets, with escaping
  and indentation counted. This is neither provider-token accounting nor a total
  context-window guarantee.
- Consider script/brief references and host-reserved account keys first, preserve
  dictionary order within priority groups, and omit whole oversized values.
- Keep all persistence and exact substitutions unchanged. Omission is model-visible
  through a static unknown-value notice, never a deletion or fabricated summary.
- Project only the known initial engine prompt. Decode JSON rather than finding a
  closing tag inside arbitrary content. Do not rewrite later messages or tools.
- Enable at the sole AI-Shifu Engine factory, retaining portable defaults. No
  changes to profile writes, database schema, frontend protocol or production list.

## Outcomes & Retrospective

Implementation and acceptance are in progress. The canonical contract is
[lesson memory context](../../product-specs/lesson-memory-context.md). All-message
history compression, repeated substitution limits, independent human course
acceptance, viewing/deletion and cross-course sharing remain separate follow-ups.

## Context and Orientation

`engine/script.py` composes the initial prompt. `engine/memory_context.py` projects
legacy initial sections in temporary request history. `engine.py` applies the
optional host limit and preserves original history on save. `lesson_entry.py`
is the sole production factory. The memory facade owns existing course reads.

## Plan of Work

Add bounded whole-value JSON projection and stable reference/account priority.
Apply the same projection to known legacy initial prompts without changing stored
history. Prove exact answers, substitution, deferred resumes, retries, JSON escaping,
scope merging, literal tags and portable behavior through FunctionModel and SQLite.

## Concrete Steps

Use conda ai-shifu from src/api for focused tests, the required complete engine
suite and complete learning service regression. Run developer tooling and all-files
pre-commit gates at repository root. Push only GitHub origin, open a focused PR,
integrate its tested tree into sim and verify deployed bytes and normal teaching.

## Validation and Acceptance

Actual model requests carry memory payloads within the configured JSON limit across
both scopes and legacy resumes. Referenced/host-priority keys outrank incidental
notes when they fit. Complete answers remain in storage, exact substitutions and
tool results. Failed calls retain deferred evidence; successful calls append new
history without rewriting prior messages. Other hosts keep unrestricted defaults.

## Idempotence and Recovery

No data or schema migration. Existing oversized memory remains stored. Reverting
projection restores previous model inputs without recovering deleted data. Temporary
model-history copies cannot affect the database or original session on failure.

## Interfaces and Dependencies

Add an optional Engine memory_context_limit and rendering keyword arguments.
Use existing pydantic-ai ModelRequest parts, dataclass copies and new_messages().
No dependency upgrades, provider bypass or new transaction boundary are needed.

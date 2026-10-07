# Admit Declared Variables and Explicit Learner Requests

## Purpose / Big Picture

Enforce the user's 2026-10-07 decision: an AI-Shifu lesson may record variables
declared with `%{{key}}` in its script, or content the learner explicitly asks
it to remember. A casual preference or an invented model fact is insufficient.
Explicit requests must also survive the next course lesson without requiring
an author-created profile definition.

## Progress

- [x] 2026-10-07 09:20 UTC: Inspected tools, deferred answers, checkpoints,
      gateway billing and profile storage. Recorded the user's selected policy.
- [x] 2026-10-07 09:33 UTC: Implemented admission, grounded request validation,
      scoped reads and account-key protections.
- [x] 2026-10-07 09:36 UTC: Verified real engine, SQLite, rollback, pending
      evidence, checkpoints and gateway context. Learning/profile suites: 2387
      passed, one skipped, four subtests. Disabling admission causes 31 failures.
- [ ] Pass repository gates and publish one focused PR.
- [ ] Integrate and validate sim, handle every independent AI finding, and
      verify final CI. Main merge remains user-owned.

## Surprises & Discoveries

The runtime reader currently loads profile definitions and canonical fields,
so a persisted undeclared variable disappears on the next host request.
Deferred questions may collect several answers before the model resumes;
request evidence must survive that serialization and a failed model call.
Model-authored choice values are not evidence of a learner's free-text request.
Legacy profile keys such as `language`, `sex`, `birth` and `avatar` route globally
without a `sys_` prefix; the host supplies the writer's complete reserved-key set.
Admission awaits another model call, so writes must recheck capacity and finished
state afterward.

## Decision Log

- Enable the admission policy at the single AI-Shifu engine construction site;
  retain the portable engine's existing default for other hosts.
- Declare keys only from the main script, outside fenced examples. A reference
  document or teaching brief cannot grant additional write permissions.
- An undeclared note requires an exact current accepted free-text input and an
  independent semantic check through the existing billed/traced gateway. Refuse
  on failure. Limit and cache these checks; declared writes need no extra call.
- Explicit requests use user scope within the current course. They cannot change
  system profile keys unless the author declared that key. No cross-course
  sharing or new database schema is introduced.
- Keep variables in the existing typed memory category and profile writer.
  Opt the agent reader into current-course variable rows, with canonical runtime
  resolution taking precedence. Other memory consumers retain their contract.
- Preserve existing rows without inferring their origin, consistent with the
  existing memory facade. Do not fabricate provenance or silently purge history.

## Outcomes & Retrospective

Implementation and acceptance are in progress. The canonical contract is
[learner memory admission](../../product-specs/learner-memory-admission.md). Independent human teaching
acceptance, viewing/deletion, cross-course policy and full injection projection
remain in the workspace MDF 2.0 plan.

## Context and Orientation

`engine/tools.py` owns model writes and deferred questions. `engine.py` owns
accepted inputs; `session.py` and `agent/rewind.py` preserve pending state.
`lesson_entry.py` is the sole production engine factory and binds GatewayModel.
`learn/memory` owns typed variable reads/writes; `run_agent.py` loads and stages
memory with the session's transaction.

## Plan of Work

Add optional host admission capabilities, validate declared keys and real
free-text evidence, and wire a fail-closed independent request judge. Preserve
pending evidence through serialization, retry and rewind. Extend only the agent's
course-variable read projection. Prove positive and negative cases with actual
engine calls and SQLite, including next-lesson input and rollback.

## Concrete Steps

Use conda `ai-shifu`. Run focused admission/entry/memory/rewind tests from
`src/api`, then the learning service suite. Run developer tooling, architecture
checks and the all-files pre-commit gate from the repository root. Publish to
GitHub origin, integrate the tested tree into sim, and inspect deployed bytes
and normal learning regression results without logging credentials.

## Validation and Acceptance

Declared notes and exact named answers persist. Undeclared guesses, casual
preferences, fabricated quotes, choice-value tricks, system-key changes and
unavailable judge calls do not write memory. Explicit requests survive the next
lesson only for the correct learner/course. Multi-question resumes, failed saves
and rewind cannot reuse unrelated consent. Gateway calls retain billing/trace
context; reviewer findings receive original-thread replies.

## Idempotence and Recovery

No migration or destructive data rewrite. A refused call leaves both memory
scopes and persistence events unchanged. Existing transaction rollback remains
authoritative. Revert the focused runtime change to restore the earlier policy.

## Interfaces and Dependencies

Add optional Engine admission callbacks and pending input evidence with backward
compatible deserialization. Reuse pydantic-ai and GatewayModel; no dependency
upgrade, provider bypass, protocol replacement or frontend flow is needed.

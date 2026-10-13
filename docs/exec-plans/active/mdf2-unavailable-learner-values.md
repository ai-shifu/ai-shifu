# Unavailable Learner Values

## Purpose / Big Picture

Prevent skipped earlier lessons from presenting unresolved personal templates as
learner facts in teaching prose and generated visuals.

## Progress

- [x] 2026-10-13: Read-only production trace confirms missing values in the actual
      initial context and literal unresolved templates in displayed output.
- [x] 2026-10-13: Three absent/null/empty prompt cases first fail. Implement explicit
      unavailability and preserve known, collected and fenced-code semantics.
- [x] 2026-10-13: Nine prompt/SDK cases and six historical/current section-refresh
      compatibility cases pass; SDK doubles are not actual-model acceptance.
- [ ] 2026-10-13: Complete broader tests, repository gates, Ready PR, reviews,
      sim integration and actual-model missing/known-value verification.

## Surprises & Discoveries

Existing prose already says to omit an unresolved read. The reported model still
copies it into prose/HTML. Replacing global output text would also corrupt literal
syntax lessons and generated code. A legacy script may match the new form while
its separate brief does not, so section compatibility must be checked independently.

## Decision Log

- 2026-10-13: Represent missing reads as request metadata; preserve the source
  bundle and original displayed evidence. Do not fabricate values or change
  shared course configuration, collection syntax, scopes or budgets.

## Outcomes & Retrospective

Implementation is under verification. The reported saved output remains failure
evidence. This focused fix does not close broader classroom acceptance.

## Context and Orientation

`engine/script.py` renders the initial script/brief. `prompts/v1_syntax.md` defines
its semantics; `nickname.py` and `deleted_memory.py` refresh known host sections.
The canonical contract is [memory recall](../../references/markdownflow-memory-recall.md).

## Plan of Work

Render absent/null/empty reads as unavailable metadata outside fenced code. Keep
fresh collected values deferred and exact known substitutions. Match legacy/current
host sections independently, preserving later history. Validate model delivery
and actual prose/visual behavior before recommending merge.

## Concrete Steps

Run focused tests, then `cd src/api && python -m pytest tests/service/learn/
tests/scripts/ -q`. Run toolchain and all-file repository gates before committing.
Create a Ready PR; deploy only sim and verify both replicas before model checks.

## Validation and Acceptance

Missing facts must use authored unavailable wording or omission, with no invented
personal facts, raw template or metadata displayed. Known values remain exact;
code examples, fresh answers, current nickname/deletion refresh and saved evidence
retain their contracts. Actual-model checks complement controlled SDK tests.

## Idempotence and Recovery

Old/new known host sections are matched exactly; unfamiliar history fails closed.
Repeated deletion is idempotent. Preserve original failures and never reset an
existing learner or rewrite displayed output to manufacture acceptance.

## Interfaces and Dependencies

An optional internal substitution flag enables unavailable metadata for host
prompts. Default low-level substitution retains its prior contract. No new API,
frontend protocol, package, database schema or shared configuration is required.

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
- [x] 2026-10-13: Review finds missing syntax inside authored verbatim spans
      must remain literal. Three cases first fail; preserve missing notation in
      inline/block verbatim examples without changing known personalization.
      Final 3645 learning/script checks plus 50 subtests pass (three skips),
      including 14 prompt/SDK and six legacy/current compatibility cases.
- [x] 2026-10-13: Ready PR #3124, broader tests and all repository gates pass.
      Adopt both original-thread verbatim findings in f826f7ef3; document all
      21 touched functions in 7dbe0f477 (local AST inspection, not whole-backend
      coverage). The documentation follow-up passes 51 focused tests.
- [x] 2026-10-13: Sim 00dd77e67 / build 618 / Drone 5407 serves two Ready API
      replicas, each matching 68 files and passing 436 deployed SDK checks.
      Integrated learning/script checks pass 3850 plus 50 subtests (three skips).
- [x] 2026-10-13: Actual original-model diagnostics use two unchanged reported
      lesson bundles, each with one missing and one synthetic-known input.
      Missing timeline facts and the primary tool display as unconfirmed; known
      goal/result/tool values appear in prose/visuals without raw placeholders or
      metadata. Four generations settle 6.33 credits to the isolated test attempt
      and block. Persisted sessions/progress/variables and authored sources remain
      unchanged. These are in-memory diagnostics, not ordinary-HTTP full lessons.
- [ ] 2026-10-13: Verify final receipt-head CI and current review status before
      recommending merge; no automatic merge.

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

The missing/known paths pass actual-model prose and visual checks for both
reported lessons. Read-only trace/token/ledger matching accounts for all four
requests; a result-transport failure was recovered from existing remote files
without repeating a model call. The reported saved output remains failure
evidence. This focused fix does not close broader classroom acceptance.

## Context and Orientation

`engine/script.py` renders the initial script/brief. `prompts/syntax.md` defines
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

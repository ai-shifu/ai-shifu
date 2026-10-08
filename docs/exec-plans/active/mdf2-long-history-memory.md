# Long teaching history and current memory acceptance

## Purpose / Big Picture

Extend the repeatable memory-quality operator with real-model journeys that
combine older long teaching, semantic overviews, exact original reads and a
session round trip. A current learner fact must come from current authorized
memory; an exact historical example must come from original teaching rather
than a lossy overview. Continue milestone 4 after merged PR #3052.

## Progress

- [x] 2026-10-08 21:54 CST: Verified #3052 merged as `89579244b`; main
  build 421 / Drone 5212 succeeded. All eight CN/US deployments 2026-2033 succeeded; eight API replicas each
  match seventeen runtime hashes and retain production 1.0 routing.
- [x] 2026-10-08 21:51 CST: Inspected current recall, excerpt, summary, cache
  and operator paths. Existing cases do not combine these real-model surfaces.
- [x] 2026-10-08 22:07 CST: Added four fixed long-history cases and negative
  scorer regressions. Canonical fixture/operator tests: 58 passed; complete
  learning/profile/operator checks: 2,866 passed, one expected skip and four
  subtests passed. Final excerpt/tool changes: 541 engine/operator tests passed.
- [x] 2026-10-08 22:07 CST: Retained the canonical deployed baseline: 6/12,
  zero request errors. Historical questions incorrectly used current memory.
- [x] 2026-10-08 22:13 CST: The fifth candidate passed 12/12, zero request
  errors, after clarifying excerpt omissions and original-read tool scope.
- [x] 2026-10-08 22:15 CST: Final policy candidate passed 12/12, zero
  request errors; final complete local regression passed 2,866 tests, one
  expected skip and four subtests. Repository-wide gates passed.
- [ ] Run local gates, open one focused PR and verify deployed sim acceptance.
- [ ] Reply to every independent AI opinion in its original discussion.
- [ ] Await manual main merge and verify release selection.

## Surprises & Discoveries

The existing twenty cases cover admission and current recall, including owned
answer reloads. They do not establish whether a model distinguishes current
memory from a lossy older teaching overview or uses original evidence for an
exact historical question after cache reload.

The initial fixture had an outdated first host prompt after replacing its script.
It was corrected to match the stored script before the canonical baseline. The
initial report remains retained but is not combined with canonical evidence.
A first candidate passed 9/12 but failed all excerpt-only historical reads; a
second passed 9/12 with historical reads fixed but intermittent current-fact
failures. All reports remain retained. A third candidate again passed 9/12: current facts
were correct, but excerpt-only historical reads still failed. A diagnostic
confirmed it chose current recall rather than the available original-read tool.
The fourth candidate clarified the original-read tool description but remained
9/12. The fifth also clarifies that excerpt edges may omit the requested topic
entirely and point to a complete historical original, not today's memory. It
passed all twelve selected runs. A final consistency correction scopes the old
recall-compaction instruction to current memory; it must not demand current
recall for a question about an original historical example.
A longer notice exceeded the existing 1,700-character regression bound; the final
notice was shortened while preserving the 1,024-character key-name budget.

## Decision Log

- Reuse the existing selected-course gateway, reporting, fixed catalog and
  opt-in evaluator. Synthetic sessions do not claim database authorization or
  persisted host acceptance; those remain covered by real storage regressions.
- Generate real semantic summaries for positive cases; explicitly label the
  injected summary-failure case and verify deterministic fallback separately.
- Require paired current-turn tool evidence before the answer, unchanged memory
  and original history, a genuine cache round trip, and finished teaching.
- Preserve system-global/course-local scope and production 1.0 routing.

## Outcomes & Retrospective

Acceptance is pending. Passing small synthetic fact/tool cases will not complete
natural teaching-quality acceptance, long-term cost observation or human trials.

## Context and Orientation

The operator is `src/api/scripts/evaluate_mdf2_memory.py`; its catalog is under
`scripts/mdf2_memory_quality/`. Engine teaching projection and derivative cache
are documented in `docs/references/markdownflow-teaching-history.md`. Keep its
original-evidence and current-memory contracts separate.

## Plan of Work

Add long-history current-update/deletion and historical exact-read cases with
successful cached summaries and an injected failure fallback. Run against the
existing deployed engine before making any runtime-policy correction. Preserve
failures and compare actual deployed runtime fingerprints afterward.

## Concrete Steps

1. Add fixed fixtures and scorer refusal tests under the existing operator.
2. Run local operator/engine coverage, then selected real-model baseline.
3. Fix only demonstrated current-memory or exact-history errors and rerun.
4. Stage Markdown before regenerating knowledge indexes; run development-tool
   and all-files gates before ordinary commits; push only to GitHub origin.
5. Open the PR, synchronize sim, verify replicas and real model/HTTP behavior.

## Validation and Acceptance

Three repetitions of every added case must retain all failures and distinguish
provider/summary errors from semantic failures. A missing tool, guessed historical
answer, stale current value, memory write or changed original history must fail.
Summary cache reuse must not create another logical summary request on reload.
The injected failure must keep the exact excerpt/read path available.

## Idempotence and Recovery

Use synthetic sessions and dedicated internal sim learners only. Preserve reports
privately; do not load real learner memory or modify production settings. Local
fixture/model tests run without network. Rewind and failure behavior retain their
existing tests and are not weakened for an evaluator pass.

## Interfaces and Dependencies

Reuse Engine, Session serialization, TeachingSummarizer, the production summary
factory and GatewayModel. No SQL migration, dependency, environment or UI change
is planned. Any runtime change requires its corresponding engine regressions.

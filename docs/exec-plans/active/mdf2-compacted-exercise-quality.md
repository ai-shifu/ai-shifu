# Validate exercise reports after teaching compaction

## Purpose / Big Picture

The exercise evaluator currently keeps every teaching message below the compaction threshold. Its passing statistics cannot establish correct results after a long correction is summarized. Extend the existing synthetic evaluator to require actual source-bound projection, serialized cache reuse, original evidence reads and correct per-question statistics.

## Progress

- [x] 2026-10-09T15:48:00Z: Confirmed #3074 merged, all final CI passed, no actionable AI comments, and sim-d0ba676 is ready on both API replicas and web.
- [x] 2026-10-09T15:48:00Z: Add successful-summary and injected-failure statistics cases with immutable long feedback evidence.
- [x] 2026-10-09T15:48:00Z: Prove missing projection/cache reuse cannot pass, run selected live cases with scoped billing, and retain failures.
- [x] 2026-10-09T15:57:13Z: Developer-tool checks, full gates and commit hooks passed; published [PR #3075](https://github.com/ai-shifu/ai-shifu/pull/3075) with functional commit b94979ac1.
- [ ] 2026-10-09T15:58:40Z: Independent AI/CI review remains pending; CodeRabbit is currently rate-limited, not substantive approval. Reply to any actionable opinions in their original threads before declaring review handling complete.

- [x] 2026-10-09T15:59:45Z: Accepted Devin documentation finding: distinguish completed selected synthetic compaction coverage from remaining natural-course/other-model acceptance in the canonical history paragraph.

## Surprises & Discoveries

The projection flag is enabled in existing exercise cases, but none of their text is eligible and no semantic summarizer is configured. Actual compaction must be observed in model requests rather than inferred from options.

## Decision Log

- Keep the two full-history baselines unchanged and add two selected synthetic cases.
- Place the original incorrect feedback and hint in the middle of one eligible older teaching part, outside excerpt edges. Use the production summary factory; explicitly injected failure tests the cached excerpt path.
- Reuse the existing evaluator, gateway context, original exercise reader and calculator. Do not change runtime prompts, storage, grading semantics, user memory or 1.0.
- Require positive projection evidence and no repeated summary after session reload. Incorrect/missing summaries and plausible totals alone cannot pass.

## Outcomes & Retrospective

Offline evaluator and engine regressions pass (647 total); 107 evaluator tests pass after restoring a mutation that disables projection/cache assertions. That mutation makes all four missing-projection/cache regressions fail. Selected sim live evaluation passes 2/2 on ark/deepseek-v4-1-flash-260910, with actual original reads, calculated results, one summary attempt/cache reuse and required projection markers. All 28 report fingerprints match the local candidate. Thirteen gateway rows are fully attributed to the dedicated learner, course, lesson and owner, with no fabricated classroom IDs, failures or unsettled billable successes; settled cost is 12.17 credits. One completed summary request is accounted separately; the failure case intentionally makes no summary-provider request. This single selected repetition is not a full-catalog result. Developer-tool verification, repository gates and commit hooks passed; PR #3075 is open with functional commit b94979ac1. Independent AI/CI review remains pending, with CodeRabbit currently rate-limited. Keep this plan active for that follow-up; no application deployment is required for the evaluator-only delta. This scope closes repeatable statistics-after-compaction coverage only; natural courses, other models/languages, external providers, human teaching quality and long-term fees remain separate acceptance items.

## Context and Orientation

The opt-in CLI is `src/api/scripts/evaluate_mdf2_memory.py`. The fixed catalog and exercise runner live in `scripts/mdf2_memory_quality/`; tests are under `tests/scripts/`. The canonical contract is `docs/references/markdownflow-memory-quality.md`. The engine stores original history separately from request projection and exposes raw exercise records through `read_exercise_history`.

## Plan of Work

Build one long correction per fixture, warm one bounded summary/failure cache, reload the session and observe the actual engine request projection. Retain strict row/source/aggregate checks and add summary/cache evidence. Reuse the teaching observer to keep both evaluator families consistent.

## Concrete Steps

Run focused evaluator tests with conda ai-shifu. Mutate projection or cache handling to prove regressions fail, then restore. Run selected live cases in an isolated sim temporary scripts directory using the existing dedicated learner and published course, with normal gateway accounting and no session/profile persistence. Verify source fingerprints and read-only billing scope. Run repository gates and publish a main PR manually.

## Validation and Acceptance

Both eligible cases require exact original reads before calculation/reporting, one summary attempt, the expected summary or excerpt marker, unchanged original history/memory and actual finish. Correct-looking reports without projection or proper cache reuse fail. Live reports retain errors and separate summary usage, with no raw prompts, answers, IDs or credentials. A selected synthetic run never counts as full-catalog or natural-course acceptance.

## Idempotence and Recovery

Synthetic sessions remain in memory. Temporary scripts do not overwrite application files. Gateway billing still applies and must be reconciled separately. Preserve private reports before cleaning temporary files. No deployment, schema migration or data reset is required for this evaluator-only change.

## Interfaces and Dependencies

Use existing Session serialization, Engine, production teaching summarizer, model wrapper observation and the scoped opt-in quality CLI. No new external dependencies, endpoints, analytics events or memory scope.

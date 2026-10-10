# Keep current memory distinct from old follow-up answers

## Purpose / Big Picture

A learner's current saved preference must reflect updates from another lesson
and menu deletion. Old conversation remains available for explicit historical
questions but must not establish that a preference is still saved.

## Progress

- [x] 2026-10-10T01:52:11Z: Confirmed #3082 merged as efa38c70c; final technical
  CI succeeded, with no actionable review comments. CodeRabbit was quota-limited.
- [x] 2026-10-10T01:52:11Z: Reproduced stale current answers after a cross-lesson
  update and deletion through ordinary sim HTTP calls on a dedicated learner
  with nine completed lessons. Storage, menu deletion and canonical profile
  checks succeeded; fresh-lesson recall correctly reported unknown.
- [x] 2026-10-10T01:52:11Z: Four new offline integration cases failed without
  recall, then passed with the existing bounded engine tool. Same-run writes
  must not be shadowed by a duplicate local snapshot.
- [ ] 2026-10-10T01:52:11Z: Complete historical/discovery regressions, learning
  suite and repository gates; publish the focused PR without merging it.
- [ ] 2026-10-10T01:52:11Z: Release to sim through its normal branch pipeline,
  verify both runtime replicas, repeat the natural journey and reconcile usage.
- [ ] 2026-10-10T01:52:11Z: Inspect CI and reply to every actionable AI opinion
  in its original thread; record acceptance limits.

## Surprises & Discoveries

The existing follow-up path supplies current memory in its initial system
context but exposes only remember. An old-anchor answer still asserted the old
library analogy after another lesson saved a bus analogy, and again after menu
deletion. A new lesson reported unknown. Persistence was correct. Follow-up
Deps also copied the same snapshot into both user and local memory; a newly
admitted user value would be hidden by the stale local copy during recall.

## Decision Log

- Reuse the existing exact, bounded recall tool; no new storage, endpoint,
  semantic classifier or provider fallback. The current authorized snapshot is
  request-local, and the shared gateway retains usage/attempt attribution.
- Keep the snapshot in user memory only, matching follow-up writes. Preserve
  immutable request evidence and original historical messages.
- Require current reads for current facts and preserve historical quotations.
  This remains model guidance, not deterministic output enforcement.
- Keep existing request/tool budgets, semantic admission, deletion epochs,
  preview no-write behavior and system/course scope rules. Retain engine 1.0.

## Outcomes & Retrospective

Pending candidate live acceptance. Keep the initial failures as evidence; do not
overwrite them with subsequent passing reports or declare human acceptance.

## Context and Orientation

`follow_up_memory_writer.py` owns the native Agent used by default contextual
LLM answers, configured fallbacks and GetBiji synthesis. `follow_up_context.py`
supplies history and the bounded memory prompt. The reusable engine recall
tool returns complete values, unavailable or too_large, and paginates key names.
External provider-only answers and Live do not acquire these tools.
The previous [full catalog acceptance](../completed/mdf2-memory-catalog-acceptance.md) covers
synthetic engine sessions; this natural follow-up defect was outside that run.

## Plan of Work

Prove the missing read path with FunctionModel tool calls, expose existing recall
and guide current versus historical use, validate unchanged write permissions
and failure/cancellation handling, then test the deployed path with the same
dedicated internal learner. Keep before/after histories and ledger evidence
private. Publish only aggregate results and revisions.

## Concrete Steps

Run the focused follow-up tests and `pytest tests/service/learn/ -q` in the
ai-shifu conda environment. Regenerate knowledge indexes, check developer tools
and run `lefthook run pre-commit --all-files`. Commit with repository-default
identity, push only origin, and open a non-draft PR to main. Apply the runtime
delta to sim without dropping its existing changes. Wait for normal build and
rollout, check runtime hashes on both replicas, then repeat save, cross-lesson
recall, update, old-anchor recall, menu deletion and historical quotation.

## Validation and Acceptance

Offline checks cover updated, missing and oversized values, same-run writes,
discovery and unchanged historical evidence. Current factual reads must not
write memory or invoke semantic admission. Ordinary questions retain one model
request. The natural journey must answer the new preference after update and
unknown after deletion while preserving the earlier quotation, original lesson
records, completed progress and canonical profile. All actual gateway usage
must carry matching real attempts/blocks and settle correctly. This closes only
the tested model and learner journey, not other-provider, human or long-term
memory/fees acceptance.

## Idempotence and Recovery

Use only the existing dedicated internal learner and its own test preference;
sim shares the production database. No production learner or configuration
changes. Preserve baseline failures and use a separate candidate evidence
directory. Do not blindly retry billed requests or delete unrelated notes.
Retain the source branch and private evidence on interruption.

## Interfaces and Dependencies

No new dependency, migration, wire contract or analytics event. The shared
bounded recall tool reads Deps.user_memory; remember updates the same namespace.
Request snapshots are immutable outside the native run, and only successfully
consumed streams publish the existing host-staged write patch.

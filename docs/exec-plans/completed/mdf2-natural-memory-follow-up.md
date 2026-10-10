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
- [x] 2026-10-10T02:03:00Z: Historical/discovery regressions and 3,061 learning/
  profile tests plus four subtests pass, with one expected skip. Developer tools,
  repository gates and commit hooks pass. Published #3083 as db46e0837.
- [x] 2026-10-10T02:03:00Z: Released only the runtime/test delta to sim as
  d50b3d25c; both ready API replicas match all 37 relevant runtime fingerprints.
- [x] 2026-10-10T02:17:28Z: Final b8f14677d passes 3,063 learning/profile tests
  and four subtests, with one expected skip; repository gates/hooks pass. Both
  sim-ea3da3b API replicas match all 37 runtime fingerprints.
- [x] 2026-10-10T02:17:28Z: Final natural HTTP journey answers current values
  correctly in all seven recall questions: updated old-anchor preference 3/3,
  deleted old-anchor 2/2, fresh deleted context 1/1 and initial cross-lesson 1/1.
  Historical analogy is retained; all 142 original elements across nine lessons,
  canonical profile and unrelated memory survive. Test preference is deleted.
- [x] 2026-10-10T02:17:28Z: Reconciled final 24 successful, settled requests,
  13.47 credits. All have matching real progress IDs but lack block IDs; keep
  this incomplete attribution acceptance open.
- [x] 2026-10-10T02:17:28Z: Replied to Devin's budget finding and CodeRabbit's
  docstring advice in their original discussions, with pushed SHAs and tests.
  Technical checks except the running runtime-harness have passed at this time.
- [x] 2026-10-10T03:22:03Z: Confirmed #3083 manually merged as caa1211e1;
  final technical CI passed. Archived this narrow current-value fix. Transfer
  missing block attribution to the [follow-up usage plan](mdf2-follow-up-block-attribution.md)
  and causal explanation failures to the [memory quality backlog](../../references/markdownflow-memory-quality.md#remaining-natural-answer-quality).
  These acceptance gaps remain open independently of this merged fix.

## Surprises & Discoveries

The existing follow-up path supplies current memory in its initial system
context but exposes only remember. An old-anchor answer still asserted the old
library analogy after another lesson saved a bus analogy, and again after menu
deletion. A new lesson reported unknown. Persistence was correct. Follow-up
Deps also copied the same snapshot into both user and local memory; a newly
admitted user value would be hidden by the stale local copy during recall.

Read-only reconciliation of the initial natural HTTP window found eleven
successful, settled requests totaling 7.76 credits, with correct owner/course.
All eleven have matching real progress IDs but lack generated-block IDs. The original eleven progress records and
nine completed sessions are unchanged. This is a separate existing follow-up
attribution defect, not evidence of complete accounting acceptance.

The first deployed candidate exposed recall but still skipped it for one
old-anchor current-preference question. It correctly handled deletion and the
historical quotation. A separate cross-lesson answer read the right current
value but invented that a previous save had failed. Preserve this mixed result;
add a current-question host reminder that also forbids inventing a cause for
changed/missing memory. The notice is only a model-facing projection, outside
raw learner evidence and stored history.

## Decision Log

- Reuse the existing exact, bounded recall tool; no new storage, endpoint,
  semantic classifier or provider fallback. The current authorized snapshot is
  request-local, and the shared gateway retains usage/attempt attribution.
- Keep the snapshot in user memory only, matching follow-up writes. Preserve
  immutable request evidence and original historical messages.
- Require current reads for current facts and preserve historical quotations.
  This remains model guidance, not deterministic output enforcement.
- Keep existing request/tool budgets, semantic admission, deletion epochs,
  preview no-write behavior and system/course scope rules initially. Retain
  engine 1.0. Review later demonstrated that recall needs a larger finite budget:
  count pages through the actual byte-bounded recall implementation, reserve
  three write attempts, up to three added pages and one exact read, plus a final
  model request. Enforce the original three-attempt write cap independently.
- Transfer the demonstrated follow-up accounting defect to the next focused
  usage-attribution task; do not fabricate IDs or expand this memory fix.
- Add meaningful protocol docstrings to the four new FunctionModel stream
  helpers. Behavior-named pytest functions remain exempt under the engineering
  baseline's D102/D103 rules, regardless of a reviewer coverage warning.
- Place the bounded host reminder beside the final current user prompt, as the
  teaching engine already does for revalidation. No memory values or permission
  evidence are copied into it; original messages stay untouched.
- Accept Devin's deep-discovery finding: two new cases with 45 short/long keys
  fail before the budget fix. Counting actual pages handles the UTF-8 byte cap
  as well as the 20-name cap. Ordinary answers still use one model request.

## Outcomes & Retrospective

The final natural journey correctly reports current saved values in seven of
seven recall questions, including three consecutive old-anchor reads after an
update and two after deletion. The historical analogy remains available without
claiming it is currently saved. Both sim replicas match the runtime; 142 original
elements across nine lessons, canonical profile and unrelated memory remain
unchanged. Final usage is 24 successful, settled requests costing 13.47 credits.
Initial baseline and first-candidate failures remain preserved separately.

This is narrow current-value acceptance only. Three final answers still invented
why a historical save differed or said the preference had never been saved;
the host reminder did not eliminate these causal/chronological errors. They
remain failed natural answer-quality evidence. All 49 requests across the three
windows settled (28.71 credits) and have matching real progress IDs, but
all lack generated-block attribution. Neither
issue is closed by the correct current values, and neither synthetic tests nor
this internal learner journey establish human or full memory acceptance.

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
records, completed progress and canonical profile. Reconcile all actual gateway
usage and retain incomplete attribution as a failed, separate acceptance item.
Settlement alone does not prove attempt/block ownership. This closes only
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

---
title: Close Local Interaction Review Gaps
status: completed
owner_surface: backend
last_reviewed: 2026-11-18
canonical: false
---

# Close Local Interaction Review Gaps

## Purpose / Big Picture

Use PR #3419's review to keep local interaction reports trustworthy after
interrupted runs and make missing teaching behavior visible in the fixture
checks. Reviewers should be able to return to saved evidence and annotations.

## Progress

- [x] 2026-11-18 13:10 UTC: Verified the current branch and classified the review findings.
- [x] 2026-11-18 13:35 UTC: Corrected evaluator and review-page edge cases.
- [x] 2026-11-18 13:45 UTC: Tightened rubric and replay coverage and verified captured teaching output.
- [x] 2026-11-18 13:51 UTC: Passed 70 targeted tests, all 28 configured replays, and the repository-wide pre-commit gate.

## Surprises & Discoveries

The engine can commit an answer before the resumed model call fails. A failed
request can also contribute text to the report before its exception arrives.
The initial live balcony probe exposed different interpretations of an
optional reminder to click. The review now treats the button as an independent
criterion and allows the prose to focus on preparing at the chosen location.

## Decision Log

- 2026-11-18. Preserve the observed memory snapshot separately from uncompleted
  model-dependent checks. Keep the call error in the report.
- 2026-11-18. Use existing prose criteria for teaching requirements. Keep the
  start-recording button title unrestricted and check branch and memory
  behavior independently.
- 2026-11-18. Give the question judge earlier learner-facing prose only when
  consecutive steps have identical visible titles and controls. Incorporate
  that text only to resolve an explicit reference to the same question.

## Outcomes & Retrospective

Both judges agreed with the expected judgments on 38 targeted samples, which
included earlier human-reviewed prose, changed timing, missing feedback and
equivalent answer disclosures. GPT-6.2 Sol and DeepSeek Flash reached the
correct balcony question after reload and passed with the revised rubric.
Gemini 4 Hydrogen passed after an automatic teaching continuation.
Local review-page checks covered restoring annotations after a damaged draft,
selecting a pending step after importing decisions, and rendering all three
saved runs side by side.
The full replay includes 19 first-attempt passes, seven recovered passes, and
two reproduced historical failures. All 70 focused tests passed.

## Context and Orientation

The [evaluator guide](../../../src/api/scripts/README.md#evaluate_mdf_interactionspy)
owns report generation and review instructions. The
[catalog guide](../../../src/api/scripts/mdf_interactions/README.md) explains
live and replay assertions. The review page reads saved reports and browser
annotations without a model call.

## Plan of Work

Resolve valid PR findings in small independent changes. Preserve existing
report identities and criterion status meanings. Add regression checks for the
interrupted call, fixture paths, and malformed review inputs.

## Concrete Steps

1. Preserve partial evidence and protect input files during report generation.
2. Validate browser data and improve saved report and annotation recovery.
3. Cover branch selection after reload, required correction and wait behavior,
   and the representative historical anomalies.
4. Verify local replay, browser behavior, and the resulting PR head.

## Validation and Acceptance

Run the evaluator and helper pytest modules and the full pre-commit gate.
Exercise review navigation and restored drafts, including invalid saved data
and imported verdicts. Recheck revised semantic requirements against captured
responses and targeted positive and negative examples.

```bash
cd src/api
python -m pytest tests/scripts/test_evaluate_mdf_interactions.py \
  tests/scripts/test_mdf_interaction_live.py \
  tests/scripts/test_mdf_interaction_continuation.py -q
python scripts/evaluate_mdf_interactions.py --json /tmp/interaction-replay.json
```

## Idempotence and Recovery

Run offline replay and regenerate review pages from copies of saved reports.
Keep published report IDs and saved annotation keys stable. Reject output
paths that alias an input before writing.

## Interfaces and Dependencies

The evaluation tools use schema version 5 reports and the existing
MarkdownFlow engine, Pydantic AI model stream, and local review assets.

---
title: Keep Authored Input Hints Out of Choice Buttons
status: in-progress
owner_surface: learner
last_reviewed: 2026-10-07
---

# Keep Authored Input Hints Out of Choice Buttons

## Purpose / Big Picture

An editor preview showed the author's free-text hint as a fourth answer button.
Keep the intended choices and input while preserving adaptive teaching.
The durable contract is [Authored Input Hints](../../references/markdownflow-authored-inputs.md).

## Progress

- [x] 2026-10-07 15:00 UTC: Reproduced the exact malformed tool call from sim's
  expiring debug session; a second run had the correct three choices.
- [x] 2026-10-07 15:05 UTC: Added a narrowly matched correction for new and saved
  pending interactions, with offline engine and protocol regressions.
- [x] 2026-10-07 15:07 UTC: Engine/protocol 390 passed; learning/profile 2,508
  passed (1 skip, 4 subtests). All repository gates passed. The installed renderer
  showed three choices and submitted the typed answer. Disabling the correction
  failed 11 of 25 focused regressions; the restored code also passed 36 offline probes.
- [x] 2026-10-07 16:07 UTC: Opened PR #3033 after GitHub's service disruption.
  Sim build 366 deployed `sim-6a45222`; both API replicas passed 36 probes and
  matching module hashes. Fresh guest read, audio backfill and listen passed.
- [x] 2026-10-07 16:34 UTC: Reproduced both Devin findings: indented examples and
  verbatim escaped hints. Ten new regressions failed before the corrections;
  the corrected focused suite passed, including real-choice preservation.
- [x] 2026-10-07 16:36 UTC: Learning/profile 2,521 passed (1 skip, 4 subtests),
  including all 38 focused regressions and the full engine. Expanded deployment
  probes passed 55 checks locally without provider calls or database writes.
- [ ] Verify the review fixes locally and on sim, reply to both inline findings
  and the independent docstring warning, and check final CI.

## Surprises & Discoveries

The screenshot's source notation and installed frontend parser were correct.
Editor debug sessions live in expiring Redis entries, not learner session rows.
Read-only sim inspection found the same model emitting both three and four
options, with the fourth exactly duplicating the input hint. No user or course
record was modified during diagnosis.

## Decision Log

- 2026-10-07: Prioritize this reported bug; retain cross-course memory work in a
  separate checkout and PR.
- 2026-10-07: Correct only unambiguous authored hint duplication. Do not globally
  remove options whose text happens to equal a placeholder or constrain dynamic
  follow-up questions. Repair pending controls without changing past answers.

## Outcomes & Retrospective

Local verification is complete, including an actual malformed sim tool call,
engine-to-renderer controls and free-text submission. The first revision is
published and verified on sim. Review corrections and final CI verification are
in progress. Human approval owns the main merge.

## Context and Orientation

`engine/tools.py` reads authored notation and defers typed interactions;
`engine/engine.py` creates per-turn dependencies and resumes saved pending
questions. `legacy_protocol.py` renders controls back into `?[...]` and verifies
parser round trips. Both teacher debug previews and learner runs use this engine.

## Plan of Work

Extend the existing authored-question scanner with variable, hint, and choice
mode metadata. Compare complete ordered display/value pairs before repairing a
hint-only extra option. Normalize new tool specs and saved pending specs with
the same helper. Cover negative matches, escapes, saved history, and actual
learner input persistence.

## Concrete Steps

From the repository root, activate the `ai-shifu` conda environment, then run:

```sh
cd src/api
python -m pytest tests/service/learn/agent/engine/ tests/service/learn/agent/test_legacy_protocol.py -q
python -m pytest tests/service/learn/ tests/service/profile/ -q
cd ../..
python scripts/build_repo_knowledge_index.py
python scripts/check_dev_tools.py
lefthook run pre-commit --all-files
```

Use a focused feature branch and PR to main, integrate the tested change into
sim, verify deployed module hashes and new preview controls, and inspect reviews,
inline comments and issue comments before handoff.

## Validation and Acceptance

A malformed three-choice-plus-hint tool call must render exactly the three
choices and one input. A typed answer must survive serialization and be stored
unchanged. Real authored choices and unmatched dynamic questions must survive.
Existing pending controls must be corrected without changing classroom history.
The installed renderer must visibly show the corrected controls. Final CI and
sim runtime must use the final reviewed commit.

## Idempotence and Recovery

The correction is idempotent: the corrected controls match the author's choices
and are left unchanged on subsequent turns. Reverting the code restores prior
rendering without data migration. Keep all diagnostic access read-only and use
fresh internal learners for sim acceptance. Never reset the reported lesson.

## Interfaces and Dependencies

No public tool arguments or frontend protocols change. Per-turn `Deps` carries
parsed main-script input declarations. No dependencies, configuration, schema,
production routes, or analytics event contracts change.

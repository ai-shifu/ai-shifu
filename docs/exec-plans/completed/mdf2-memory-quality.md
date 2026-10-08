# Current memory evidence and repeatable quality baseline

## Purpose / Big Picture

Provide the 2026-10-09 concentrated testing with a repeatable, reported real-model
baseline for explicit memory admission and exact current-memory recall. Fix the
reproduced stale-answer behavior: a repeated memory question must read the current
snapshot instead of copying an earlier answer after an update or deletion. Existing
unit and host-storage tests cannot measure model decisions on fixed semantic
examples. Keep this PR focused on current-memory answer fidelity and its acceptance evidence.

## Progress

- [x] 2026-10-08 18:59 CST: Inspected existing semantic judge, engine recall,
  course selection, storage integration tests and the shared gateway.
- [x] 2026-10-08 19:03 CST: Added eighteen fixed synthetic cases and twenty offline
  evaluator regressions; provider/structured failures cannot pass as refusals.
- [x] 2026-10-08 19:14 CST: Reproduced both stale-answer failures with the actual
  course model, then confirmed that explicit current-turn recall instructions
  corrected the facts in that diagnostic. Preserve failing reports; later repeated
  acceptance can still fail and must remain visible.
- [x] 2026-10-08 19:17 CST: Candidate rule passed all 54 results (18 cases,
  three repetitions) with the actual course model. This used temporary operator
  prompt files and the initial procedural fixture; it is preliminary and
  superseded by natural-script evaluation following review; verify the deployed prompt after sim release.
- [x] 2026-10-08 19:27 CST: Deployed procedural-fixture run retained 53/54
  passing results, zero errors and one stale deleted-memory answer. The prompt
  change does not establish stable acceptance; do not discard this failure.
- [x] 2026-10-08 19:32 CST: Natural-script baseline retained 48/54 passing
  results, zero request errors; updated/deleted cases failed all three repetitions.
  Inspection found conflicting tool guidance: the tool still said to use recall
  only for missing context. Align the tool description and system rule next.
- [x] 2026-10-08 19:43 CST: Tool/system wording alone still failed all six
  changed/deleted diagnostic repetitions (6/12 recall passes). Actual requests
  contain the new system rule and offered tool. Added bounded current-snapshot
  revalidation notices derived from prior exact reads; source history stays exact.
  All 458 engine regressions passed before four additional legacy-value guards.
- [x] 2026-10-08 19:50 CST: A leading dynamic system notice still failed all six
  changed/deleted repetitions. Place the bounded host notice next to the current
  learner question as well, without changing accepted admission inputs. The
  actual-model candidate passed 12/12 recall checks (four cases, three repetitions).
  All 509 engine/evaluator regressions passed, including the admission boundary.
- [x] 2026-10-08 20:02 CST: Deployed current-turn context passed the complete
  54-result suite, zero errors. Encoded-name budget hardening followed in
  `8c569cc76`; sim `c912b5a08` (build 413 / Drone 5204, deployments 2004/2005)
  independently passed another complete 54/54 with zero errors and no candidate
  overrides. Both ready API replicas match all twelve runtime fingerprints and
  route to 2.0. Fresh-learner HTTP read, 2.22-second TTS backfill and listen-mode
  completion passed on that final runtime.
- [x] 2026-10-08 19:22 CST: Learning/profile/evaluator integration passed 2,785
  tests, one expected skip and four subtests; all 444 engine tests and repository
  gates passed. PR #3051 is open, sim build 410 is running. A subsequent scoring
  regression (27 focused checks) also catches in-place stored-history mutations.
- [x] 2026-10-08 19:28 CST: Addressed three scoring review gaps: natural author
  fixture, visible-content continuation and paired ordered exact-key evidence.
  Record controlled generation settings; verified CN image scripts are absent.
- [x] 2026-10-08 20:02 CST: Full learning/profile/evaluator coverage passed
  2,824 tests, one expected skip and four subtests. The final encoded-name
  regression raises focused engine/evaluator coverage to 510; all repository
  gates pass. Every independent review finding has an original-thread reply,
  including both findings in the combined CodeRabbit thread and the docstring
  warning. CodeRabbit's subsequent rate limit is not a completed final review.
- [x] Publish the final runtime and acceptance evidence for required PR checks.
  PR #3051 remains open; check its live status for CI conclusions.
- [x] 2026-10-08 20:27 CST: User merged PR #3051 as `af98a169c`. Main build
  415 / Drone 5206 succeeded; deployments 2008–2015 all succeeded. Six CN and
  two US API replicas each match twelve runtime fingerprints and retain 1.0
  selection. Persisted-answer follow-up continues in `mdf2-memory-journey.md`.

## Surprises & Discoveries

The product judge intentionally returns false on provider/validation failures.
An evaluator must independently validate the model response before treating that
false as semantic evidence, otherwise outages inflate the refusal score.

After correcting the synthetic first-message envelope, the real model still copied
old answers in both updated and deleted scenarios: 16/18 full-catalog cases passed,
then a focused two-case diagnostic reproduced both failures. Strengthen the
production recall prompt to require a current-turn read for learner memory
questions. The deployed 53/54 run still shows a stability gap; the stronger prompt
is guidance, not an enforced output authorization boundary.
A model may emit correct content before finishing; mirror the host
with at most one automatic continuation, retaining all output and errors.

## Decision Log

- Use the actual product judge and real engine, not a second judge prompt or
  direct provider client. All calls use current course gateway selection.
- Use only synthetic sessions and snapshots; persist no learner memory/session.
  Existing gateway usage accounting still runs under a dedicated test learner.
- Score exact current tool evidence and retained history, not only a substring
  that could have come from stale history. Report every failure and denominator.
- Compare only prior exact reads with the current authorized snapshot. Place a
  value-free host notice beside the question as well as in dynamic instructions;
  leading instructions alone did not correct the reproduced behavior. Accepted
  learner write-authorization inputs remain verbatim. Bound names after delimiter
  escaping so learner-controlled names cannot exceed the stated budget.
- Keep live calls opt-in, sequential and unavailable on a 1.0 environment.
  Keep human quality, database authorization and long-term cost acceptance separate.

## Outcomes & Retrospective

The evaluator exposed a stale-answer defect. The temporary procedural candidate
passed 54/54, but deployed acceptance failed one deleted-memory repetition (53/54).
The natural script then exposed all six updated/deleted failures (48/54).
Aligned tool guidance and a leading dynamic system notice each still failed all
six relevant repetitions. Adding the bounded notice beside the current question
passed a 12/12 recall candidate run. The deployed current-turn context then
passed 54/54, and the final encoded-name hardening independently passed another
54/54, both with zero errors. Actual sim runtime fingerprints and HTTP read,
TTS backfill and listen completion passed. Required PR checks and manual merge
are tracked in PR #3051; the manual merge and both production regions are verified above.
The focused baseline is complete; further persisted-answer acceptance continues
in [the next plan](./mdf2-memory-journey.md).
Earlier failures remain evidence. The evaluator rejects wrong-key, contradictory,
late and invalid reads and preserves usage/assertions for malformed tool output.
This baseline does not complete the entire quality milestone or authorize production.

## Context and Orientation

`memory_admission.make_request_check` owns independent semantic authorization.
`engine.recall` owns exact bounded reads of an already authorized snapshot.
`lesson_entry._resolve` owns published lesson access and model selection.
The canonical [quality reference](../../references/markdownflow-memory-quality.md)
defines cases, scoring, invocation and limitations.

## Plan of Work

Add the catalog and opt-in evaluator, test its fail-closed scoring with real
FunctionModel engine turns, then run the actual selected course model on sim.
Retain failed reports as evidence and repair only defects in this PR's scope.

## Concrete Steps

1. Run `python scripts/evaluate_mdf2_memory.py --list` from `src/api`.
2. Run `python -m pytest tests/scripts/test_evaluate_mdf2_memory.py -q`.
3. Run live with a dedicated temporary learner and accessible sim lesson;
   retain JSON report and inspect every failed/error result.
4. Run learning/profile integration coverage and all repository gates before
   committing. Push only to origin, open the focused PR, synchronize sim.

## Validation and Acceptance

The catalog has fourteen admission cases and four real-engine recall cases.
Reports must distinguish incorrect decisions from failed requests, missing cases,
subsets and duplicates. Read-only recall must not change memory or original
history. Live results record model/source fingerprints and usage; claims are
limited to actual repetitions and never imply human acceptance.

## Idempotence and Recovery

Each case/repetition creates a fresh model/checker/session. A rerun makes new
billed gateway calls but cannot overwrite learner memory. Reports replace only
the explicitly chosen local output file, atomically with mode 0600. Keep an
initial failing report before running a focused diagnostic report.

## Interfaces and Dependencies

The opt-in recall prompt/tool guidance gains a current-evidence rule, and current
instructions and a current-turn host notice flag stale prior reads against the
authorized snapshot. Accepted learner input remains verbatim for write admission. No product
DTO, SSE, frontend, persistence schema, dependency or environment switch changes. Reuse GatewayModel, current access selection, Engine and the
existing admission factory. The CLI and versioned JSON report are local operator
interfaces; they are not public HTTP endpoints. The currently verified CN deployment image (built by the separate deployment
Dockerfile, unlike the public repository Dockerfile) does not include these scripts: copy the evaluator and catalog to a private
temporary directory and set API_DIR to the deployed application when running an
in-image operator probe; verify runtime fingerprints against the source checkout.
Do not replace any files used by the serving process.

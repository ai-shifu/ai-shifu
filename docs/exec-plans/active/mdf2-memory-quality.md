# Current memory evidence and repeatable quality baseline

## Purpose / Big Picture

Provide tomorrow's concentrated testing with a repeatable, reported real-model
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
  correct the facts. Preserve failing reports; run the complete candidate next.
- [x] 2026-10-08 19:17 CST: Candidate rule passed all 54 results (18 cases,
  three repetitions) with the actual course model. This used temporary operator
  prompt files and is preliminary; verify the deployed prompt after sim release.
- [ ] Run the complete baseline against the deployed sim runtime and retain results.
- [x] 2026-10-08 19:22 CST: Learning/profile/evaluator integration passed 2,785
  tests, one expected skip and four subtests; all 444 engine tests and repository
  gates passed. PR #3051 is open, sim build 410 is running. A subsequent scoring
  regression (27 focused checks) also catches in-place stored-history mutations.
- [ ] Complete deployed-sim acceptance, final CI and every independent AI reply.
- [ ] Await manual main merge and verify post-merge release selection.

## Surprises & Discoveries

The product judge intentionally returns false on provider/validation failures.
An evaluator must independently validate the model response before treating that
false as semantic evidence, otherwise outages inflate the refusal score.

After correcting the synthetic first-message envelope, the real model still copied
old answers in both updated and deleted scenarios: 16/18 full-catalog cases passed,
then a focused two-case diagnostic reproduced both failures. Strengthen the
production recall prompt to require a current-turn read for learner memory
questions. A model may emit correct content before finishing; mirror the host
with at most one automatic continuation, retaining all output and errors.

## Decision Log

- Use the actual product judge and real engine, not a second judge prompt or
  direct provider client. All calls use current course gateway selection.
- Use only synthetic sessions and snapshots; persist no learner memory/session.
  Existing gateway usage accounting still runs under a dedicated test learner.
- Score exact current tool evidence and retained history, not only a substring
  that could have come from stale history. Report every failure and denominator.
- Keep live calls opt-in, sequential and unavailable on a 1.0 environment.
  Keep human quality, database authorization and long-term cost acceptance separate.

## Outcomes & Retrospective

The evaluator exposed and now covers a stale-answer prompt defect. Candidate
real-model acceptance is 54/54 with zero errors using temporary operator prompt
files. Offline checks passed and PR #3051 is open. Final CI and deployed-sim acceptance
remain pending. This initial baseline does not complete the entire quality milestone.

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

The existing opt-in memory recall prompt gains a current-evidence rule. No product
DTO, SSE, frontend, persistence schema, dependency or environment switch changes. Reuse GatewayModel, current access selection, Engine and the
existing admission factory. The CLI and versioned JSON report are local operator
interfaces; they are not public HTTP endpoints. The current deployment Dockerfile
does not copy operator scripts: copy the evaluator and catalog to a private
temporary directory and set API_DIR to the deployed application when running an
in-image operator probe; verify runtime fingerprints against the source checkout.
Do not replace any files used by the serving process.

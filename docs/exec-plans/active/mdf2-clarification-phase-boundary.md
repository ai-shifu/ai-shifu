# Keep Knowledge Clarification Within Its Authored Phase

## Purpose / Big Picture

A current-turn authored reference applies correction-only withholding to knowledge
clarification. Scope those limits to checking-direction and authored-help feedback so a permitted
side question can receive a brief response and return to the pending exercise.
Preserve the teacher's disclosure limits, including a prohibition on examples.

## Progress

- [x] 2026-10-13: Functional repair 557352ec3 passes all eleven checks and
  completed Codex review. CodeRabbit's later rate-limit SUCCESS is not counted
  as a new review. Reply 4257856022 records adoption of root 4257773675.
- [x] 2026-10-13: Combined sim f67afe0f7/build640/Drone5429 deploys successfully
  in records 2936/2937: API2/2 and Web1/1 on sim-f67afe0. Both APIs match 69
  fingerprints and pass 490 SDK/logging cases. Integration passes 3890 cases,
  50 subtests and two expected skips plus all gates. Complete API matches the
  independent schema candidate except this PR's reference source and test;
  this is explicitly combined verification, not a standalone full-API claim.
- [x] 2026-10-13: A new isolated learner makes two ordinary HTTP requests on
  unchanged published materials, model slot2 and original budgets. All three
  feedback objects select clarification; after two genuine provenance rejections
  the complete response is displayed and the same original exercise stays pending.
  Four original output/token tuples uniquely bind two traces to actual attempts,
  blocks and all 36.06 settled credits. Four history elements are stable on two
  reads; rejected prose is absent from deserialized stored TextParts. Original
  classrooms and the prior failed balanced learner remain unchanged.
- [x] 2026-10-13: Stop full-classroom acceptance on a separate visible factual
  error: the narrative adds 1 to 2, but its program loads 2 and adds 2, producing
  4 instead of 3. Do not repair the evidence or fail solely for missing expansion.
  There are no summaries, completed questions or final statistics. No quantitative
  teacher-brevity pass, full teaching-quality pass or #3122 pass is claimed.
- [ ] Complete the broader fresh eleven-question natural-compression/statistics/
  billing acceptance independently; the two-request factual failure is preserved.

- [x] 2026-10-13: Adopt Codex finding 4257773675: authored-help correction
  also retains condition matching, teacher multiplicity and disclosure limits.
  Four initial/reloaded uncounted/two-question SDK checks first fail against
  0b885270e. Limit only the clarification exemption; do not waive correction
  rules for the ordinary authored-help branch.
- [x] 2026-10-13: Validate the review repair: all four new authored-help cases
  fail before the fix; final learning/script suites pass 3860 cases, 50 subtests
  and two expected skips. Preserve both correction branches and the teacher
  limits without changing inputs, schema or budgets.
- [x] 2026-10-13: Push 557352ec3, reply in the original review thread and verify
  its current CI/review and repaired sim as recorded above.

- [x] 2026-10-13: Synchronize with main 7e3a34e24, including the independent
  response-lifetime fix #3128 and log-startup fix #3130.
- [x] 2026-10-13: Remove inherited #3122 worked-example instructions/tests and
  later forced-walkthrough retry guidance from this PR's final delta. Preserve
  their history and failures independently. The only runtime delta is the
  phase-scoped authored reference; no schema or model change is included.
- [x] 2026-10-13: Initial scoped regression passes 238 cases before this final
  baseline synchronization. Extend authority coverage to teachers who prohibit
  worked examples, plus initial/reloaded native retry behavior.
- [x] 2026-10-13: All ten phase/authority cases fail on the original main
  reference, then final independent-main learning/script suites pass 3856 cases,
  50 subtests and two expected skips. Original teacher/source and request limits
  remain unchanged.
- [x] 2026-10-13: Final repository gates, functional-head CI/review and both
  deployed sim replicas are verified above.
- [x] 2026-10-13: Record the actual-model check at its exact scope; broader fresh classroom
  natural compression, statistics and billing acceptance remain open.

## Surprises & Discoveries

The earlier stacked PR included the unmerged worked-example policy and pressure
to deliver requested walkthroughs. Those are distinct from a host phase-boundary
bug. A learner's request for an expanded example can conflict with the teacher's
brief-response instruction; missing expansion alone is not a platform defect.
Previously recorded factual errors in generated programs remain errors.

The separate balanced-model classroom comparison stops after opening and its
first knowledge request: four feedback-string calls fail native object validation.
Five generations settle 45.60 credits without a visible clarification. That is
protocol evidence for #3125, not a factual or phase-boundary pass for this PR.

## Decision Log

- 2026-10-13: Target main directly. Keep #3122 and #3125 changes out of this PR.
- 2026-10-13: Preserve verbatim author scope and current learner input. Do not
  add a semantic grader, require examples against teacher limits, relax criteria,
  change model slots or increase any request/retry/context budget.
- 2026-10-13: Retain historical failures in their original evidence and Git
  history. Changing PR dependency/scope does not change those verdicts.

## Outcomes & Retrospective

The independent phase-boundary fix has scoped local, CI, review, deployed SDK and
ordinary-HTTP delivery evidence. All prior failures remain preserved; the new
visible program mismatch prevents full-classroom acceptance. This PR does not
claim general model accuracy, teacher-style compliance or #3122 acceptance.
The final documentation receipt has an unchanged API/test tree; verify its own
checks in the PR conversation before recommending the current head for merge.

## Context and Orientation

`answer_context.py` builds the bounded request-local authored reference.
`test_clarification_scope.py` checks phase/teacher authority in initial and restored
SDK calls. The broader acceptance record remains in
`mdf2-broader-classroom-acceptance.md`; independent schema work remains in
`mdf2-feedback-branch-schema.md` on its own PR.

## Plan of Work

Keep correction restrictions scoped to both checking-direction and authored-help. Deliver the same
author source to knowledge clarification, preserve brevity/disclosure limits and
return to the same pending exercise. Verify the independent candidate before
changing its merge recommendation.

## Concrete Steps

Run the focused clarification/reference/feedback suites, then all learning and
script regressions. Stage complete documents before regenerating the knowledge
index. Run tooling, harness and all-file hooks; push the existing branch without
rewriting history and retarget its existing Open PR to main.

## Validation and Acceptance

Both supported feedback modes and session reload retain exact author text,
current input, prior history, unchanged script and memory. Correction limits do
not apply to a permitted clarification, teacher example prohibitions remain in
force, and retries display only the complete accepted response. No next exercise
appears before actual navigation. Record CI, both actual sim fingerprints and
isolated SDK regressions separately from model factual performance.

## Idempotence and Recovery

Never reset or repair an existing classroom to obtain acceptance. Keep prior
failures and immutable-source evidence. Git history retains the previous stacked
candidate. Production is read-only; use only isolated internal learners in sim.

## Interfaces and Dependencies

No public API, stored session format, tool payload, database schema or library
version changes. Main supplies the already merged lifetime and logging fixes.

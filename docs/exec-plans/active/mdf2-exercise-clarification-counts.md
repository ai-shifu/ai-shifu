# Keep knowledge questions out of exercise answer counts

## Purpose / Big Picture

A knowledge clarification without an attempted answer must not count as a new
answer or retry. Preserve its original reference and distinguish it from a real
answer whose correctness is unverified. Keep actual wrong attempts counted.

## Progress

- [x] 2026-10-10: #3088 merged; its final sim quotation sample passes three
  answers, including repeated-question chronology and post-deletion quotation.
- [x] Inspect the retained eleven-question natural session: no eligible long
  teaching response precedes its final statistics. Preserve it as short-history
  evidence, not a compression acceptance result.
- [x] New internal learner completed all eleven exercises in 28 HTTP turns.
  The original failure is preserved: two knowledge questions were labeled
  unverified, inflating 14 answer attempts / three retries to 16 / five.
- [x] Actual teaching max is 4,055 JSON-wire bytes, below the production 4,096
  threshold, and the summary cache is empty. Natural compaction remains open.
- [x] All 38 actual requests succeeded and settled for 67.95 credits; each
  matches its real course/progress/block/owner. No SQL writes or old-learner resets.
- [x] Four new count cases fail before the correction. The candidate passes
  615 engine/evaluator tests and 3,176 learning/profile/evaluator tests plus four
  subtests and one expected skip, including the actual SDK non-answer schema.
- [x] Published #3089 as a601b4d91 / sim 8cc763e5e. Initial candidate
  deployed but no paid replay ran before the byte-capacity review correction.
- [x] Devin's 41-question boundary finding is reproduced as a failing test.
  Omit zero non-answer fields in rows and totals, preserving old zero-case JSON
  capacity; absent counters mean zero. Final 615 engine/evaluator and 3,176
  broader cases pass plus four subtests and one expected skip.
- [ ] Publish byte-capacity correction and reply in the original Devin thread.
- [ ] Verify runtime hashes, replay the retained pre-report original session
  without persistence, and compare every actual attempt and reported count.
- [ ] Reconcile replay costs, preserve original completed sessions, answer every
  AI opinion and record final CI. Do not claim compressed-course acceptance.

## Surprises & Discoveries

The earlier retained quiz has 62 persisted messages; its first 51 messages include no
response text above the production 4096 JSON-escaped UTF-8 byte threshold. The
large opening user prompt is not eligible teaching. Enabling projection alone
does not prove that any classroom teaching was compressed.

The new report actually calls the calculator with incorrect/unverified/correct
for each question containing a clarification. Arithmetic is internally consistent
but its semantic categories cannot represent a non-answer. This is a demonstrated
counting defect, distinct from compaction; do not tune the threshold to manufacture
compression evidence.

## Decision Log

- Use a new internal learner; never rewind or rewrite the original completed
  learner, alter published course content, or inject padded historical messages.
- Ask a realistic clarification during a normal classroom interaction. Whether
  its actual response becomes eligible is observed, not forced with a lower
  threshold or fabricated teaching. If no eligible source is produced, report
  that limitation rather than replaying unchanged paid calls until a pass.
- Read stored sessions through the existing read-only account. Use HTTP for
  authorized learner actions. Sim shares the China production database.
- Add a not_answer judgment to the existing evidence-bound calculator. Retain
  exhaustive original references and chronological validation; filter only that
  semantic category from attempts, retries, failures and first-answer selection.
  Report its count separately. Unverified real answers still count as attempts.
  Classification remains a model judgment, never a keyword filter or permission
  to erase an actual wrong answer. Hints remain independently judged from evidence.
- Grade question membership and chronology against actual original answers and
  feedback. Correct totals alone cannot hide swapped question results.

## Outcomes & Retrospective

The narrow counting correction is pending natural replay. This is a one-course, one-model technical journey, not human acceptance,
an all-provider benchmark, a production switch or permission to delete 1.0.

## Context and Orientation

The engine projects only older eligible teaching parts, retains two recent turns,
and caches position-bound summaries. Exercise tools read original submissions
and validate calculations. The dedicated computer course has eleven exercises;
its earlier complete natural journey failed statistics before the calculator fix.

## Plan of Work

Preserve the failed natural classroom report and its full original session.
Exercise not_answer before, between and instead of answer attempts through the
calculator and actual SDK. Publish the focused fix, verify sim runtime, then replay
the exact pre-report pause once without changing the completed learner. Compare
complete source reads, semantic judgments, calculated totals and final report.

## Concrete Steps

Use conda ai-shifu and existing HTTP helpers. Store credentials and raw evidence
only in 700/600 private paths. Run appropriate regression and repository gates
for any fix, push to GitHub origin, submit an Open PR and answer every AI opinion
in its original discussion. The user merges manually.

## Validation and Acceptance

Require unchanged original history, complete reference coverage, correct grading
membership, exactly 14 real attempts / three retries / two non-answer inputs, normal
HTTP/SSE completion, and real usage/progress/block/owner attribution. Report
unknown hint counts as unknown. Missing compaction is not a passing compressed
statistics test. Preserve failed answers and distinguish logical turns from paid
provider requests and auxiliary summaries.

## Idempotence and Recovery

Refuse to overwrite evidence or reuse the original learner for a new journey.
Retain a failed HTTP turn before investigating. Do not retry unchanged paid
answers for a favorable sample, mutate SQL, deploy production configuration,
delete 1.0 or merge automatically.

## Interfaces and Dependencies

Extend only the existing internal statistics-tool outcome enum and result counts;
update its prompt, description and tests together. No schema, endpoint, frontend,
provider or memory-write change. Reuse Session, original exercise records and the
existing usage ledger. Never commit raw course/learner content, credentials or tokens.

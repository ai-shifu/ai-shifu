# Fresh classroom after authored grading corrections

## Purpose / Big Picture

Exercise a fresh eleven-question natural lesson through the learner HTTP path
after #3096. Saved-checkpoint replays and synthetic controls do not establish
that question delivery, grading, clarification, correction and the final report
work together in a new classroom. Keep all failed evidence and all legacy code.

## Progress

- [x] 2026-10-11: Confirm #3096 merged as ebccd9037. Sim already serves the
  corrected runtime; check both replicas against merged source before learning.
- [x] 2026-10-11: Start a new internal test learner and complete the existing
  published eleven-question lesson without resetting or replaying its session.
- [x] 2026-10-11: The first fresh HTTP request fails before any answer: text-only
  `<interact ... />` is repeated across three turns and the repeat heuristic
  marks the lesson finished. Preserve all three settled requests (3.42 credits)
  with real progress/block attribution; no learner reset or historical repair.
- [x] 2026-10-11: Four SDK regressions fail before correction. Add bounded output
  validation, hide only standalone unexecuted tags and refuse finish while the
  question has not been created. All 591 engine checks and 3,277 learning/script
  checks plus 50 subtests pass, with three expected skips.
- [x] 2026-10-11: Reproduce and fix intervening-tool loss and custom-element
  false positives from AI review. Reconstruct the unfinished guard from saved
  history, stopping at an actual answered interaction. A separate saved-history
  regression fails before correction, and completion after a real answer remains
  allowed. Final learning/script checks pass 3,283 tests and 50 subtests with
  three expected skips; developer-tool/all-files gates pass.
- [x] 2026-10-11: Review question order, authored answer criteria, clarification
  handling, retries and final report against actual learner-visible responses.
- [x] 2026-10-11: Verify persisted history, real compression when present,
  request attribution and settled billing with read-only evidence.
- [x] 2026-10-11: Open #3097 for the focused unexecuted-interaction defect.
  Source d7b12d477 passes 3,283 learning/script checks and 50 subtests (three
  expected skips); sim's 732 engine/host checks and repository gates pass.
  Reply to all four inline AI findings and the separate docstring observation.
- [x] 2026-10-11: Sim a7c72ea22 builds successfully (build 530 / Drone 5319),
  API 2/2 and web 1/1 Ready. Both API replicas match all 55 source/runtime hashes.
  Restore the genuine saved pre-repeat checkpoint in memory: turn two, four
  original messages, unfinished and no pending input. The actual course model
  repeats the textual tag once, receives the runtime retry, then calls interact
  for the original first question with its meaningful text placeholder. No
  display leakage, errors or completion; original prefix and memory preserved.
  Two real generations settle 2.31 credits, with actual user/course/lesson/owner
  attribution and no invented classroom attempt IDs. Original progress,
  session, variables, four blocks and ten history elements remain unchanged.

- [x] 2026-10-11: Confirm #3097 manually merged as 267c16ad6. Merged source
  matches the deployed sim runtime on all 55 paths across both API replicas.
  Resume the retained new HTTP learner at its first pending question; never reset
  the earlier failed classroom. The first deliberate wrong answer receives a
  directional hint and another real text input without advancing.

- [x] 2026-10-11: Continue the retained new learner through all eleven questions,
  in 27 ordinary HTTP/SSE requests. All controls and question ordering pass;
  three incorrect/incomplete answers require genuine learner corrections. The
  completed lesson's 27 visible text elements exactly match persisted history;
  two reads return the same 54 elements. All 39 actual generations settle 65.70
  credits with real progress/block/owner attribution. No original exceeds the
  4,096-byte compaction threshold (maximum 3,412), and no summary is generated.
- [x] 2026-10-11: Preserve the failed report: attempts 14, retries 3, first-correct
  8 and two excluded knowledge questions are correct, but independent-first is
  8 instead of 6. The calculator received hints_before_first=0 for both qualifying
  pre-answer explanations. Save independent expectations before the final answer.
- [x] 2026-10-11: Clarify actual-answer timing in the runtime report policy,
  calculator documentation and provider-visible hint fields. Cover schema delivery
  after serialized resume and independent/assisted/unknown timing arithmetic.
  Both schema-delivery controls fail before correction; final learning/script
  checks pass 3,286 tests and 50 subtests, with three expected skips. Developer
  tools and the all-files repository gate pass.
- [x] 2026-10-11: Verify the corrected report on the deployed candidate using the
  genuine pre-final-answer checkpoint without rewriting the failed classroom;
  then open #3098 and reply to every AI opinion. Sim 116f7287f serves API 2/2
  and web 1/1 Ready; both API replicas match all 55 runtime/resource fingerprints.
  One in-memory replay produces all eleven correct report rows, 14 attempts,
  three retries, eight first-correct and six independent-first, matching the
  expectation saved before the final answer. All eleven traced generations carry
  the timing guidance and settle 25.25 credits. No summary, errors or invented
  attempt IDs; original messages/memory, persisted progress/session/variables and
  all 108 element rows (including historical rows) remain unchanged. Current
  learner history still contains the stable 54 elements. Initial result-file
  retrieval failed; reading the already-created file recovered it without a
  second model run.
- [x] 2026-10-11: Adopt the AI fixture observation in a4b0cc503, using a genuine
  knowledge-question/answer pair and explicitly limiting the deterministic test
  to arithmetic. All 33 focused checks and all-files gates pass; reply in the
  original thread. Decline the external docstring-percentage suggestion with the
  repository's existing test exemptions and documented runtime contract.
- [x] 2026-10-11: Confirm #3098 merged as 7190bd64c and the intervening UI
  upgrade #3099 merged as 323612b6c. On sim f138f1fd3, both ready API replicas
  match all 55 runtime/resource hashes from the merged source.
- [x] 2026-10-11: A new internal learner completes the same eleven-question
  published lesson in 27 ordinary HTTP/SSE requests, without reset or checkpoint
  replay. Three wrong/incomplete answers require new learner corrections; two
  knowledge questions do not count as answer attempts. The minimal five-point
  answer advances without an added peripheral requirement; the authored dot
  matrix is preserved. Save independent expectations before the final answer.
- [x] 2026-10-11: Four sequential original-history pages cover all 16 relevant
  inputs. Every input's question/outcome binding, all eleven calculator rows,
  all totals and the visible report match that pre-saved expectation: 14 attempts,
  three retries, eight first-correct, six independent-first and five hints.
  Both knowledge explanations have one pre-first hint. The lesson finishes
  normally; a single unsolicited remember attempt is refused and no custom
  memory is stored. Original pre-final messages and the script remain intact.
- [x] 2026-10-11: All 27 visible teaching elements exactly match persisted
  history; two reads return the same 54 elements. All 35 actual generations
  settle 54.21 credits with matching real progress/block/owner attribution and
  no failed or outstanding charges. No summary generation or summary cache;
  maximum original teaching is 3,712 JSON-wire bytes, below 4,096.
- [x] 2026-10-11: Close this one-lesson acceptance scope and transfer remaining
  coverage to the memory-quality reference: other models/languages/providers,
  new naturally compressed full lessons, human feedback, long-term costs and
  broader course journeys remain open. Earlier failed classrooms remain failed;
  all MarkdownFlow 1.0 code is retained.

## Surprises & Discoveries

Production still served the preceding UI release when the initial run started. Sim's
existing deployment contains the merged grading correction, so identical runtime
code does not require another deployment or paid replay before a fresh lesson.

The first question is emitted as a self-closing XML-like text tag, although the
author wrote MarkdownFlow notation and never used that tag. The next two host
continuations repeat it without a tool call. The lesson is persistently finished
at turn three, with no pending interaction or submitted answer. Repetition is
not evidence of completion when the model never created the question.

## Decision Log

- Archive only the completed single-lesson acceptance scope. Keep prior failures
  and narrow replays labeled separately, and carry the remaining wider acceptance
  in `docs/references/markdownflow-memory-quality.md`.

- Use the existing temporary-learner and learner HTTP/SSE path on sim, where
  billing and persistence are real. No payment, SMS, course edits or learner reset.
- This is one complete natural lesson, not a claim that every lesson in the
  course, every model or human acceptance has passed.
- Use the unchanged authored script and runtime limits. Never alter answers,
  historical grades or thresholds retrospectively to obtain passing evidence.
- Fix the observed missing-tool boundary in this PR. Do not parse XML attributes
  into tool calls or memories. A failed correction raises an error under the
  SDK's existing output-retry limit instead of reaching repeat-based completion.
- Recognition is limited to complete single-line standalone `<interact ...>`
  tags outside fenced/indented code, with exact authored literals preserved.
  Inline or multiline imitations are not covered by this correction.
- Carry remaining human, provider/language and long-term acceptance in the
  workspace status and memory-quality reference; 1.0 retirement is inventory only.

## Outcomes & Retrospective

The fresh classroom is retained as failed at the first question. Prior failed
classrooms remain failed; #3096's saved-answer replay does not replace them.
The focused recovery passes on the deployed candidate. The same actual model
first repeats the tag, then follows the single output retry and creates the
original first text question. The trace confirms both requests; no summary is
requested. Failure plus recovery costs 5.73 credits in total (3.42 + 2.31).
This is in-memory recovery from a genuine saved checkpoint, not a new successful
HTTP lesson or a repair to its persisted completed state. The separate retained new learner now completes the lesson, but fails report
acceptance: two pre-answer explanations are counted as hints while their timing
is incorrectly supplied as zero. First-correct remains eight; independent-first
must be six under the unchanged authored rules. Completion and stable history
cannot override this failed semantic count. Its 39 actual generations settle
65.70 credits separately from the earlier 5.73-credit failure/recovery. The
deployed scoped replay now passes all eleven per-question and total counts,
including six independent-first and two non-answer knowledge questions. Eleven
traced requests settle another 25.25 credits, without any classroom repair.
A separate new complete natural lesson now passes after #3098: 27 normal
HTTP/SSE requests, all eleven authored questions and the report's exact original
input bindings, rows and totals. All 35 generations settle another 54.21 credits;
this is separate from earlier failed journeys and scoped replays, never a repair
to them. The new lesson generates no teaching summary, so it closes neither
compressed natural acceptance nor broader course/provider/language/human/cost
coverage. Those remaining items stay in the memory-quality reference. This plan's
single-lesson acceptance scope is complete; no runtime or legacy-code change is
needed to record its outcome.

## Context and Orientation

`agent/lesson_entry.py` orchestrates HTTP teaching turns; `run_agent.py` persists
session and learner-visible elements. The vendored engine's `system.md` supplies
authored grading guidance. Exercise history and statistics tools supply original
answers and computed totals for the final report. Private workspace helpers use
the existing HTTP interface and a read-only database account for verification.

## Plan of Work

Verify deployed runtime, start a new learner and inspect each response before
choosing the next answer. Include intentionally incorrect answers and knowledge
questions, then correct according to the actual authored criteria. Compare all
final report rows to actual inputs and feedback. Diagnose the first concrete
failure and keep any fix narrowly scoped.

## Concrete Steps

Use conda ai-shifu locally. Store raw prompts, identities, tokens, sessions,
traces and billing only in the private dated workspace evidence directory with
700/600 permissions. For changes, run focused failing-first tests, appropriate
engine/service checks, developer-tool checks and the all-files repository gate.
Push only GitHub origin. Deploy validated changes to sim and open a PR; do not
merge it automatically. Reply to every AI opinion in its original discussion.

## Validation and Acceptance

Observe all eleven authored questions in order, valid input controls, faithful
grading and retry boundaries, clarification excluded from answer counts and a
consistent final report with normal completion. Confirm retained HTTP content
matches persisted history, usage belongs to actual progress/blocks and settled
charges match the course owner. Report compression only when actual trace input
contains a summary bound to an original over-threshold teaching message.

## Idempotence and Recovery

Use unique evidence files, never overwrite failures or repeat an unchanged paid
probe to seek a pass. Sim and China production share storage. Database evidence
is read-only; normal test learning is the only intended persistence. Preserve
all existing learners, original sessions and unrelated local work.

## Interfaces and Dependencies

No planned dependency upgrade, schema migration, production configuration or
public API change. Determine any corrective interface changes only from observed
evidence and update all affected consumers together if necessary.

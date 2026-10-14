# Computed examples through existing lesson interactions

## Purpose / Big Picture

A generated program and its hand-written table can disagree even when the model
receives tracing guidance. Add an explicit, bounded computation payload to an
existing interaction. Compute its program states and render that artifact from
those same states, instead of accepting model-authored result rows. This is a
numeric artifact guarantee, not a semantic grader or a guarantee about surrounding
free prose. Keep the eleven-question factual acceptance gate independent.

## Progress

- [x] 2026-10-14: Re-read task formatter requirements and actual main 33f5ba47c,
  including merged #3134 shared formatting, #3135 version 3.0.0 and #3136 initial
  progress notification. Existing #3122 and shared sim remain unchanged.
- [x] 2026-10-14: Choose a same-response optional interact payload on supported returned text inputs so local
  computation adds no model request, planning turn, learner input or budget.
- [x] Add strict bounded integer-program validation, execution and canonical
  Markdown program/initial-state/table rendering, with negative and positive
  controls derived from retained failure classes.
- [x] Bind the canonical artifact to accepted interaction delivery and saved
  teaching; preserve native arguments, rejected-response isolation and reloads.
- [x] Verify provider schema transformations and the real formatter, element,
  history, audio and first-turn progress consumers on the current main.
- [x] Complete repository gates, ready PR #3137 and all original-thread review
  replies for code head 1d8f5ee8e. Its eleven checks pass; Codex explicitly
  reviewed that head, and CodeRabbit run 0243b99a reports no actionable comments.
  Seven code roots are resolved after replies; the classroom acceptance root stays open.
- [x] Inspect an authorized fresh ordinary-HTTP opening and first knowledge
  follow-up on deployed sim-8cf56ef. Stop on a visible loop-count factual failure.
  No preliminary paid checkpoint replay or unchanged paid resampling was run.
- [x] Add and verify accepted-use analytics after Codex review 4271281168:
  published modes only, anonymous bounded payload, native timing/deduplication and
  asynchronous fail-open transport. No paid classroom rerun accompanies it.
- [ ] Verify the analytics commit's own CI/reviews and reply in the original thread;
  the real classroom acceptance root remains independently open.
- [ ] Pass fresh eleven-question natural compression, per-question statistics,
  actual summaries and final cost attribution; the first-question failure holds this gate.

## Surprises & Discoveries

- The new task requirement forbids a second element classifier or a frontend
  compensation layer. Main #3134 already owns all-mode classification.
- A calculator returning a result to the model does not bind the displayed
  table: the model can rewrite it incorrectly. Render the program and trace
  directly as canonical teaching in the existing interaction response instead.
- A checked artifact does not prove that its program matches a free-form
  description, the author's permissions or the learner's request. Those remain
  explicit independent real-model acceptance requirements.
- An unavailable confirm normally continues without a pause. A computed payload
  must be rejected before that path can discard its artifact; a rollback control
  reproduces the loss. Original authored input and native retry budgets remain.
- Codex's initial actual-head review identified incompatible simultaneous bounds
  and malformed JSON releasing prose with feedback_contract off. Adopt both:
  reduce the new machine ceiling to 32 steps so all maximum-width columns and
  declarations fit the unchanged 16 KiB artifact, and conservatively buffer
  unparseable interact JSON while this capability is enabled. Four focused
  assertions fail before the fixes; 36 kernel/SDK/element cases pass afterwards.
  Pinned SDK 2.43 returns INVALID_JSON by default rather than raising; use its
  strict parsing option to distinguish that case without changing original args.
- Devin's original-head review found a portable non-resumed turn reprojecting
  earlier directions using the new turn's empty render mapping, and a repeated
  complete state at the execution boundary being missed. Preserve the existing
  prefix and project only new messages; check the final state
  before declaring exhaustion, while explicit prefixes remain incomplete.
  A five-turn/reload portable control and a first-repeat-at-32 boundary control
  pass in the 38 focused cases. The history rollback fails on exact saved-prefix
  equality. An initial fixture missed TextPart's import; retain that failure and
  use the corrected independent rollback as the behavioral reproduction.
  The full gate then caught that blindly appending the saved portable prefix
  loses the SDK's interrupted-tool repair. Retain its repaired prefix without
  display projection, and project only new messages; original memory/teaching
  compaction paths retain their existing evidence handling. All 51 focused
  kernel/SDK/element/interrupted-recovery cases pass together. The failed full
  run (4,014 passing / one failing) remains evidence; the final broad run passes
  4,015 tests, 50 subtests and two expected skips, with all-file hooks green.
- CodeRabbit's daba2eecb review independently identifies the already-fixed
  cycle boundary, and empty interact arguments bypassing strict parsing because
  the SDK returns an empty object. Adopt the latter for empty strings, objects
  and missing arguments when this capability is enabled. Empty-string and empty
  JSON-object native retry cases fail before the fix; four malformed/empty forms
  now preserve original arguments and withhold rejected prose through reload.
  All 53 focused artifact/history/recovery cases and the final 4,017 learning/
  scripts tests, 50 subtests, two expected skips and all-file hooks pass.
- Codex's 44954223b review identifies supplied custom toolsets bypassing the
  built-in sole-call validators. Apply the same computation-only guard through
  the SDK's before-tool-validation capability when enabled, before custom
  argument validators and execution. Both sibling orders reproduce the side
  effect before this fix; normal standalone custom calls still run afterwards.
  All 55 focused checks, 4,019 learning/scripts tests, 50 subtests, two expected
  skips and all-file hooks pass. No product model
  request has been made; sim-b98370c is not the final candidate for acceptance.
- Self-review of the initial streaming boundary reproduces already-visible
  prose disappearing from history when the model invents an unoffered artifact.
  Refuse the artifact and mixed side effects, but mark prose hidden only on the
  supported buffered turns. Single/mixed initial controls fail before the fix;
  all 57 focused artifact/history/recovery checks pass afterwards. This adds no
  initial buffering or model strategy. The preliminary sim-915f94b deployment
  (build 649 / Drone 5438, records 2984/2985) matches 73 files on both Ready APIs
  and passes 529 isolated SDK/logging cases each, but excludes this final fix.
  Final local gates pass 4,021 tests, 50 subtests, two expected skips and all-file
  hooks; the 57 focused cases include preserved initial streaming and history.

- Codex's actual 0b16af4fd review identifies the missing new-capability analytics
  contract despite unchanged learner actions. Adopt it: define the reference
  contract first, add a content-free optional engine observer after canonical
  stream output, and bind only published host turns to the shared asynchronous
  server queue. Config/network work stays on bounded workers, outside the native
  producer. Event data has exactly surface and learning_mode; no IDs or content.
  Both observer timing controls fail against the prior runtime. An initial
  missing-module collection failure is not behavioral evidence; retain it and
  the separate rollback reproduction. A wrong working-directory setup attempt
  changed no production files and was corrected before the passing run.
  The complete learning/scripts plus shared-tracker gate passes 4,051 tests,
  50 subtests and two expected skips; architecture stays 131 existing/zero new.
  Queue saturation, asynchronous failure, missing config and failed HTTP are
  isolated. Historical real-run evidence remains on 1d8f5ee8e; no new model
  request, learner, course edit or factual pass is claimed for this observation patch.
  CodeRabbit's minor unverified issue-reference warning is addressed by wrapping
  that paragraph without an issue reference at the beginning of a line.

## Decision Log

- 2026-10-14: Adopt Codex's 0b16af4fd analytics finding. A generated artifact is
  a new visible capability even though the learner's action and wire contracts
  stay unchanged. Define the accepted-use contract in the reference before code:
  one anonymous mode-bounded event per newly streamed accepted artifact, through
  an asynchronous shared server tracker. Preview/history/rejections/omissions
  emit none; this does not measure model-schema offers or browser visibility.
  Add offline native/host/transport controls, without a new paid classroom run.

- 2026-10-14: Use the authorized fresh ordinary-HTTP journey itself for changed
  runtime acceptance, inspecting opening/knowledge help before continuing.
  Avoid an extra paid checkpoint replay. Preserve all seventeen frozen inputs,
  source/standards, model slot, temperature and per-turn budgets; a learner's
  request to expand does not override authored brevity or disclosure limits.
- 2026-10-14: Offer computed_example only on supported returned text inputs,
  where existing native feedback already buffers the response. Preserve initial
  and unsupported-turn streaming and schemas. Use the optional interact payload, not arbitrary code
  execution, a hidden model judge, a new tool request or a course-specific gate.
  A portable Engine keeps this capability off unless its host enables it.
- The abstract language has explicit initial PC/registers/data and integer
  operations with fixed bounds. There is no file/network access, eval/exec,
  overflow inference, missing initialization default or author-source rewrite.
- State rows, branch destinations and halt/cycle/prefix status come only from
  execution. The payload accepts no model-authored result table or claimed final
  values. Unknown, malformed, out-of-range or budget-exhausted cases are refused.
- Reuse ordinary Markdown ContentDelta, the shared formatter and existing
  adapters; no frontend, DTO, SSE, element-number or stored-session-schema change.
- Existing source/phase/native interaction guards still decide whether the
  response can be delivered. An artifact never authorizes examples, disclosure,
  progression, a passing grade or additional learner requirements.
- Source comments/docs/PR remain English. Private learner identities, classroom
  JSON, tokens and raw generations remain outside version control.

## Outcomes & Retrospective

The bounded interpreter, canonical delivery and saved history are implemented.
Controlled SDK/provider/storage checks cover Ark/OpenAI/DashScope schemas and
read/classroom/listen formatter parity, exact SQLite history, audio eligibility,
rejected content, mixed-tool side effects and initial streaming timing.
The final full learning/scripts run passed 4,021 tests, 50 subtests and two
expected skips after the review fixes, interrupted recovery and initial-history preservation. Toolchain, repository
harness, architecture baseline (131 existing / zero new violations), and the
all-file lefthook gate passed. Source frontend, formatter, pager and element
adapter files are unchanged from actual main.
An offline retained-checkpoint probe used one SDK request, zero provider calls
and 126,889 wire bytes within the unchanged 262,144-byte input limit after review
(126,832 before the bounds description changed). Test failures
from the private probe's missing limit argument and pending-input lookup were
retained and corrected without a provider request or old-session write.

The existing #3122 prompt-only experiment remains held; its original failures
and the 18.59-credit balanced failure are retained. This candidate excludes the
prompt guidance of PR #3122. Final sim integration 8cf56ef18 / build 650 / Drone 5439
(records 2986/2987) deploys as sim-8cf56ef with API 2/2 and web 1/1 Ready.
Both actual APIs match 73 source fingerprints and pass 531 isolated SDK/logging
cases each; the complete API/web/i18n tree matches code head 1d8f5ee8e.

A single fresh internal learner used the unchanged authorized balanced clone,
model slot 2 (qwen/glm-5.3), temperature 0.3 and original seventeen frozen inputs,
standards and per-turn budgets. The opening passed. The first knowledge follow-up
failed: free prose claims two loop iterations, while the explicitly labelled ADD
loop body executes once (LOAD 4, SUB 2, failed JZ, ADD, JMP, SUB to zero, JZ, HALT).
R1's 4-to-2-to-0 arithmetic is correct and the program halts; this is not another
termination or arithmetic failure. R0 initialization is absent, but no final R0
value is asserted. Do not invent one or rewrite the retained output.

All four follow-up generation inputs offer the explicit computed_example object
schema and guidance, but every saved native call omits it. The real model never
exercised the computed artifact: the optional mechanism does not establish
coverage of freely generated examples. Source/learner input contains no such
program, and exact raw final content binds to the saved response; no evidence
attributes this loop-count mismatch to authored source, serialization or display.
A request for expanded help does not override the author's brief-response rule;
missing expansion or a quantified style-compliance pass is not asserted here.

The two normal HTTP/SSE requests produce two traces and five generations (one
opening, four follow-up attempts). Native retries reject a missing feedback
branch, a non-verbatim submission quotation and a control-only replacement.
Three rejected responses retain native tool arguments but zero saved TextParts;
this is not a first-draft protocol pass. All five raw content/output-token tuples
uniquely match usage, actual attempt/block and ledger owner/source. All 46.09
credits settle (7.87 opening, 38.22 follow-up); cached input tokens total 83,712,
with zero summary generations, completed questions or finished sessions.
Six typed history elements are stable across two reads and exactly match SSE:
text/interaction, then text/code/text/interaction. The original published course,
old classrooms and prior failed learners remain unchanged by read-only checks.

A browser history probe blocked all API writes and teaching requests before
navigation and reached login rather than the classroom; it is not a visual pass.
Its first launch lacked Playwright's bundled browser; the installed Chrome probe
completed with zero model calls. No access rule or course state was changed.
Private raw outputs, reasoning, SSE, identities, source snapshots and audit
receipts stay outside version control. The stopped classroom is retained and
its runner refuses further teaching calls. No extra learner, paid replay,
remaining phases, summary or budget increase follows the failure.

Acceptance remains failed and #3137 is not recommended for merge. The next
mechanism needs an offline, general proof of coverage when the model omits an
optional calculation payload, while preserving author permissions and the
existing formatter. No supported proof currently connects arbitrary free prose
to that payload; do not replace this missing property with prompt synonyms,
course-specific checks, hidden semantic grading or unchanged paid retries.

## Context and Orientation

The vendored engine owns tool schemas, native feedback gates and session history.
interact already renders source-bound structured checking directions into normal
teaching. run_agent and LessonPager on main now reuse the 1.0 StreamFormatter in
all modes. The normal element adapter persists that existing contract.

## Plan of Work

First prove arithmetic/state semantics and canonical rendering without a model.
Then use the actual SDK to prove one response can pause with a computed artifact,
that invalid calls retry without leaking text and that reload preserves exactly
what was displayed. Finally exercise current-main formatter/storage consumers and
provider-converted schemas, without weakening existing budgets or author gates.
Only a changed-runtime, independently inspected real-model result can justify
starting a fresh full classroom; stop on a genuine failure.

## Concrete Steps

1. Add focused red regressions before production code.
2. Add a bounded interpreter/renderer and integrate the optional tool payload.
3. Add end-to-end SDK/history and all-mode host/adapter checks.
4. Run relevant learning, provider and script tests and repository gates.
5. Create a ready focused PR, retain failed evidence and answer every AI opinion.

## Validation and Acceptance

Require initialized reads, distinct code/data addresses and valid targets; reject
booleans as integers, unsupported operations, excessive sizes/values and missing
instructions. A repeated complete state proves a cycle only for this deterministic
no-IO language. A prefix or step limit never proves termination. Correct controls
must retain their exact states, not merely reject every example.

Require one native model request for an accepted example interaction, canonical
program/table output and exact saved teaching across reload; raw arguments stay
original. Invalid feedback or interaction siblings must withhold all rejected
content. Reading/classroom/listening must reuse formatter output and keep the
existing history/rewind/audio and initial outline notification contracts.

Real-model acceptance must separately inspect requested behavior, author brevity
and disclosure boundaries, general teaching facts, raw/provider evidence and
billing. Full natural compression, statistics and summaries remain open.

## Idempotence and Recovery

No migration, production write or old classroom rewrite. Preserve dirty task
files and concurrent shared sim updates. A failed probe is retained rather than
rerun unchanged. Disabling this engine capability restores the previous schema;
existing stored canonical teaching remains readable as ordinary text.

## Interfaces and Dependencies

Use existing Pydantic models, native interact, ContentDelta and saved TextPart.
Do not add external dependencies or change frontend formatter or public events.
The numeric program language is an explicit internal tool-input contract, not
an evaluator of learner submissions or a replacement course DSL.

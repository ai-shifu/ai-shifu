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
- [ ] Complete repository gates, ready PR and all original-thread review replies.
- [ ] Establish deployed and independent real-model acceptance before a fresh
  ordinary-HTTP eleven-question journey; no unchanged paid resampling.

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

## Decision Log

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
The final full learning/scripts run passed 4,013 tests, 50 subtests and two
expected skips after both Codex review fixes. Toolchain, repository
harness, architecture baseline (131 existing / zero new violations), and the
all-file lefthook gate passed. Source frontend, formatter, pager and element
adapter files are unchanged from actual main.
An offline retained-checkpoint probe used one SDK request, zero provider calls
and 126,889 wire bytes within the unchanged 262,144-byte input limit after review
(126,832 before the bounds description changed). Test failures
from the private probe's missing limit argument and pending-input lookup were
retained and corrected without a provider request or old-session write.

The existing #3122 prompt-only experiment remains held; its original failures
and the 18.59-credit balanced failure are retained. This candidate contains no
#3122 prompt guidance. No browser, new deployment or real-model acceptance has
been performed for it; no offline test establishes full classroom acceptance.

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

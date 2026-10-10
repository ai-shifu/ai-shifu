# Keep natural-language text questions answerable

## Purpose / Big Picture

A lesson asking for the learner's own words must show an input box even when the
model omits a placeholder in either a typed tool call or narrated notation. Empty text must keep the original question pending,
without a model call, a fabricated answer or a memory write.

## Progress

- [x] 2026-10-10: Verify #3089 merged as c6f0a8bc9; archive its narrow counting
  plan, final CI and replied AI opinions. Natural compaction remains open.
- [x] 2026-10-10: User reports Submit-only controls in a production draft lesson.
  Read the exact course/lesson through the read-only account and matching Redis
  cache. Current retained questions have explicit hints; the screenshot's exact
  missing-hint generation is not retained and is not claimed reproduced.
- [x] 2026-10-10: Reproduce nine missing/blank-hint protocol failures and twelve
  blank-answer failures. Two real SDK saved-session regressions also fail before
  the correction. Explicitly named empty-valued options remain valid.
- [x] 2026-10-10: Add a localized presentation fallback for text-bearing controls;
  reject whitespace-only free-text values without trimming real answers.
- [x] 2026-10-10: 3,211 learning/profile/evaluator cases plus four subtests
  pass, with one expected skip; 633 engine/evaluator cases pass. Eight locales
  render real translated input hints. Existing authored-hint regressions pass.
- [x] 2026-10-10: Browser proof with the exact pinned markdown-flow-ui 0.2.32
  reproduces the old Submit-only control and verifies input/send callbacks for
  text, single-or-text and multi-or-text. Selection values survive mixed input.
  Developer-tool checks and all-files gates pass.
- [x] 2026-10-10: Open PR #3092 (c0d4a1550). Initial sim d5ca9dee6 is Ready;
  both API replicas match 54 runtime/resource hashes and independently pass two
  saved-session cases plus 72 localized text controls without provider or DB calls.
- [x] 2026-10-10: Adopt the narrated-control review finding: five missing-hint
  cases fail before correction; preserve authored spans and parsed choices/variables.
  Add ten empty-valued-option boundary cases. The actual browser/host filters blank
  input; the SDK explicitly distinguishes selected values from typed text.
  Expanded regression: 3,230 cases and four subtests pass, one expected skip;
  783 host/protocol/engine cases pass. Verify the narrated fallback in all locales.
- [ ] 2026-10-10: Publish the review correction and verify its sim rollout;
  record final deployment/CI evidence and review decisions on PR #3092.
- [ ] 2026-10-10: Reply to every AI opinion in its original discussion and record
  final CI. User merges manually; retain 1.0 and the natural-compaction backlog.

## Surprises & Discoveries

The Python parser accepts a bare free-text marker, but the frontend exposes text
input only with a nonempty hint. Its absence becomes a Submit-only control.
A nonempty list containing an empty string also passed the prior answer check.
The earlier authored-hint repair deliberately requires an exact script match;
it cannot repair every dynamic natural-language question and should retain that
identity boundary.

The read-only query initially assumed a preview_mode column that does not exist
in learn_agent_sessions. Inspect actual columns and repeat only the failed read;
no SQL writes or model calls were involved. Current records are evidence of the
course, not proof that a later cached run is the screenshot's original run.

## Decision Log

- Prioritize the new reported bug before another paid natural-compaction journey.
- Render a missing/blank hint through shared translations for all supported
  locales. Preserve explicit hints, typed semantics, prompts, options, variables
  and stored specs. Do not guess an authored question or add an answer choice.
- Reject blank free text before typed-interaction model execution. Preserve the
  exact nonblank text received by the engine, confirmations and options that
  intentionally store an empty value. The browser's existing submission helper
  trims/deduplicates values; this PR does not change that frontend contract.
- Keep narrated spans byte-for-byte when they already have a hint or only choices.
  For a missing hint, insert translated escaped text and require identical parsed
  options, variable, interaction type and multi-select semantics.
- Production diagnosis is read-only. Sim shares the China production database;
  use isolated sessions and new internal learners only, never reset user progress.

## Outcomes & Retrospective

Implementation, independent component proof and the initial sim checks pass;
the review correction and final CI are being completed on PR #3092. The exact screenshot run is
not retained; local reproduction establishes the missing-hint and blank-answer
contracts independently. Do not call this production-browser acceptance.

## Context and Orientation

legacy_protocol.py translates typed interactions into the existing MarkdownFlow
controls. engine/interaction.py validates normalized answers before the engine
resumes deferred tools. The authored-input normalizer already handles exact
script hints and must continue to do so. Eight shared backend learn translation
files own the generic input hint. No new frontend path or analytics event exists.

## Plan of Work

Keep the original production material private. Prove that missing hints remain
text inputs in the currently pinned component. Exercise a natural question across
Session serialization: blank values re-emit that same question without another
model call or mutation; a real answer resumes normally and is preserved exactly.
Run the relevant learning/profile/engine regressions and repository gates, open
one focused PR, deploy only its runtime changes to sim, and audit review replies.

## Concrete Steps

Use conda ai-shifu for backend work. Private evidence uses 700/600 permissions.
Push only GitHub origin, run developer-tool checks and all-files gates before
commits, rebuild knowledge indexes after staging plan moves, and keep the PR body
current. Do not merge automatically or modify production configuration.

## Validation and Acceptance

Require visible writable text controls for all text-bearing types with absent,
empty or whitespace-only hints; preserve explicit placeholder escaping, choice
values, multi-select semantics and localization. Blank answers must not advance
history, answers or memory. Reloaded pending sessions must accept the next real
answer, preserving whitespace as received at the engine boundary. Browser-side
trimming remains unchanged. Verify current runtime hashes and
relevant isolated checks on both sim replicas. Distinguish source/component
proof from inaccessible historical UI evidence.

## Idempotence and Recovery

Keep old learner evidence and completed sessions intact. Do not delete Redis,
change a course, fabricate pending history, repeat unchanged paid calls to seek a
pass, or overwrite retained failures. The generic fallback is presentation-only;
removing it restores previous rendering without a data migration.

## Interfaces and Dependencies

The existing interaction schema, endpoints, deferred tools, SSE events and
persistence formats remain. Shared i18n owns the fallback wording. No library
release, provider configuration, database schema or 1.0 removal is required.
Natural compaction and other milestone acceptance stay in the memory-quality
reference and workspace status plan.

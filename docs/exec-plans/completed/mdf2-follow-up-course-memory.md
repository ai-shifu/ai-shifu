# Read current course memory during MarkdownFlow follow-ups

## Purpose / Big Picture

A learner can explicitly store a course note without an author-defined variable.
Normal 2.0 teaching reads it, but follow-ups currently resolve only defined profile
keys and never render an independent memory snapshot. Make the already stored
current-course facts available in text, external-provider and Live context builders.
Do not write new memory from follow-ups in this increment.

## Progress

- [x] 2026-10-09T01:16:50Z: Four new real-storage/context regressions fail; legacy
  behavior and an explicitly empty snapshot already pass.
- [x] 2026-10-09T01:16:50Z: Opted 2.0 loads into the existing scoped course reader,
  including the actual text host's pre-resolved snapshot. Shared prompts include
  a bounded, boundary-encoded JSON memory block even with a custom ask prompt.
- [x] 2026-10-09T01:17:49Z: Full local regressions pass (4,799 tests, four subtests,
  eleven expected skips); repository gates pass. Baseline HTTP follow-up cannot
  recall a stored undeclared test code.
- [x] 2026-10-09T01:37:00Z: Reviewed candidate b03d27b7b passes 4,801 tests,
  four subtests and eleven expected skips. All eleven CI checks pass. Sim build
  433 / Drone 5224 and both deployments succeed; both replicas match 32 hashes.
  Three fresh learners recall their independent notes naturally; an update is
  recalled and deletion returns unknown in a fresh lesson context.
- [x] 2026-10-09T02:03:21Z: Final 83978dbec / sim 3130cfee2 passes shared-gateway
  privacy acceptance, 4,803 local tests / four subtests / eleven expected skips,
  all technical CI checks (full backend 10,781 passed / 23 skipped and eight
  contracts), three browser smokes, and fresh HTTP recall with no note in either
  replica log. Every AI opinion has an original-discussion reply; final CodeRabbit
  re-review is rate limited. User manually merged as 676d60528.
- [x] 2026-10-09T02:19:00Z: Main build 435 / Drone 5226 and all eight production
  deployments 2082-2089 succeed; all eight API replicas match 32 runtime hashes
  and remain on 1.0.

- [x] 2026-10-09T01:28:50Z: Review hardening: two logger-boundary tests fail before the fix;
  reviewed focused context/provider tests pass 88/88. Content logs are replaced by
  counts, and actual Dify outbound / Get Biji synthesis delivery is covered. Provider
  delivery limits and natural recall guidance are recorded; final sim is pending.

## Surprises & Discoveries

Review found legacy prompt/message logs exposing new notes. Two logger-boundary
regressions failed before replacing content logs with counts, including the shared
formatter. Initial deployed HTTP recalls an explicitly named key, but a natural
request to recall an earlier fact returned unknown despite the note being present
in the actual LLM messages. The memory instructions now explicitly cover facts
remembered in earlier lessons outside visible history; three independent fresh
HTTP learners now pass natural recall. A final deployed log audit found a second
exposure in the shared LLM gateway: raw messages, responses and provider parameters
were still printed. Two real gateway logger-boundary tests reproduce this in both
chat and invoke calls. Replace ordinary content/credential logs with model/count
metadata while preserving provider payloads, controlled traces and usage recording.

The text host supplies a resolved profile snapshot before invoking the shared
builder. Changing only the builder's fallback reader would leave real text requests
unfixed. Supplied snapshots, including empty ones, must remain authoritative and
must not trigger a second read. Live uses its own voice prompt and the shared loader.

## Decision Log

- Reuse load_memory(include_course_variables=True) and the environment-only runtime
  selector. Production 1.0 keeps its current prompt and profile behavior.
- Include only authorized current-course values plus registered system fields from
  the existing facade. No cross-course custom storage or broad elsewhere reader.
- Bound the additional JSON payload to 16,384 UTF-8 bytes after encoding. Whole
  values are selected in snapshot order; oversized values remain stored and unknown
  to this prompt. No truncation, retrieval tools or silent guess of omitted values.
- Treat stored values as untrusted current facts, never instructions or permission
  to save. Keep historical quotations distinct. Live observes a snapshot when its
  conversation is created; this does not hot-update an ongoing provider session.

## Outcomes & Retrospective

Reviewed learning/profile/shared-gateway/metering/billing acceptance passes: 4,801
tests and four subtests passed, with eleven expected skips. The deployed baseline
returned unknown for an independently stored test code on a fresh internal learner.
Functional sim acceptance passes natural recall, update and fresh-context deletion.
Final gateway privacy deployment and manual main release pass; new follow-up memory writes and
natural-course/long-term cost acceptance remain separate work.

## Context and Orientation

follow_up_context.py constructs text/provider/Live prompts. context_v2.py supplies
text's resolved memory; follow_up_memory.py renders its bounded JSON data. Existing
memory facade owns definition resolution, custom-course reads and deletion filtering.
See [follow-up context](../../references/follow-up-classroom-context.md).

## Plan of Work

Reproduce the missing undeclared note, fix both real text-host and shared fallback
loads, verify consumers and privacy boundaries, then repeat sim HTTP with a fresh
internal learner and independently scoped stored note.

## Concrete Steps

1. Use real profile storage with conflicting learners/courses and no variable definition.
2. Verify update/delete freshness, supplied empty snapshots, encoded keys/values and
   whole-value omission. Check actual host dispatch and both provider contexts.
3. Run learning/profile/shared-metering regressions and repository gates.
4. Open a focused PR, push sim, fingerprint both replicas and test real HTTP recall.
5. Read every AI review surface, reply to each opinion and await manual merge.

## Validation and Acceptance

A normal 2.0 follow-up sees the latest scoped note in LLM and provider context;
legacy 1.0 does not gain it. Other learners/courses and deleted values stay absent.
No additional model requests, memory writes or changes to history ordering occur.
The text host forwards a single resolved snapshot. Preview classification, voice
instructions and provider routing remain covered by existing regressions.

## Idempotence and Recovery

Only fresh dedicated internal sim learners may receive test notes. Sim shares the
CN production database; production probes remain read-only. Keep credentials and
raw transcripts private. Roll back this increment without changing stored memory.

## Interfaces and Dependencies

No schema, dependency, environment variable or public API changes. Reuse existing
memory and context contracts; only add an internal bounded rendering helper.

## Provider delivery boundary

The default LLM and Live builder consume this memory snapshot. Dify serializes the
shared provider messages into its outbound query, and Get Biji uses the contextual
LLM synthesis factory after retrieval. Existing Coze, Coze Workflow and Volc
adapters discard provider messages; their provider-only answers do not receive
course memory through this increment. Provider-specific context delivery remains
separate follow-up work, preserving the existing configured knowledge interfaces.
The builder supplying a message list is not proof that every adapter transmits it.

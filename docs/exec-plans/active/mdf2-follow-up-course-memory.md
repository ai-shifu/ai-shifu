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
- [ ] 2026-10-09T01:16:50Z: Finish regression/gate, deployment, actual HTTP recall
  and AI opinion reply acceptance. Await manual main merge.

## Surprises & Discoveries

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

Local learning/profile/shared-gateway/metering/billing acceptance passes: 4,799
tests and four subtests passed, with eleven expected skips. The deployed baseline
returned unknown for an independently stored test code on a fresh internal learner.
Final deployed validation is pending; new follow-up memory writes and
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

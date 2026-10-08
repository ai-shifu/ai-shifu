# Semantic summaries for older MarkdownFlow teaching

## Purpose / Big Picture

Older long teaching currently retains only its exact opening and ending in model
requests. Add a lossy semantic overview so the teacher can continue coherently,
with exact original evidence still available through `read_teaching`.

## Progress

- [x] 2026-10-08 18:08 CST: Inspected projection, gateway, persistence and rewind.
- [x] 2026-10-08 18:12 CST: Implemented bounded generation, session cache and fallback.
- [x] 2026-10-08 18:13 CST: 79 focused, 443 engine, 2,757 learning/profile tests (one skip, four subtests) and repository gates passed; durable cache roundtrip also verified.
- [x] 2026-10-08 18:14 CST: Opened PR #3049 and deployed sim build 404 / Drone 5195.
- [x] 2026-10-08 18:18 CST: Real sim course-model summary and continuation passed;
  reload made no extra request, exact reads and rewind cleanup passed.
- [x] 2026-10-08 18:20 CST: Added shared accounting/deadline corrections for three
  AI findings; 385 gateway/LLM regressions passed including seven accounting paths.
- [x] 2026-10-08 18:22 CST: Shared LLM, model gateway, metering, learning/profile
  regressions passed: 3,211 tests, one skip, four subtests; all repository gates passed.
- [x] 2026-10-08 18:26 CST: Pushed gateway fixes `b875ddcaa` and replied to all
  independent AI opinions in their original threads. Sim build 405 / Drone 5196
  and deployments 1970/1971 succeeded; both API replicas match ten runtime hashes.
  Real course-model summary/continuation, reload reuse, exact reads, rewind cleanup,
  gateway usage records and real HTTP read/listen/TTS completion passed.
- [ ] 2026-10-08 18:26 CST: Await the user's manual main merge and verify its
  post-merge deployment; production engine selection must remain unchanged.

## Surprises & Discoveries

- Review identified that early gateway closure skipped usage finalization and
  immediate connection retries skipped cancellation checks. Both paths require
  shared-gateway fixes and real accounting regressions before acceptance.

- The existing deterministic projection preserves message counts and tool pairs;
  checkpoints depend on that invariant. Semantic summaries must decorate the
  projection, never replace stored messages.
- Gateway streaming retries are shared. An optional retry deadline must coexist
  with learner disconnect cancellation; asyncio timeouts alone cannot interrupt
  a blocking synchronous provider read.

## Decision Log

- Summarize only already eligible assistant text, retaining two recent turns and
  all learner inputs. Each summary receives one complete original text, no memory,
  script, learner answers, tools or unrelated lesson content.
- At most one summary generation per engine turn. Consider the latest 64 eligible
  sources; cache successful summaries and empty failure markers in that session.
  Bind cache keys to prompt version, selected model, source position and digest.
- Accept sources up to 32 KiB of JSON-escaped UTF-8 and summaries up to 1024 bytes.
  Keep the exact opening, ending, reference and original character count. Larger
  sources and failed or invalid outputs retain deterministic excerpts.
- Use the shared gateway, billing and tracing with a separate generation name,
  a 40 KiB mapped input budget, 256 output tokens, an eight-second provider timeout
  and retry deadline. The deadline is cooperative between synchronous reads;
  provider socket timeout still bounds a blocked read. Cancellation propagates.
- Clear cached derivatives on rewind. They are not memory, authorization or a new
  instruction and never grant cross-course access. No database migration or new
  rollout switch is needed; only the existing 2.0 route enables this capability.

## Outcomes & Retrospective

Local and sim acceptance are complete for PR #3049. The final real-model run
summarized 4,576 source bytes to 669 bytes with one summary request, reused the
cache without another request and continued teaching. Both real summary calls
have successful shared gateway usage records. Real HTTP reading and listening
completed; on-demand TTS completed in 1.95 seconds. All three actionable AI
findings were fixed and replied to; the docstring percentage warning received
an explicit reasoned reply. Main remains a user-controlled merge.

Full memory quality/cost observations and human course feedback remain separate
milestone work. This does not complete the entire memory milestone.

## Context and Orientation

`src/api/flaskr/service/learn/agent/engine/teaching_history.py` projects old text
without changing evidence. `engine/session.py` serializes lesson state;
`rewind.py` restores checkpoints. `lesson_entry.py` binds the current course's
model, gateway, preview billing and engine options.

## Plan of Work

Add a portable summary callback and bounded request-only decoration. Persist a
small derivative cache with backward-compatible defaults. Build a host callback
using GatewayModel and a dedicated prompt. Enable it alongside teaching history
compaction and clear derivatives during rewind. Cover failure, invalid output,
cache reuse, recent answers, exact reads and gateway budgets.

## Concrete Steps

Use the `ai-shifu` conda environment. Run focused teaching/summary/gateway/rewind
checks, then the engine and learning/profile suites. Run the developer tool check,
regenerate knowledge indexes after staging Markdown, and run all pre-commit gates.
Commit with the repository identity, push only GitHub origin and open a main PR.
Merge the feature into sim after local validation; never automatically merge main.

## Validation and Acceptance

A mock gateway observes a bounded isolated summary request and a teaching request
containing its semantic overview. Reload reuses cached results without another
summary call. Rewind discards future derivatives. Full original text reconstructs
through read_teaching; messages, answers, tools and IDs remain unchanged on disk.
Malformed/oversized/error responses preserve the existing excerpt and lesson flow.
Real sim validation checks the selected model's summary and teaching continuation;
production routing stays on 1.0. Reply to every independent AI review opinion in
its original thread before reporting completion.

## Idempotence and Recovery

Legacy sessions default to an empty cache. Only current eligible source references
and the current prompt/model policy may be used. The cache has at most 64 entries;
failures are cached to prevent repeated paid attempts for the same source. A rewind
or policy change permits regeneration. Removing the option restores deterministic
projection with intact historical evidence.

## Interfaces and Dependencies

Use pydantic-ai Model/Agent and the project's existing GatewayModel. No new package,
provider SDK, store, global memory field, migration or SSE event is introduced.

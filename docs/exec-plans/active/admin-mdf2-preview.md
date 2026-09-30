# Use the 2.0 lesson runtime in teacher debug preview

## Purpose / Big Picture

Teachers debugging an allowlisted course on the simulation deployment should see the same 2.0 teaching behavior as learners. The editor sends its current draft script, and debug runs remain isolated from learner progress and durable memory.

## Progress

- [x] 2026-09-30 15:33 CST: Mapped the editor preview request and the 2.0 lesson runtime.
- [x] 2026-09-30 16:00 CST: Reused the 2.0 lesson runner with an isolated, expiring debug session.
- [x] 2026-09-30 16:00 CST: Stopped the editor's 1.0 block continuation for a 2.0 response.
- [x] 2026-09-30 16:00 CST: Covered routing, isolation, input continuation, session expiry, analytics, and existing preview compatibility.
- [ ] 2026-09-30 16:00 CST: Review the pull request and verify a real allowlisted lesson in sim after deployment.

## Surprises & Discoveries

- The editor calls a separate, block-oriented preview endpoint. Its `block_index` is a 1.0 control, while the 2.0 runtime advances an entire lesson until a question or completion.
- Existing 2.0 `preview_mode` isolates learner progress, but still saves a lesson session and durable memory. Editor debug therefore needs its own expiring session and must suppress durable memory writes.

## Decision Log

- 2026-09-30: Route only allowlisted courses to 2.0 in the deployment serving the request. Reuse `agent_lesson_events`, `run_agent_lesson`, and `PreviewElementRunAdapter`; do not build a second turn translator.
- 2026-09-30: Use a per-debug-run expiring session so editor resets and draft changes cannot contaminate learner or teacher lesson sessions.

### Creator lesson preview engine event

- Business question: Of teacher debug runs that received an engine response, how many used 2.0 versus 1.0, and for which allowlisted course and lesson?
- Metric definition: Count distinct `creator_lesson_preview_engine_started` events by `engine` per day, optionally grouping by course and lesson. The existing `creator_lesson_preview_click` is an intent signal; aggregate click-to-start ratios are approximate because clicks and starts have no shared attempt identifier.
- Actor and surface: Signed-in teachers and collaborators in the lesson editor. Guests and learner preview are excluded.
- Trigger: The first valid engine marker received for a fresh editor debug session, before content arrives. One event per editor debug session; block continuations and answer requests do not repeat it. A new reset creates a new session.
- Payload: `engine` is `v1` or `v2`; `shifu_bid` and `outline_bid` are stable machine IDs needed to inspect rollout by course and lesson. No script, answer, title, URL, user identity, or model output is sent.
- Consumers: Rollout review of 2.0 teacher debug usage. No correctness or billing decision uses this best-effort signal.
- Compatibility: New event, no historical backfill. The existing click event keeps its meaning.
- Verification: Frontend tests cover the exact event, deduplication, payload, and tracking failure isolation. Backend route tests cover both engine markers.

## Outcomes & Retrospective

The editor now sends a run ID and current draft to its existing preview endpoint. Allowlisted courses use the shared agent lesson runner and in-memory element adapter; debug sessions expire in Redis and do not write lesson rows or durable memory. Other courses continue through the 1.0 preview. Backend learn tests passed (2,106 passed, one skipped with a valid Redis locale). Focused frontend tests passed. Sim deployment and live editor acceptance remain open.

## Context and Orientation

The editor hook is `src/web/src/components/lesson-preview/usePreviewChat.tsx`. It calls `POST /api/learn/shifu/<shifu_bid>/preview/<outline_bid>` in `src/api/flaskr/service/learn/routes.py`. That endpoint currently invokes `RunScriptPreviewContextV2`. The learner's 2.0 path is `agent_lesson_events` in `src/api/flaskr/service/learn/agent/lesson_entry.py`, using `run_agent_lesson` and the element adapter.

## Plan of Work

Add a preview-only session store behind the existing runner's load/save seam. Give the runner the editor's draft script and preview variables. Select it inside the existing preview route only when the course is allowlisted. Tell the editor which engine answered and prevent its block-by-block continuation for 2.0.

## Concrete Steps

1. Add an expiring debug session store and an injectable session persistence seam to the existing runner.
2. Route allowlisted editor previews through the lesson runner and existing element adapter.
3. Add a response marker consumed by the editor hook; preserve the existing 1.0 behavior for other courses.
4. Run focused backend and frontend tests, then repository checks, and open a normal pull request.

## Validation and Acceptance

- An allowlisted course uses 2.0 on the same deployment; a course outside the list keeps 1.0.
- A fresh editor debug run starts from the current draft; an answer resumes its own session.
- The debug run writes no learner progress, learner session, or durable profile memory.
- The editor does not request the next 1.0 block after a 2.0 stream ends.

## Idempotence and Recovery

Debug sessions expire automatically. A fresh debug run uses a new session identifier. Removing a course from the deployment allowlist returns the editor to the existing 1.0 path without data migration.

## Interfaces and Dependencies

The API keeps its existing preview endpoint and element SSE messages, adding a small engine marker. The editor sends an opaque debug session identifier. The server uses the existing Redis cache, gateway model, runner, and preview element adapter.

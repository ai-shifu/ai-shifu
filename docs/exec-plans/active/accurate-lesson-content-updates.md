# Accurate lesson content updates without schema changes

## Purpose / Big Picture

Replace timestamp-based retake recommendations with exact original-body
comparison for formal and preview 2.0 sessions. Implement the contract in
[Lesson Content Update Recommendations](../../product-specs/lesson-content-updates.md)
without database schema changes or full session transfer on directory reads.

## Progress

- [x] 2026-10-11 CST: Reviewed storage, consumers, reset paths and performance
  tradeoffs; user approved exact comparison and conservative legacy handling.
- [x] 2026-10-11 CST: Fetched origin and created the task branch from current main.
- [x] Implement SQL/in-memory predicates and API integration.
- [x] Isolate formal/preview history and retake lifecycle.
- [x] Update frontend authoritative flag and documented retake analytics.
- [x] Run focused regression, MySQL/SQLite parity and isolated performance checks.
- [x] Run repository gates and prepare the reviewed change for delivery.
- [ ] Verify deployment order and learner/preview behavior after release.

## Surprises & Discoveries

- Session LONGTEXT includes full messages and original body. SQL projection
  reduces network/application memory but does not eliminate JSON parsing.
- Formal records do not already load agent sessions; preview history does.
- Existing directory preview status loads complete sessions, and formal reset
  retires both scopes. A cleared draft can fall back to formal history/reset.
- The configured development database lacks the 2.0 session table. Performance
  and MySQL correctness checks must use an isolated temporary database, never
  migrate or populate that development database for this task.
- Repeated guarded JSON extraction took about 4.83 seconds for 100 one-MiB
  documents on local MySQL. Extracting only the source and message existence
  through `JSON_TABLE` reduced this to about 0.60 seconds in the final fixture.
  This is still slower than a local full-history transfer, but avoids about
  108 MB of result values and 111 MB of Python allocation. See the
  [performance report](../../references/lesson-content-update-performance.md).
- The optimizer initially preferred a user index. A MySQL-only hint now
  selects the existing unique active-key index; EXPLAIN confirms a range scan
  even with 1,000 same-user retired sessions and 1,000 other-user sessions.
- Source-checkout frontend dependencies were older than the lockfile. An
  isolated `npm ci` restored the exact dependencies. Both pristine main
  `f1e9bf190` and this branch still report the same two TypeScript errors in
  `src/web/src/app/admin/operations/users/[user_bid]/page.test.tsx` at lines
  964 and 1026; neither file nor the dependency manifests were changed.

## Decision Log

- Reuse recognized 2.0 snapshots; missing/legacy baselines do not show notices.
- Normalize CRLF and CR only. Equal-length changes remain significant.
- Preserve the directory boolean contract. Use one indexed batch projection
  and binary SQL comparison rather than transferring entire session documents.
- Use the records boolean as the frontend authority. Add the two privacy-safe
  retake events documented in the product contract before implementing them.
- No schema changes, historical backfill, persisted digest, cache or engine
  routing changes are part of this implementation.
- Use MySQL `JSON_TABLE` for known servers >= 8.0.21; older/unknown versions
  and MariaDB retain guarded extraction. Both paths return scalar states only.
- Preview history/reset classification uses the current structure's physical
  row. A cleared draft with any 2.0 session history remains isolated after
  reset; genuinely scriptless legacy lessons retain existing behavior.
- Engine execution and its existing scriptless fallback are unchanged. The
  cleared-body regression covers history, directory status and reset domains,
  not a redesign of subsequent 1.0 execution or progress storage.

## Outcomes & Retrospective

Implementation is complete. Backend learn/API/golden regression: 3,169 passed,
93 skipped. Frontend: 199 tests across nine suites passed with exact locked
dependencies. MySQL/SQLite synthetic semantic checks: 100 passed. Architecture,
unit-of-work, tooling doctor and all-files pre-commit checks passed. Type-check
remains limited by the two independently reproduced main-branch test errors.

Performance measurements cover real comparison SQL and a synthetic Flask
comparison endpoint, not the full authenticated production directory/history
endpoints. The local server was MySQL 26.7.0; actual deployment-target MySQL 8.0
and production latency/concurrency remain release-environment verification.
No schema was migrated and no deployment is claimed.

## Context and Orientation

`learn_funcs.py` owns directory status and reset; `listen_elements.py` routes
history; `agent/preview_history.py` owns preview presentation. Original body is
`LearnAgentSession.session_data.script.script`, and `active_key_for` separates
formal learning from preview. The frontend history refresh currently has a
separate draft-time comparison; both paths will use one backend contract.

## Plan of Work

Implement a focused comparison module and parity tests; integrate eligible
directory/records reads and scoped lifecycle; update the frontend and events;
benchmark independent fixtures and complete repository gates.

## Concrete Steps

Use the existing Python environment at the source checkout, Ruff 0.16.5 in an
isolated temporary tool environment, and exact-lock frontend dependencies
through an ignored local symlink. Validation commands:

```bash
cd src/api
python -m pytest tests/service/learn/ tests/test_learn_api.py tests/golden/ -q
python scripts/benchmark_lesson_content_updates.py --mysql-env .env --iterations 7
```

Frontend targeted Jest suites cover the history hook, notice UI and producer,
analytics lifecycle/transport, page, mobile header and records API. Run
`npm run type-check -- --incremental false` and `npm run lint` as well.
Regenerate knowledge indexes after docs settle. Run dev-tools doctor, harness,
architecture, UOW ratchet and all-files pre-commit checks before committing.

## Validation and Acceptance

Exact SQL/Python agreement on same-length edits, Unicode/case/whitespace,
newlines, reverts and malformed/unknown documents. Cover in-progress/completed,
reset/unstarted, formal/preview isolation, cleared bodies, late frontend
responses and analytics failures. Benchmark 10/100 synthetic candidates with
different body/session sizes, recording statement count, execution plans,
projected bytes, Python peak allocation and p50/p95 query/API timings. Clearly
distinguish synthetic local measurements from production performance.

## Idempotence and Recovery

No stored learning baseline is rewritten. Temporary benchmark databases have
unique names and are removed after use. Rollback is code-only; legacy and
missing snapshots remain untouched. Release backend before frontend.

## Interfaces and Dependencies

Add `has_content_update_for_current_user` to lesson-record DTOs while preserving
the outline field. SQL and Python consume the existing session schema and
active-session index. No dependency version changes are required.

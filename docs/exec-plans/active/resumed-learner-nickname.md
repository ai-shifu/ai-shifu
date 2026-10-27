# Refresh Nicknames in Existing Agent Lessons

## Purpose / Big Picture

Let learners who resume an existing lesson receive their current canonical
nickname, or the localized presentation fallback after clearing it. Follow up
the two compatibility findings deferred from PR #3024 without restarting lessons.

## Progress

- [x] 2026-10-07 08:15 UTC: Inspected host, engine, profile and session storage.
- [x] 2026-10-07 08:16 UTC: Added actual-model/SQLite regressions and host repair.
- [x] 2026-10-07 08:21 UTC: Focused regressions passed (11); learning-service suite
      passed (2,236 tests, one skip, four subtests). Repository gates passed after
      regenerating the knowledge indexes. Disabling host repair makes six of the
      eleven regressions fail, including actual closing rendering.
- [x] 2026-10-07 08:29 UTC: Published PR #3025; Devin and CodeRabbit reported no
      actionable code findings. Sim `12ee27bf7` is deployed with API 2/2 and web
      1/1 Ready. Forty-eight deployed host probes and a new temporary learner's
      read/audio/listen completion passed, with the canonical profile unchanged.
- [ ] 2026-10-07 08:29 UTC: User-owned main merge and post-merge source check;
      keep this plan active until that external acceptance is complete. Final CI
      and review replies are tracked on PR #3025 and in the workspace record.

## Surprises & Discoveries

Refreshing `user_memory` alone does not refresh the first rendered model input.
Session memory also overrides canonical profile memory. Deferred tool calls must
keep their matching results; adding arbitrary messages between them is unsafe.

## Decision Log

- Keep the engine's general memory precedence intact; reconcile only the canonical
  nickname in the host, excluding debug sessions.
- Reconstruct recognized initial host sections using the original injected memory.
  Do not replace arbitrary name strings or rewrite learner/assistant/tool history.
- Retain the collected-variable guard while a nickname question awaits its answer.
- Parse memory as JSON so delimiter text inside learner values stays ordinary data.

## Outcomes & Retrospective

Implementation, local regressions and sim validation are complete. Both automated
code reviewers reported no findings against runtime commit `9df886e44`.
The optional CodeRabbit docstring percentage warning does not alter the tested
behavior; entry points and parent test contracts document their purpose. Final CI
is tracked on PR #3025; main merge remains manual. Deployed runtime files match
the local tested bytes. The workspace record is
`task/docs/mdf2-resumed-nickname-2026-10-07.md` in the sibling task repository.
Human teaching acceptance and broader memory
admission/budget policy remain tracked in the workspace MDF 2.0 status document.

## Context and Orientation

`agent/run_agent.py::_load_or_start` loads canonical memory before constructing
the resumed session. `agent/nickname.py` repairs the first host user prompt and
removes the stale session nickname. `session_store.py` persists this with the
existing turn transaction. Engine variable substitution still protects fences,
collected variables and unknown keys.

## Plan of Work

Seed sessions matching the pre-fix shape in the real session store. Inspect the
actual resumed FunctionModel request, then test pending answers and failed saves.
Run the learning suite and repository gate before publication. Integrate only
the tested feature into sim; main remains a manual merge.

## Concrete Steps

Use the configured conda `ai-shifu` environment. From `src/api`, run
`python -m pytest tests/service/learn/agent/test_resumed_nickname.py -q`, then
`python -m pytest tests/service/learn/ -q`. From the root run
`python scripts/check_dev_tools.py` and `lefthook run pre-commit --all-files`.

## Validation and Acceptance

Old blank prompts receive the fallback; a changed or cleared canonical nickname
beats an old collected answer on resume. Fresh pending answers still win their
own turn. Preserve other memory, IDs, history, pending tool results and unknown
or fenced text. Repeated repairs are idempotent. A failed save retains the exact
previous session row. Inspect final CI, all AI review surfaces and deployed sim.

## Idempotence and Recovery

Only successful turn persistence stores repairs. Unrecognized prompt shapes and
unmatched brief sections remain untouched. No migration or eager database rewrite
is introduced; rollback uses the existing transaction and deployment path.

## Interfaces and Dependencies

Use the stable profile API for `SYS_USER_NICKNAME`, existing engine substitution
helpers and pydantic-ai message dataclasses. No schema, provider, SSE, frontend,
global memory precedence or production configuration changes.

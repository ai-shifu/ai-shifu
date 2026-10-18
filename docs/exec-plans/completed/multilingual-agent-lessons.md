# Respect the course output language in agent lessons

## Purpose / Big Picture

Honor the existing multilingual course setting in the 2.0 host, including resumed
and retaken lessons. All newly generated teaching, HTML labels and interaction
display text must follow the current requested language when enabled. Disabled
courses retain the author's language. Historical teaching and machine values stay
unchanged.

## Progress

- [x] 2026-10-18 CST: Reproduced English requests producing Chinese using a local
  published-course copy and the production model through the shared gateway.
- [x] Wire the draft/published setting into each host turn and add regression tests.
- [x] Verify Chinese, English and French starts, persisted continuation and retakes
  against the real course content and model in an isolated local database.
- [x] Run repository gates and create open [PR #3145](https://github.com/ai-shifu/ai-shifu/pull/3145).

## Surprises & Discoveries

Publication and session retirement work. The agent host never reads the language
setting. Its generic learner-language wording is insufficient: an English profile
still produced Chinese while a French profile happened to produce French.
A system-only policy still produced Chinese during real English acceptance. The
engine therefore projects its native current-language configuration beside the
latest model input as well as in system instructions. This projected context is
removed before persistence; it never becomes a learner message or stale preference.

## Decision Log

- Resolve the request locale in the host and pass native `Engine.output_language`
  configuration; never edit the durable profile to select a course language.
- Keep policy and per-model-request context projection inside the 2.0 engine, using
  its existing SDK history capability, independently of the gateway or 1.0 runtime.
- Use existing locale resolution. Preserve
  verbatim authored spans, code, identifiers, option values and element formatting.
- Editor debug may explicitly select a language through its preview variables;
  normal lessons prefer request language over the saved profile fallback.
- Test live generations against a local course copy; production remains read-only.

## Outcomes & Retrospective

Native engine configuration and real-model acceptance passed on 2026-10-18.
Using a private published-course snapshot in local SQLite and the production
DeepSeek model through the shared gateway, Chinese, English and French each passed
start, saved continuation and retake (9 generations). A second run passed Chinese
start, English continuation, French continuation, English retake and disabled-course
French request producing the Chinese source language (5 generations). Inspecting
the generated prose, HTML text and pending controls confirmed the expected language;
translated options retained authored submission values. Original answers/history
and profile language remained intact. These checks cover the first lesson and its
initial interactions, not every lesson or deployed browser behavior.

Offline learning, engine, evaluation-script and LLM tests: 4,149 passed, 1 skipped,
4 subtests passed. The frontend study request tests also passed (7 tests). Developer tooling and all repository pre-commit gates passed. PR #3145 is open
for review; remote CI was running when this plan was completed. No production
deployment or data write occurred. Private course material and raw model
inputs remain outside the repository; failed experiments are retained separately.

## Context and Orientation

`agent/lesson_entry.py` reads draft/published configuration, creates an engine and
calls `run_agent_lesson`. `run_agent.py` reloads memory and restores or creates a
session. The engine recomposes system instructions on each model request. Legacy
output-language names are resolved by `common/i18n_utils.py`.

## Plan of Work

Pass the setting through the resolver and runner. Resolve a supported runtime
language before session creation, project its variables only in memory, and set native engine configuration specifying the generated display language and
stable submission values. Project current configuration at every model call, remove
only engine-marked context, and preserve original conversation and tool pairing. Add focused host/SDK tests and run the existing learning suite. Exercise
real persisted first questions and answers, language changes and retakes.

## Concrete Steps

Use the conda `ai-shifu` environment for pytest and repository Python gates. Store
private course snapshots and live outputs outside this repository. Run
`python scripts/check_dev_tools.py` and `lefthook run pre-commit --all-files` before
committing. Push only to GitHub origin and open a ready-for-review PR.

## Validation and Acceptance

Offline coverage must observe the real SDK input for the current language across
new/restored sessions, request/profile mismatch, disabled courses, editor debug,
draft classroom and read/listen paths. Assert unchanged profiles, answers and
authored machine values. Live acceptance must cover Chinese, English and French
openings, continuation from saved questions and retakes with the same course.

## Idempotence and Recovery

No migration or production write is required. Restart local acceptance with a new
test identity only when diagnosing a failure; retain failed outputs separately.
Keep the existing host session retirement and write-race guards.

## Interfaces and Dependencies

The private lesson resolver gains the multilingual setting. Its destructuring
consumers and test doubles must change together. `Engine.output_language` accepts a target language, an empty string for authored
language, or `None` for existing portable defaults. No external package, frontend
payload, SSE event or formatter contract changes are needed.

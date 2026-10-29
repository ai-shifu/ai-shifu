# Reuse the 1.0 formatter for every 2.0 lesson mode

## Purpose / Big Picture

MarkdownFlow 2.0 lessons must produce the same typed elements as 1.0 so the
existing reading, listening, and classroom frontends can display HTML and other
visuals without changes. The same contract must survive element persistence and
history replay.

## Progress

- [x] 2026-10-14 11:56 CST: Compared the 1.0 formatter, 2.0 runner, and frontend mode projections.
- [x] 2026-10-14 12:00 CST: Route every content path through the shared streaming formatter.
- [x] 2026-10-14 12:04 CST: Verified formatter parity, element persistence, and learning regressions (3633 passed, 93 skipped).
- [x] 2026-10-14 12:04 CST: Passed the toolchain doctor, repository harness, architecture checks, and all-file lefthook gate.
- [x] 2026-10-14 12:26 CST: Fixed review findings for separated HTML attachments and question prompts after unfinished visuals; preserved ordinary prose history/audio grouping.
- [x] 2026-10-14 12:26 CST: Verified the updated learning suite (3678 passed, 93 skipped), actual element/history regressions, and all-file lefthook gate.
- [x] 2026-10-14 12:04 CST: Review the ready pull request and verify a real lesson after deployment. Closed at archival on 2026-10-29: #3134 is merged into main and deployed with it, so this review, merge or rollout step no longer applies.

## Surprises & Discoveries

- Only listening currently creates `LessonPager`; reading and classroom receive
  untyped fallback text containing HTML, which classroom then filters out.
- Interaction prompts bypass classification and are forcibly tagged as text.
- The pager drops separator-shaped lines even inside HTML or code and adjusts
  element numbers after classification. This can conflict with the formatter's
  script/style attachment to the preceding HTML element.
- The shared adapter treated returned HTML numbers as interrupted slots and
  isolated style/script/link attachments from their original card.
- Formatter flush does not reset unfinished visual syntax. Questions need a
  fresh classifier after visuals, while consecutive prose must keep its element
  grouping to preserve classroom history and answer anchors.

## Decision Log

- 2026-10-14: Use `markdown_flow.formatter.stream.StreamFormatter` for every
  content path and preserve its content, type, and number. Remove the custom
  separator filtering and renumbering so 2.0 does not define a competing grammar.
- 2026-10-14: Keep TTS conditional on listening, independently of classification.
  Reuse the existing element adapter, persistence, and frontend without changing
  their public contracts or adding dependencies.
- 2026-10-14: Reuse the original HTML slot for returned HTML numbers, retaining
  interrupted-slot behavior for other types. Restart the question formatter
  after visuals with a unique number offset; preserve ordinary prose grouping
  and deduplicate questions only against formatted prose.

## Outcomes & Retrospective

All new lesson output now uses the pinned 1.0 streaming formatter in every
learning mode, including rich interaction prompts. The learning suite passed
with 3678 tests and 93 skips; 52 host/adapter storage/history cases cover visual
content, separated attachments, and questions after unfinished visuals. One
earlier run hit a Live readiness query-count assertion; its eight tests passed
in isolation and the final full suite passed without Live code changes.
Repository gates passed. Existing
saved fallback-text records are not rewritten. PR review and live deployment
acceptance remain external follow-up; offline tests do not establish a rollout.

## Context and Orientation

`src/api/flaskr/service/learn/agent/run_agent.py` translates engine content and
interactions into `RunMarkdownFlowDTO` events. `agent/pagination.py` wraps the
1.0 streaming formatter. The DTO's private formatted parts reach
`ListenElementRunAdapter`, which creates and persists the existing element SSE
contract. Classroom filters text; listening separates visual and spoken elements.

## Plan of Work

Create the formatter in every lesson run. Format interaction prompts through the
same instance and flush before emitting their controls. Keep partial tags and
code fences buffered across tool events. Forward formatter parts without
filtering or rewriting them. Cover both listening and non-listening
runs, including arbitrary stream chunk boundaries and saved element readback.

## Concrete Steps

1. Update the pager and all content exits in the agent runner.
2. Replace the regression that requires unformatted reading output with shared
   formatter assertions and add real element adapter coverage.
3. Run focused tests, the learning suite, toolchain doctor, and repository gates.
4. Commit, push, and create a ready PR; do not merge it.

## Validation and Acceptance

- HTML, SVG, images, code, tables, and other supported formats carry the same
  type and number as the 1.0 streaming formatter in every learning mode.
- Script/style append pieces keep the formatter's original HTML association.
- Separated style/script/link attachments update the original HTML element in
  the stream and stored history; non-HTML interrupted slots retain their order.
- Separator-shaped content remains intact, including inside HTML and code.
- Interaction prompts are classified and arrive before their controls.
- Questions after unfinished HTML/SVG/code have independent text and audio,
  including when the visual already contains a copy of the question. Ordinary
  prose grouping and classroom rewind anchors remain compatible.
- Listening synthesizes only the existing speakable text; non-listening never
  creates a TTS processor.
- Final saved elements retain visual types and renderability on readback.
- Relevant regression suites and repository checks pass.

## Idempotence and Recovery

No migrations or dependency updates are required. Reverting this task restores
the previous runner and formatter adapter. Existing saved elements are not
rewritten; restarting a lesson generates newly classified elements.

## Interfaces and Dependencies

Use the pinned MarkdownFlow package, existing DTO formatted parts, existing
element adapter, and existing TTS binding. No frontend, engine, or external
protocol change is required.

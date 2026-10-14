# Restore classroom visual pages

## Purpose / Big Picture

Restore visual cards in classroom mode for MDF 2.0 lessons, including content
already generated in reading mode. Keep narration off the classroom screen and
keep classroom delivery independent from speech generation.

## Progress

- [x] 2026-10-14 CST: Synchronize with main ca75a292c and create the focused
      sunner/fix-classroom-mode branch in the existing worktree.
- [x] 2026-10-14 CST: Trace classroom requests through the frontend projection
      and MDF 2.0 host. Confirm classroom sends listen=false, while LessonPager
      is constructed only for listen=true. Recent production history contains
      whole text elements with embedded visual cards, consistent with this path.
- [x] 2026-10-14 CST: Confirm the reported symptom is absent content across
      classroom pages, including HTML that is no longer emitted separately.
- [x] 2026-10-14 CST: Add regressions for classroom delivery and saved mixed
      content. Backend delivery cases fail before correction.
- [x] 2026-10-14 CST: Separate classroom visual pagination from audio generation and restore
      visual-only projection of existing mixed content using the shared parser.
- [x] 2026-10-14 CST: Pass 1,765 backend cases, focused frontend suites,
      type checking, lint without errors, harness and boundary checks. An
      independent review verifies mode propagation, parser order and IDs.
- [ ] Deploy the reviewed candidate and verify real-browser classroom behavior.
      No main merge or production deployment is part of this repair task.

## Surprises & Discoveries

- Classroom uses the shared slide renderer but intentionally suppresses text
  narration and audio. Changing its filter to show all text would change its
  intended presentation rather than restore separate visual cards.
- A future-generation-only fix leaves existing read-mode records and content
  generated before a read-to-classroom switch invisible. Compatibility must
  therefore operate on saved/current canonical content without rewriting history.
- The existing source checkout has a usable Python 3.11 environment. Its web
  dependency installation is older than this branch's pinned package; install
  this worktree's lockfile before verifying package-dependent frontend behavior.
- The shared renderer parser's default path can lose HTML preceding a code
  fence. Its existing streaming scan preserves mixed source order; compatibility
  uses that path with prose excluded, with actual pinned-parser regressions.

## Decision Log

- 2026-10-14: Reuse LessonPager for new classroom turns, while retaining the
  existing listen-only voice gate. Pass the already-normalized learning_mode
  through lesson_entry to run_agent_lesson.
- 2026-10-14: Reuse the frontend's existing MarkdownFlow content segmentation
  for mixed text compatibility. Preserve canonical content, interaction and
  generated-block identities. Extract only recognized visual pieces.
- 2026-10-14: This restores the existing classroom path and its mode-selection
  analytics; it introduces no new action or analytics schema.

## Outcomes & Retrospective

The candidate restores newly generated classroom pages and existing mixed-text
visuals without modifying learner history or starting speech. Deterministic
regressions, type/lint checks and independent review establish the repaired code
contract. Publication is through a ready task-branch PR. Live container readiness
is infrastructure evidence only; repaired production behavior remains unverified.

## Context and Orientation

The learner uses learning_mode=read|listen|classroom. Classroom shares the slide
renderer with listening but removes narration and audio. The relevant frontend
projection is src/web/src/app/c/[[...id]]/Components/ChatUi/chatUiModeProjection.ts.
The backend mode enters src/api/flaskr/service/learn/agent/lesson_entry.py and
delivery occurs in run_agent.py. pagination.py wraps the same StreamFormatter
used by legacy lessons to identify separate visual and text elements.

## Plan of Work

First prove the absent visual-element contract with deterministic host tests.
Then pass classroom mode through the host and paginate without constructing a
LessonVoice. In parallel, project recognized visual segments from mixed fallback
text for classroom only, with stable identities and no canonical-state mutation.
Verify streamed and saved content, reading/listening preservation, interactions
and audio exclusion before preparing a reviewable pull request.

## Concrete Steps

1. Run focused backend lesson-entry, host and pagination tests with the existing
   Python environment; retain failure evidence before the fix.
2. Install src/web dependencies from package-lock.json using npm ci.
3. Run classroom projection and slide-renderer tests, then frontend type and
   lint checks for the changed scope.
4. Regenerate repository knowledge indexes, run harness/boundary checks and
   python scripts/check_dev_tools.py, then the required all-files hook gate.
5. Review the final diff, commit with Changed/Benefit sections, push the task
   branch and open a ready PR. Attach the PR to this chat. Never merge main.

## Validation and Acceptance

- New classroom output containing narration and multiple HTML cards emits
  separately typed/renderable visual elements in order, without TTS calls.
- Existing unsegmented mixed content projects only its visual pieces in order,
  retaining interaction values, stable navigation and block ownership.
- Plain narration remains hidden. Audio remains excluded. Reading and listening
  keep their current delivery behavior and existing tests stay green.
- Deterministic tests establish the code contract. Production availability and
  real browser behavior require post-deployment verification and are not implied
  by tests or a successful build.

## Idempotence and Recovery

All repairs are confined to the task branch. Compatibility is a read-only view
over existing content; no migration, session reset or learner-history rewrite is
required. Revert the focused commits to restore previous behavior.

## Interfaces and Dependencies

Use the existing normalized learning_mode and listen flags, LessonPager,
MarkdownFlow parser and ChatContentItem projection. Do not alter SSE event names,
stored records, speech capability, dependencies or analytics contracts.

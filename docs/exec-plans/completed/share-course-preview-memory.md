# Share course memory across preview and learning

## Purpose / Big Picture

When a teacher opens a course draft in the ordinary learner preview, use the
same persistent memory rules as when that account learns the published course.
The preview still runs the draft lesson and keeps its existing access, progress,
billing, and reset behavior. The editor's debug simulator remains isolated.

## Progress

- [x] 2026-11-08 18:24 CST: Confirmed that in-lesson answers already share
      memory; identified preview-only exclusions in follow-up and the user menu.
- [x] 2026-11-08 18:35 CST: Shared follow-up memory admission and persistence, while
      rejecting writes from retired preview sessions.
- [x] 2026-11-08 18:35 CST: Exposed and verified the existing course memory manager in
      preview, including analytics.
- [x] 2026-11-08 18:35 CST: Verified backend and frontend behavior, types, and repository checks.

## Surprises & Discoveries

- Course memory is keyed by account and course, rather than by script version.
  Preview can already overwrite a same-key answer, and values introduced by a
  draft can outlive that draft. Legacy account field bindings can affect the
  same user's experience in other courses.
- At the time of this change, preview resets retired an independent session.
  The [shared-learning plan](shared-course-version-learning.md) later replaced
  that behavior with a reset of the shared draft and published attempt. Course
  memory persists across reset and can be deleted from the course memory manager.
- The proposed change to simulated system answers in PR #3365 must be reconciled
  with the shared-memory contract if both changes land.

## Decision Log

- Share the existing admission, persistence, and deletion behavior. Continue
  selecting the script and therefore its key declarations by course version.
- Keep the existing preview session lifecycle and check it before committing a
  streamed follow-up's memory updates. Do not hold a database lock while the
  model answers.
- Reuse the learner memory manager with the same copy and behavior. Keep
  preview usage distinguishable from learner adoption in analytics.

## Outcomes & Retrospective

Ordinary preview now stages admitted follow-up writes for the same account and
course as published learning, without creating a preview session. A retired
preview attempt cannot commit new memory. The course menu reuses the same
memory manager, with separate analytics attribution and identical copy.

Local tests exercised draft and published write rules, same-key replacement,
reset and deletion protection, account and course boundaries, and dialog
behavior. This change does not migrate or combine classroom history or progress.

## Context and Orientation

The backend follow-up path is in `src/api/flaskr/service/learn/ask/`.
Ordinary preview and its reset behavior live in the learning service, not in
the editor debug simulator. The frontend course menu is
`src/web/src/components/navigation/MainMenuModal.tsx`; the persistent memory
contract is documented in
[Course Memory Management](../../product-specs/course-memory-management.md).

## Plan of Work

Remove preview-only follow-up write exclusions. Guard the persistence of
completed patches with the relevant active session and the existing deletion
generation protections. Route preview users to the existing scoped list and
delete endpoints using their own account and the current course.

## Concrete Steps

1. Inspect the follow-up staging, script admission policy, and reset transaction.
2. Add targeted backend regressions for draft admission, shared persistence,
   and a reset while the model is answering.
3. Wire the course menu and dialog in preview. Define the analytics contract
   and test that learner and preview usage stay separate.
4. Run the affected suites and repository guardrails.

## Validation and Acceptance

Use local test identities only. Check that ordinary preview can write admitted
memory, keeps draft script selection, and skips persistence after reset or
deletion supersedes a streamed turn. Check that the dialog can list and delete
memory for the same account and course and that preview actions are recorded
separately from learner adoption. Verify unchanged route permissions and
independent editor debug state.

## Idempotence and Recovery

No migration is required. Reverting the change restores the previous follow-up
and menu behavior. Already written memory remains in its existing scope and can
be managed from learning or, for legacy account fields, personal settings.

## Interfaces and Dependencies

Reuse follow-up memory policy and patches, preview session lifecycle checks,
course memory list and delete APIs, and the existing course memory dialog.

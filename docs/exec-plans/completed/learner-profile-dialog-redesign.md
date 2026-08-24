# Learner Profile Dialog

## Purpose / Big Picture

The learning experience uses one responsive dialog for first-time learner
onboarding and later profile editing. A learner can provide a long-term
introduction and an independent nickname; the resulting context helps AI
teachers personalize relevant course content and expression without changing
the human teacher's course design.

## Progress

- [x] 2026-08-15 CST: The dialog, canonical profile contract, optimizer,
      compatibility behavior, and focused validation are implemented.
- [x] 2026-08-24 CST: Removed the separate profile-research document prompt
      from operator configuration, learner and preview APIs, Redis sessions, and
      the admin editor. MarkdownFlow now owns the complete research conversation;
      the platform-locked profile summary remains the only appended instruction.
- [x] 2026-08-24 CST: Simplified collection completion so the generated personal
      introduction opens directly in the shared editor without automatic
      optimization. The hidden summary block no longer emits learner-visible
      MarkdownFlow content events.
- [x] 2026-08-24 CST: Completed the widened backend, frontend, i18n,
      repository, and CI verification for the direct-to-editor completion
      contract.
- [x] 2026-08-24 CST: Added an explicit collection-complete handoff before the
      save editor, carried `sys_user_nickname` into canonical nickname saving,
      and made the hidden research summary reuse the manual optimizer rules.

## Surprises & Discoveries

The product retains both canonical learner data and legacy course variables.
The dialog is the only modern learner-editing surface; legacy variables remain
available only to existing compatibility flows and courses.

## Decision Log

- The dialog follows one flow: collect learner context when needed, review the
  nickname and long-term introduction, optionally improve the introduction,
  then save.
- Nickname and introduction are independent inputs. The system never extracts a
  nickname from introduction prose; an exact `sys_user_nickname` MarkdownFlow
  assignment is carried separately into the nickname input and final save.
- The active editor has a viewport-responsive, content-independent height with
  internal scrolling.
- AI optimization replaces only the current in-memory introduction draft; it
  never saves automatically and supports one-step undo.
- The optimizer returns the model's non-empty plain-text result as generated.
  It reports protocol, configuration, moderation, timeout, or provider errors
  with their specific user-facing reasons.
- The optimizer uses the current user's system language for generated labels
  and sentences; every category starts on its own line.
- The optimizer has one server-side in-flight slot per learner to prevent a
  duplicate request. It has no IP rate limit, trusted-proxy configuration, or
  feature-specific environment variables.
- The modern flow never writes legacy `sys_*` rows. It may read the exact
  `sys_user_nickname` assignment from its Redis session result so V2 complete
  can save the canonical nickname alongside the profile.
- Profile onboarding configuration contains only the enable switch and the
  MarkdownFlow document. Legacy stored `document_prompt` keys are ignored and
  disappear on the next save; they are never returned or executed.
- The collection surface relies on the dialog title and permanent purpose
  statement; it does not add a second question heading or a duration estimate.
- The platform-generated profile draft is returned only as structured terminal
  session metadata. It is never emitted as a learner-visible MarkdownFlow
  content item.
- A completed collection places that draft directly in the personal
  introduction editor after the learner chooses **Review and confirm**. AI
  optimization remains available only as an explicit learner action from the
  existing optimization card.
- The hidden collection summary appends the same optimizer prompt used by
  **Improve with AI**, with only a research-source preamble. This keeps both
  generated profiles aligned without making collection call the optimize API.

## Outcomes & Retrospective

Learners stay in the active lesson while editing a natural-language profile.
The dialog presents guidance for background, current situation, and preferred
language style without modifying the draft. Empty introduction saves are valid
and preserve the independent nickname. A saved profile is available as
untrusted learner context to Teaching, Ask, and formal preview.

AI optimization organizes and elaborates explicitly stated learner context so
later course delivery can more consistently use relevant examples,
terminology, emphasis, and expression. It does not add personal facts, take
control of course content or pedagogy, or persist any learner business state.
Collection completion itself does not invoke this optimizer.

## Context and Orientation

- Dialog and UI state:
  `src/cook-web/src/components/profile-onboarding/LearnerProfileDialog.tsx`
- Modern frontend API:
  `src/cook-web/src/api/learnerProfile.ts`
- Learner onboarding and menu entry:
  `src/cook-web/src/app/c/[[...id]]/page.tsx` and
  `src/cook-web/src/c-components/NavDrawer/MainMenuModal.tsx`
- Canonical persistence, moderation, and account merge:
  `src/api/flaskr/service/profile/learner_profile.py`
- Optimizer and its admission guard:
  `src/api/flaskr/service/profile/learner_profile_optimizer.py` and
  `src/api/flaskr/service/profile/learner_profile_optimizer_admission.py`
- Learner-profile routes:
  `src/api/flaskr/route/profile.py`

## Plan of Work

Implementation and verification are complete. Future changes must preserve the
final contracts below.

## Concrete Steps

For a future change, update the dialog, profile API, backend service, i18n,
and focused tests as one contract. Do not reintroduce new modern writes to
legacy `sys_*` variables or make profile optimization a persistence action.

## Validation and Acceptance

- Opening learner settings keeps the lesson visible and opens the same
  accessible dialog used for first-time onboarding.
- The dialog exposes a separate nickname field and long-term introduction; the
  permanent purpose statement explains why the information is collected.
- The introduction editor uses `clamp(7rem, 18dvh, 12rem)`, is not manually
  resizable, and scrolls internally when content overflows.
- Canonical PUT accepts an empty introduction, preserves an omitted nickname,
  and clears a supplied empty nickname. DELETE remains a compatibility API that
  clears only the introduction and preserves nickname.
- Whenever the stored introduction is empty, GET exposes legacy background and
  style values so the frontend rebuilds the draft on every dialog open. Saving
  an empty introduction does not suppress that future prefill; nickname stays
  independent and is not revived from a handled legacy value.
- Profile, nickname, timestamps, and profile-v2 handled state update atomically
  on a successful save. Stale account, unmounted, or closed-dialog responses do
  not update the UI.
- The dialog never writes legacy `sys_*` values. Existing legacy variable
  behavior, including `sys_user_nickname`, remains unchanged.
- `POST /api/user/learner-profile/optimize` accepts one non-empty introduction
  and returns `{ "optimized_learner_profile": string }` in the common response
  envelope without mutating profile, nickname, timestamps, profile-v2 state, or
  client profile-changed events.
- Optimization success remains editable and requires the normal Save action;
  undo restores the original in-memory draft. Failure, rejection, or an old
  backend leaves the draft and direct Save action available.
- Finishing interactive collection shows a compact completion notice and
  requires one explicit **Review and confirm** action before the generated
  draft appears in the save editor. It does not call the optimization API; the
  learner may still choose **Improve with AI** afterward.
- If the collection document assigns `sys_user_nickname`, the terminal result
  carries only that exact value into the nickname field and V2 completion saves
  it atomically with the profile. Arbitrary MarkdownFlow variables remain
  session-only and no legacy `sys_*` row is created.
- The platform summary block produces no `content` or `element` event for the
  MarkdownFlow renderer; only the terminal `done` payload carries
  `profile_draft` and the optional collected nickname to the dialog boundary.
- The optimizer receives JSON-wrapped untrusted input and returns plain text.
- Course prompts receive canonical learner data only as JSON-encoded untrusted
  context. Learner data can personalize examples, terminology, emphasis,
  address, and language style but cannot override course design, teaching
  sequence, interactions, output format, or runtime instructions.
- Focused backend and frontend tests, type checking, linting, formatting,
  translation validation, architecture boundaries, repository harness, and
  desktop/mobile browser QA pass before merge.

## Idempotence and Recovery

No schema migration belongs to this dialog or optimizer. Re-running focused
tests, static checks, and browser QA is safe. If a change regresses a legacy
compatibility path, restore only the narrow affected behavior; do not reset or
rewrite legacy profile contracts.

## Interfaces and Dependencies

- Database: existing `user_users.nickname`, `learner_profile`, and
  `learner_profile_updated_at` fields plus the existing profile-v2 onboarding
  state; no new optimizer schema is required.
- API: `GET|PUT|DELETE /api/user/learner-profile` and authenticated
  `POST /api/user/learner-profile/optimize`.
- API semantics: GET exposes the canonical profile and safe nickname value;
  PUT accepts an optional nickname; DELETE preserves nickname; optimize is
  draft-only and returns no persisted state.
- Runtime: the canonical prompt composer supplies the same learner context to
  Teaching, Ask, and formal preview.
- Deployment: deploy backend before frontend. The new frontend can omit
  nickname for an introduction-only update; a changed nickname requires the
  new backend.

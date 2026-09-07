# Course Sharing

## Purpose / Big Picture

Give teachers and learners one consistent way to share a course. The share
action should open the browser or operating system's native share sheet when
possible and otherwise copy a complete, localized recommendation containing
the course name, the teacher-authored description, and the canonical course
home URL.

Teachers receive the action between Preview and Publish without changing the
course's publication state. Learners receive it in the desktop header, mobile
header, and mobile fullscreen listen/classroom header, while learner preview
mode continues to hide all sharing entry points.

## Progress

- [x] 2026-08-29 06:36 CST: Reviewed the teacher and learner headers, course
      information flow, URL helpers, localization structure, tracking wrapper,
      and existing clipboard behavior.
- [x] 2026-08-29 06:36 CST: Created `sunner/course-sharing` from the current
      `origin/main` checkout and recorded the implementation contract here.
- [x] 2026-08-29 06:50 CST: Implemented the shared share formatter, canonical
      URL resolver, native-share/clipboard flow, button, and focused tests.
- [x] 2026-08-29 06:52 CST: Added the teacher and learner entry points plus the
      learner course-description store lifecycle.
- [x] 2026-08-29 06:54 CST: Added all five locales, regenerated i18n key types,
      and completed focused and repository validation.
- [ ] 2026-08-29 06:54 CST: Exercise native share sheets on physical iOS and
      Android devices; this device-only QA is not available in the local test
      environment.

## Surprises & Discoveries

- The teacher detail response already gives every draft a stable `/c/{bid}`
  URL, even when no published snapshot exists. A URL is therefore not evidence
  that a course is published, which is compatible with the product decision to
  let teachers share unpublished courses without publishing them.
- `buildCoursePageUrl` already implements the learner-side canonicalization
  contract: it accepts only HTTP(S), strips URL credentials, removes the query
  and fragment, and preserves the current custom host and `/c/...` path.
- The learner course-info response already contains the course description,
  but the layout uses it only for document metadata. The learner course store
  needs to own that value for all three share surfaces.
- The existing teacher publish-link helper intentionally accepts loose relative
  values. Sharing needs the stricter shared sanitizer so malformed, query-only,
  and protocol-relative teacher URLs fall back to `/c/{bid}` instead of being
  reinterpreted as valid local paths.
- A course-id readiness gate is needed in the learner wrapper in addition to
  clearing the description in an effect. The gate prevents the first render
  after a route switch from pairing the previous title with the new URL.
- Adding an active ExecPlan requires regenerating the repository knowledge
  index before the harness check can pass.

## Decision Log

- Decision: share the stable course-home link regardless of publication,
  teacher permissions, or read-only state.
  - Why: sharing must remain separate from Publish, and the requested behavior
    explicitly accepts that recipients of an unpublished link may see a course
    that is not yet available.
- Decision: keep native-share invocation directly inside the button click
  handler and perform analytics without awaiting it.
  - Why: browsers require native sharing to retain the original user gesture.
- Decision: keep the teacher-authored description verbatim except for trimming
  leading and trailing whitespace.
  - Why: internal newlines and the full 500-character field are meaningful
    course content and must not be translated or truncated.
- Decision: use one shared component and one learner store-backed wrapper.
  - Why: formatting, URL safety, fallback behavior, toasts, busy state, and
    event privacy must not drift across four visual entry points.
- Decision: render learner sharing only after `courseSettingsCourseId` matches
  the current route's course bid.
  - Why: course and environment stores update independently during navigation;
    the match is the existing signal that the current course-info response has
    populated the learner store.

## Outcomes & Retrospective

The shared course action now serves the teacher header plus learner desktop,
mobile, and mobile fullscreen headers. It produces exact localized native and
clipboard payloads, rejects unsafe URLs, isolates share analytics from course
content, and keeps publication and sharing independent.

Nine focused Jest suites pass with 111 tests, along with i18n generation,
translation validity and usage checks, TypeScript, frontend lint,
architecture-boundary validation, repository harness validation, changed-file
formatting, and whitespace checks. Existing repository-wide lint warnings are
unchanged and no new warning points at this feature. Physical iOS/Android
share-sheet QA remains outstanding because it requires real devices.

## Context and Orientation

The frontend lives under `src/web`. Teacher authoring actions are rendered
by `src/web/src/components/header/Header.tsx`. Learner desktop actions are
in `Components/ChatUi/ChatUi.tsx`, learner mobile actions are in
`Components/ChatMobileHeader.tsx`, and the mobile fullscreen listen/classroom
header is constructed in `Components/ChatUi/ListenModeSlideRenderer.tsx`.

`src/web/src/app/c/[[...id]]/layout.tsx` loads course information. The
Zustand course store is `src/web/src/store/useCourseStore.ts`, with its
public state contract in `src/web/src/types/store.ts`.

Shared share behavior belongs in a small frontend library module and a shared
button under `src/web/src/components/course-share`. Existing URL cleanup
in `src/web/src/lib/urlUtils.ts` remains the canonical low-level
course-page sanitizer. User-facing strings live in each locale's
`common/core.json` and generated key types live in
`src/web/src/types/i18n-keys.d.ts`.

## Plan of Work

1. Build deterministic localized text assembly and absolute canonical course
   URL resolution, including root-relative teacher URLs and `/c/{bid}` fallback.
2. Build a shared async share operation that calls `navigator.share` first,
   treats `AbortError` as cancellation, and falls back to copying the complete
   formatted message through Clipboard API and `execCommand`.
3. Wrap that operation in an accessible, busy-safe share button with localized
   label/toasts and privacy-limited analytics.
4. Insert the teacher action between Preview and Publish without consulting or
   mutating publish permissions/state.
5. Store learner course descriptions, clear stale values before course reload,
   and render the learner wrapper on desktop, mobile, and fullscreen surfaces,
   hidden in preview mode.
6. Add five-language strings, regenerate types, and validate exact formatting,
   fallbacks, URL cleanup, entry-point visibility, and store lifecycle.

## Concrete Steps

1. Add `src/web/src/lib/courseShare.ts` and unit tests for description
   variants, payloads, cancellation/fallback outcomes, and URL safety.
2. Add `CourseShareButton` with icon/label display variants, toast handling,
   re-entry protection, and `course_share_click` / `course_share_result` events.
3. Update `Header.tsx` and focused tests for unpublished, read-only, and
   no-publish-permission behavior without any publish request.
4. Extend `CourseStoreState`, the course store, and learner layout hydration;
   add a store-backed learner share wrapper.
5. Add the wrapper to the desktop, mobile, and fullscreen learner headers and
   cover preview-mode hiding.
6. Update `ar-SA`, `en-US`, `fr-FR`, `th-TH`, and `zh-CN` common strings and
   regenerate `i18n-keys.d.ts`.
7. Run focused Jest suites followed by i18n, translation, type, lint,
   architecture-boundary, and whitespace validation.

## Validation and Acceptance

- Formatting tests compare exact output for populated, empty, multiline, and
  500-character descriptions. Chinese copied output matches the approved text.
- Native share receives separate `title`, recommendation/description `text`,
  and canonical `url` fields. Clipboard fallback receives the complete text,
  not only the URL.
- Native success, user cancellation, native error with copy success, no native
  support with copy success, and total failure all have observable tests.
- Shared URLs preserve valid custom domains and `/c/...` paths while removing
  URL credentials, all query parameters, and fragments; invalid protocols are
  rejected and teacher sharing falls back to the current origin and bid.
- Teacher sharing remains usable for unpublished, read-only, and
  no-publish-permission courses and never invokes a publish request.
- Learner desktop, mobile, and fullscreen surfaces show the action outside
  preview mode, and the learner description is populated and cleared before a
  course switch or reload.
- Focused Jest, `npm run i18n:keys`, translation checks, `npm run type-check`,
  `npm run lint`, architecture-boundary validation, and `git diff --check`
  complete successfully. Physical iOS/Android share-sheet behavior is recorded
  separately when device testing is available.

## Idempotence and Recovery

All source and locale edits are deterministic and can be safely reapplied.
Native share and clipboard calls occur only from explicit clicks; retrying
after failure does not persist server state. A rejected or invalid teacher URL
falls back to an origin-local course route without changing the stored course.

If a focused integration test exposes excessive prop plumbing, retain the
shared operation and component contracts and adjust only the learner wrapper.
If i18n type generation changes unrelated output, inspect locale drift before
accepting the generated file rather than hand-editing it.

## Interfaces and Dependencies

The shared component accepts the course title, teacher-authored description,
course bid, a synchronous URL resolver, display form, and one of these stable
surfaces: teacher header, learner desktop header, learner mobile header, or
learner mobile fullscreen. The shared operation exposes native, clipboard, and
failure/cancellation outcomes so the component can report results consistently.

No backend API, database model, or course DTO changes are required. Runtime
dependencies are existing browser APIs (`navigator.share`,
`navigator.clipboard`, and the guarded `document.execCommand` fallback), the
existing `useTracking` and toast hooks, Lucide icons, shared button/tooltip
primitives, Zustand course state, and the existing course-page URL sanitizer.

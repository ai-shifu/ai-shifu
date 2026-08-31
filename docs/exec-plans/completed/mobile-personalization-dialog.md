# Mobile Learner Personalization Dialog

## Purpose / Big Picture

The learner personalization dialog should behave as a focused full-screen task
under 640px while retaining the existing centered Radix Dialog on larger
screens. The mobile layout must leave more room for the active question or
editor, avoid iOS input zoom, keep controls clear of safe areas and the soft
keyboard, and preserve every existing workflow, message, API, analytics event,
and exit-policy rule.

## Progress

- [x] 2026-08-27 11:54 CST: Fast-forwarded `main` to the merged profile
      onboarding baseline and created `sunner/mobile-personalization-dialog`.
- [x] 2026-08-27 11:54 CST: Inspected the dialog, phase views, MarkdownFlow
      conversation, assistant-answer view, shared Dialog primitive, and focused
      tests.
- [x] 2026-08-27 12:10 CST: Implemented the full-screen mobile shell,
      safe-area spacing, phase-specific footers, inline information controls,
      focus scrolling, and one scroll owner per phase.
- [x] 2026-08-27 12:27 CST: Added focused regression coverage for responsive
      placement, compact-height behavior, input sizing, touch targets, exit
      policies, confirmations, focus behavior, and the hidden mobile AI entry.
- [x] 2026-08-27 12:40 CST: Passed focused and full frontend checks plus the
      repository-level validation gates listed below.
- [x] 2026-08-27 12:40 CST: Captured local before/after evidence at all accepted
      viewports and recorded unavailable physical-device validation explicitly.

## Surprises & Discoveries

- The current mobile dialog is a nearly full-height inset card with a decorative
  drag handle, although the Radix Dialog has no drag-to-dismiss behavior.
- The shared input primitives use 14px text by default. MarkdownFlow contains a
  mix of 16px and 14px controls, so the dialog must enforce the mobile minimum
  on all nested form controls without changing the shared primitives.
- The existing AI-assistant entry is deliberately `hidden sm:inline-flex` and a
  focused test treats that as a product contract. This change must not expose
  it on mobile.
- Width alone was not sufficient for the accepted 844x390 landscape viewport.
  The desktop shell left only about 83px for its body, so a max-height 620px
  compact mode is required while preserving the under-640 full-screen boundary.
- The save editor's flex section originally shrank below its children's natural
  height. Expanding the inline details at 320x568 exposed an optimization-card
  overlap that class-only tests did not catch; compact/mobile save content now
  uses natural height inside the body scroller.
- Coarse-pointer emulation exposed a 40px nickname input at 844x390 even after
  its font reached 16px. Dialog-scoped input/select minimum heights now protect
  touch devices without changing fine-pointer desktop density.

## Decision Log

- Continue using `src/components/ui/Dialog.tsx` so fullscreen portal routing,
  focus trapping, and browser-fullscreen behavior remain centralized.
- Use `100dvh` and safe-area padding before considering any
  `window.visualViewport` adjustment. A dialog-scoped viewport variable is
  allowed only if iPhone validation still demonstrates occlusion.
- Collection owns scrolling inside the conversation/MarkdownFlow region. Save,
  loading, error, and confirmation states own scrolling in the dialog body.
- Render information usage as an in-flow mobile `<details>` and retain the
  existing desktop footer popover. Render the mobile interactive-collection
  action beside the save heading while retaining the desktop footer action.
- Use a max-height 620px compact composition for short landscape windows:
  inline secondary controls replace desktop footer controls, header/body
  spacing tightens, and footer actions stay on one row.
- Apply the mobile 16px/44px guarantees again for `any-pointer: coarse` above
  the width breakpoint so a rotated phone does not inherit fine-pointer desktop
  sizing.
- Do not change copy, i18n keys, APIs, persistence, state transitions, events,
  dependencies, or the mobile visibility of the AI-assistant entry.

## Outcomes & Retrospective

The dialog now fills the dynamic viewport below 640px with safe-area-aware
header, body, footer, and close-button spacing. Collection keeps scrolling in
MarkdownFlow; save and confirmation scroll in the dialog body. Mobile and
short-landscape footers contain only the phase exit and primary actions, while
the information explanation and interactive-collection action live in the
active body. The centered desktop Dialog, footer popover, workflow, copy, APIs,
analytics, and hidden mobile AI-assistant entry are unchanged.

Focused Jest passed 99 tests across the three touched component suites. The
complete frontend run passed 178 suites and 1564 tests. TypeScript, ESLint,
changed-file Prettier, `git diff --check`, architecture boundaries, repository
harness, dev-tools, and lefthook also passed; existing repository lint and React
test warnings remained non-failing.

Local Chromium measurements using the synchronized real component and mocked
local API responses produced no horizontal overflow:

- 390x844 Chinese save, collection-ready, and confirmation: full 390x844 shell,
  69px footer, 678px body, 16px inputs, and no visible target under 44px.
- 320x568 French: 81px footer and 306px body; expanded information details stay
  in the body scroller with zero overlap against the optimization card.
- 844x390 landscape: 69px footer and at least 179px body. Coarse-pointer
  emulation computes 16px input text, a 44px nickname input, and no undersized
  visible controls.
- 390x844 Arabic renders with `dir=rtl`, logical alignment, and no overflow.
  1280x720 retains the 900px centered desktop Dialog, desktop footer popover,
  and 14px desktop inputs.

Before/after evidence is under `output/playwright/mobile-personalization/`.
This host has no `simctl`, no Android emulator, and no connected `adb` device,
so iPhone Safari and Android Chrome soft-keyboard behavior remains explicitly
unverified. Chromium focus checks confirmed the 16px sizing and focus-in-view
path, but are not represented as device-keyboard verification. Because no
iPhone occlusion could be reproduced, the staged `visualViewport` workaround
was not added.

## Context and Orientation

- Dialog shell and phase footer:
  `src/web/src/components/profile-onboarding/LearnerProfileDialog.tsx`
- Phase views and information usage control:
  `src/web/src/components/profile-onboarding/LearnerProfileDialogViews.tsx`
- MarkdownFlow collection region:
  `src/web/src/components/profile-onboarding/ProfileOnboardingConversation.tsx`
- Pasted AI answer editor:
  `src/web/src/components/profile-onboarding/ProfileAssistantAnswersView.tsx`
- Focused tests live beside those components.

## Plan of Work

First reshape only the responsive shell and view composition. Then codify the
responsive contracts in Jest without viewport-dependent JavaScript. After the
focused suite passes, run the broader frontend and repository checks. Finally,
exercise the real synchronized component in local browsers at the required
locales, directions, and viewports and measure footer/body geometry.

## Concrete Steps

1. Remove the decorative handle and make the mobile DialogContent fill the
   dynamic viewport with no border or radius. Apply physical safe-area padding
   to header, body, and footer; restore the current desktop dimensions at `sm`.
2. Make body overflow conditional on the active phase and keep header/footer
   outside the scroll owner.
3. Add inline and popover variants for information usage. Place the inline
   variant inside each phase's primary mobile scroller and hide the footer
   popover below `sm`.
4. Add a mobile save-view slot for interactive collection and keep the desktop
   copy in the footer. Compress each mobile footer to its exit and primary
   action only.
5. Enforce at least 16px text on mobile inputs and at least 44px touch targets.
   On focus, scroll form controls to the nearest visible position inside their
   existing phase scroller.
6. Update focused tests, then run the validation commands and browser geometry
   checks listed below.

## Validation and Acceptance

- At 390x844, Chinese collection, save, and confirmation states use a true
  full-screen shell with fixed header/footer and no horizontal overflow.
- At 320x568 in French, inline information details stay in flow; footer height
  is at most 112px and visible body height is at least 200px.
- At 844x390, footer height is at most 96px and visible body height is at least
  140px.
- At 390x844 in Arabic, logical alignment and controls remain within the visual
  viewport. At 1280x720, the centered desktop Dialog and footer popover remain.
- Mobile nickname, profile, assistant-answer, and MarkdownFlow form controls
  compute to at least 16px. Mobile action targets are at least 44 by 44px.
- Blocking/dismissible exits, save, review, discard/replace confirmations,
  focus restoration, and mobile AI-assistant hiding retain existing behavior.
- Run focused Jest, full frontend regression, type-check, ESLint, Prettier,
  architecture boundaries, repository harness, dev-tools, and lefthook.
- iPhone Safari/iOS Simulator and Android Chrome should be used to focus every
  input and verify that the keyboard and home indicator do not cover the caret
  or actions. If those environments are unavailable, do not represent Chromium
  emulation as equivalent verification.

## Idempotence and Recovery

The change has no schema, API, dependency, or persisted-data mutation. Tests,
formatters, local servers, and screenshot capture are safe to rerun. If a
responsive class causes a regression, revert only the affected view or slot;
do not change the shared Dialog portal or global viewport metadata.

## Interfaces and Dependencies

- No public component contract or backend interface changes.
- Internal view props may add an optional in-scroll content slot, an
  information-control presentation variant, and the mobile secondary action.
- No new package is required. Radix Dialog, existing Button/Input/Textarea
  primitives, Tailwind responsive utilities, and current i18n keys are reused.

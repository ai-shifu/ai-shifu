# Learner Profile Dialog Design QA

## Evidence

- Reference: `docs/assets/learner-profile-dialog-approved-reference.png`
- Reference pixels: 1487 x 1058. The image contains the approved desktop
  dialog and mobile bottom-sheet composition side by side.
- Local implementation: `http://localhost:3000`, rendered against the existing
  development API from the current course route.
- Browser choice: the Codex Desktop in-app browser, following the Product
  Design browser-choice rule.
- Latest implementation evidence:
  `/private/tmp/learner-profile-optimizer-desktop-1280x720.png`,
  `/private/tmp/learner-profile-optimizer-desktop-1487x1058.png`, and
  `/private/tmp/learner-profile-optimizer-mobile-390x844.png`.
- Combined reference/implementation comparison input:
  `/private/tmp/learner-profile-optimizer-reference-comparison.png`.
- Browser console: no application errors. One existing Tailwind CDN warning
  was present in the course page and is unrelated to this dialog.

## Static Comparison Completed

- Desktop content is a centered 680-pixel dialog with rounded corners, a
  contextual 45% overlay, a left-aligned heading, and no decorative Sparkles
  icon.
- The latest 684 x 781 comparison confirms the heading, description, field
  label, and textarea now share the same 57-pixel left edge. The former
  28-pixel secondary header inset is gone, while the prompt chips remain
  intentionally centered as a separate choice row.
- Desktop spacing, editor height, writing-guide padding, and footer padding are
  compact enough that the dialog does not require scrolling on first open at
  1280 x 720. The editor measured 115px before and after replacing 16 characters
  with a 756-character draft; its `scrollHeight` increased from 113px to 480px
  while `overflow-y: auto` kept overflow inside the field.
- Mobile content leaves a 96-pixel contextual header area above a bottom sheet
  with a drag handle, rounded top corners, internal scrolling, and
  safe-area-aware actions.
- The approved information hierarchy is present: three optional prompt chips,
  a separate nickname field, one canonical introduction field, a compact
  optional “帮我优化” action, a three-item writing guide, reassurance, and only
  the context-appropriate secondary action plus primary save action. Direct
  user feedback refined the selected reference by removing the clear and
  overflow action from the active dialog.
- Chinese, English, and French copy consistently refers to the AI teacher. The
  settings title now invites the learner to introduce themselves, and the
  Chinese field label asks what the AI teacher should know over time. The
  approved example presents a relatable office worker in Shanghai, a common
  university background, an AI-supported personal ambition, and a preferred
  language style that any subject can reuse instead of assuming a course task.
- The dialog description, third prompt, and writing guide make language style
  discoverable without asking the learner to set teaching pace, structure,
  examples, or interaction patterns; those remain the course teacher’s domain.
- Component tests assert the structural properties above, focus behavior,
  minimum action height, and dialog semantics. These checks do not replace a
  browser-rendered pixel comparison.

## Interaction Checks Completed

- Load, retry, save, discard, dismiss, duplicate-action, and stale response
  behavior are covered by focused dialog tests.
- A live failed optimization left the exact original draft in place, restored
  the ordinary save action, displayed the compact inline fallback message, and
  allowed close/discard. The development API did not yet expose the new
  endpoint, so successful replacement, undo, unchanged output, moderation
  rejection, duplicate requests, and late-response suppression were verified
  by the 38 focused dialog tests instead of mutating learner data in the
  browser.
- Deleting every character from a loaded profile keeps the normal save action
  available and writes an empty canonical profile through PUT without adding a
  separate clear button; an initially empty editor still cannot send a no-op
  mutation.
- Settings and first-time presentation share the same dialog while preserving
  their distinct save/dismiss contracts.
- Account and dialog-mode switches remount the editor so discarded text cannot
  cross scopes.
- Compatibility tests retain the modern DELETE contract and the legacy
  `LearnerProfileSettingsSection` clear flow. The redesigned dialog has no
  separate clear action; its normal save action uses PUT for a deliberately
  emptied loaded draft, while DELETE remains a compatibility-only operation
  that preserves the independent nickname.

## Latest Scoped Comparison

- Earlier finding: the reference header was centered inside an extra 560-pixel
  max-width wrapper, placing it about 28 pixels to the right of the form.
- Fix: removed that wrapper, made the title and description full-width and
  left-aligned, and retained right padding only to protect the close button.
- Post-fix evidence: the 1487 x 1058 implementation capture preserves the
  reference's centered desktop surface, contextual lesson background, rounded
  corners, left-aligned content, compact guide, reassurance, and anchored
  footer. The deliberate product refinements—explicit nickname, simplified
  example, no clear/overflow action, and optional optimizer—fit without adding
  initial scrolling.
- Fonts/typography: existing sizes, weights, and line heights are unchanged;
  the new title fits on one line at the target viewport.
- Spacing/layout: shared desktop horizontal padding defines one left edge; no
  clipping or horizontal overflow is visible. At 390 x 844 the sheet occupies
  the lower 748px of the viewport, the editor is 135px tall, the optimizer has
  a 44px touch target, content scrolls behind a visible sticky footer, and the
  page remains visible above the sheet.
- Colors/tokens: unchanged from the existing design system and source state.
- Image/asset fidelity: no image assets changed; existing Lucide icons remain
  sharp and consistent.
- Copy/content: the requested Chinese strings and simplified example are
  visible exactly, with natural English and French equivalents covered by
  translation tests. The optimizer disclosure states that only expression is
  changed and no new learner information is added.
- Focused regions were not needed beyond the full dialog because the relevant
  title, description, label, and textarea edges are legible at 1x in the
  equal-size comparison.

final result: passed

The viewport-adaptive fixed editor and optional optimizer introduce no
remaining actionable P0/P1/P2 visual findings. Desktop and mobile rendering,
internal editor scrolling, failure fallback, close/discard, console state, and
44px mobile action sizing were checked in the in-app browser; successful
optimization and undo remain covered by focused component tests until the new
backend endpoint is available in the shared development environment.

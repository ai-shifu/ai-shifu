# Learner Profile Dialog Design QA

## Evidence

- Reference: `docs/assets/learner-profile-dialog-approved-reference.png`
- Reference pixels: 1487 x 1058. The image contains the approved desktop
  dialog and mobile bottom-sheet composition side by side.
- Local implementation: `http://localhost:3000`, confirmed to return HTTP 200.
- Browser choice: the in-app browser selected by the user.
- Latest user reference: the 684 x 781 screenshot supplied on 2026-08-13,
  preserved for this QA pass at
  `/var/folders/1k/xp54mn593c1fx5mhjlslxc500000gn/T/codex-clipboard-47d911de-7cef-40fd-9306-eabb6088f95b.png`.
- Latest implementation screenshot:
  `/private/tmp/learner-profile-dialog-aligned-684x781.png`, captured in the
  selected in-app browser at the same 684 x 781 CSS viewport and 1x display
  density. The side-by-side comparison input is
  `/private/tmp/learner-profile-dialog-comparison.png`.

## Static Comparison Completed

- Desktop content is a centered 680-pixel dialog with rounded corners, a
  contextual 45% overlay, a left-aligned heading, and no decorative Sparkles
  icon.
- The latest 684 x 781 comparison confirms the heading, description, field
  label, and textarea now share the same 57-pixel left edge. The former
  28-pixel secondary header inset is gone, while the prompt chips remain
  intentionally centered as a separate choice row.
- Desktop spacing, editor height, writing-guide padding, and footer padding are
  compact enough that the dialog no longer requires scrolling on first open;
  internal scrolling remains available for shorter viewports and longer input.
- Mobile content leaves a 96-pixel contextual header area above a bottom sheet
  with a drag handle, rounded top corners, internal scrolling, and
  safe-area-aware actions.
- The approved information hierarchy is present: three optional prompt chips,
  one canonical introduction field, a three-item writing guide, reassurance,
  and only the context-appropriate secondary action plus primary save action.
  Direct user feedback refined the selected reference by removing the clear
  and overflow action from the active dialog.
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
- Deleting every character from a loaded profile keeps the normal save action
  available and clears the canonical profile without adding a separate clear
  button; an initially empty editor still cannot send a no-op clear.
- Settings and first-time presentation share the same dialog while preserving
  their distinct save/dismiss contracts.
- Account and dialog-mode switches remount the editor so discarded text cannot
  cross scopes.
- Compatibility tests retain the modern DELETE contract and the legacy
  `LearnerProfileSettingsSection` clear flow. The redesigned dialog has no
  separate clear action, but its normal save action uses DELETE for a
  deliberately emptied loaded draft.

## Latest Scoped Comparison

- Earlier finding: the reference header was centered inside an extra 560-pixel
  max-width wrapper, placing it about 28 pixels to the right of the form.
- Fix: removed that wrapper, made the title and description full-width and
  left-aligned, and retained right padding only to protect the close button.
- Post-fix evidence: at 684 x 781, both heading and field label measure `x =
  57`; the matched before/after comparison shows no remaining P0/P1/P2 copy or
  alignment mismatch for this requested state.
- Fonts/typography: existing sizes, weights, and line heights are unchanged;
  the new title fits on one line at the target viewport.
- Spacing/layout: shared desktop horizontal padding now defines one left edge;
  no clipping or horizontal overflow is visible.
- Colors/tokens: unchanged from the existing design system and source state.
- Image/asset fidelity: no image assets changed; existing Lucide icons remain
  sharp and consistent.
- Copy/content: the requested Chinese strings are visible exactly, with natural
  English and French title equivalents covered by translation tests.
- Focused regions were not needed beyond the full dialog because the relevant
  title, description, label, and textarea edges are legible at 1x in the
  equal-size comparison.

final result: passed

The latest user-requested desktop copy and alignment refinement has no
remaining actionable P0/P1/P2 visual findings. Broader responsive behavior and
save/dismiss flows remain covered by the existing focused component tests.

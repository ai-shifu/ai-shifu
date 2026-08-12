# Learner Profile Dialog Design QA

## Evidence

- Reference: `/Users/sunner/.codex/generated_images/019fe96e-310e-71e1-b426-efff9e67343f/exec-8c6fc012-e17d-4cbd-99c3-4838c2409753.png`
- Reference pixels: 1487 x 1058. The image contains the approved desktop
  dialog and mobile bottom-sheet composition side by side.
- Local implementation: `http://localhost:3000`, confirmed to return HTTP 200.
- Browser choice: the in-app browser selected by the user.
- Implementation screenshot: captured in the selected in-app browser after the
  compact-layout refinement. At the default desktop viewport, the dialog body
  measured `scrollHeight = clientHeight = 575` with `scrollTop = 0`, so the
  complete editor, guidance, reassurance, and actions are visible on open.

## Static Comparison Completed

- Desktop content is a centered 680-pixel dialog with rounded corners, a
  contextual 45% overlay, centered heading, and no decorative Sparkles icon.
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
- Settings and first-time presentation share the same dialog while preserving
  their distinct save/dismiss contracts.
- Account and dialog-mode switches remount the editor so discarded text cannot
  cross scopes.
- Compatibility tests retain the modern DELETE contract and the legacy
  `LearnerProfileSettingsSection` clear flow; neither is exposed as an action
  in the redesigned dialog.

## Remaining Visual QA

Capture and compare one portrait-mobile implementation at equal display
density. Also exercise the visible secondary and primary actions and confirm
the browser console has no new errors.

final result: partial

Desktop visual verification is complete, including the no-initial-scroll
measurement. Mobile visual comparison and interaction exercise remain.

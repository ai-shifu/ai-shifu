# Learner Profile Dialog Design QA

## Evidence

- Reference: `/Users/sunner/.codex/generated_images/019fe96e-310e-71e1-b426-efff9e67343f/exec-8c6fc012-e17d-4cbd-99c3-4838c2409753.png`
- Reference pixels: 1487 x 1058. The image contains the approved desktop
  dialog and mobile bottom-sheet composition side by side.
- Local implementation: `http://localhost:3000`, confirmed to return HTTP 200.
- Browser choice: the in-app browser selected by the user.
- Implementation screenshot: not captured. The in-app browser controller
  rejected claiming or reloading the localhost tab under its URL security
  policy, and the selected-browser rule prevents switching to a different
  browser or automation path.

## Static Comparison Completed

- Desktop content is a centered 680-pixel dialog with rounded corners, a
  contextual 45% overlay, centered heading, and no decorative Sparkles icon.
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

Capture the implementation in the selected in-app browser at one desktop and
one mobile viewport, compare both captures to the approved reference plus the
direct user-feedback refinement above at equal display density, and fix any
remaining P0, P1, or P2 visual differences. Also exercise the visible
secondary and primary actions and confirm the browser console has no new
errors.

final result: blocked

Blocker: a browser-rendered implementation screenshot from the selected in-app
browser is unavailable because localhost control was rejected by the browser
security policy.

# Learner Profile Dialog Design QA

## Comparison basis

- Selected direction: Product Design option 2, with a left step rail on roomy
  desktop viewports and compact top progress on mobile.
- Reference and implementation were inspected together in one comparison
  image at the choice step, then the paste, guided-error, and review states
  were inspected separately.
- Responsive checks covered 1280 x 720 desktop, 390 x 844 portrait mobile,
  320 x 568 narrow mobile in French, and 844 x 390 landscape mobile.

## Findings resolved

- P1, responsiveness: short landscape viewports initially switched to the
  desktop rail and left too little usable body space. The rail now requires
  both desktop width and sufficient height; compact progress, header, and
  footer sizing remain usable in landscape.
- P1, content reflow: a rigid title area could clip longer English or French
  text. The fixed shell now gives the header a stable scroll-safe slot, and
  French learner-facing titles were shortened without losing meaning.
- P1, mobile actions: three long French actions could overflow at 320 px.
  Mobile actions now use 44 px targets, compact save copy, narrower padding,
  and a shorter explicit later action. Measured dialog and footer scroll width
  matched client width at 320 px.
- P1, pending behavior: the guided MarkdownFlow interaction remained active
  while skip/save was pending. Pending state now makes active questions
  read-only, disables retry, ignores late results and errors, and shows visible
  progress on the explicit later action.
- P2, hierarchy and fidelity: desktop footer actions were visually weaker than
  the selected direction. Desktop secondary and primary actions now use larger,
  balanced targets while retaining stable three-slot ordering.
- P2, empty/error state: the first guided loading or error status appeared at
  the bottom of an otherwise empty page. It now appears at the start of the
  conversation area; subsequent status remains anchored below the conversation.

## Verification notes

- The dialog retained the same measured outer dimensions across choice,
  paste, guided-error, and review states at each checked viewport.
- No horizontal overflow was present in the 320 px French review state or the
  844 x 390 landscape state.
- Choice cards, paste input, review editing, real back navigation, fixed footer
  order, keyboard focus, reduced motion, pending locks, and stale guided-result
  guards are covered by focused component tests.
- Existing shared Dialog, Button, theme tokens, Lucide icons, and MarkdownFlow
  renderer are reused; no visual asset or runtime dependency was introduced.

final result: passed

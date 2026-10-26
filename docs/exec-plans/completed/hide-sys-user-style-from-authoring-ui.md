# Hide `sys_user_style` From Course Authoring UI

## Purpose / Big Picture

`sys_user_style` must no longer be presented in course-authoring variable lists,
preview variable controls, or the built-in demo's supported-variable list. Its
definition, APIs, persistence, MarkdownFlow parsing, storage scope, and runtime
substitution remain unchanged so existing courses retain the complete legacy
behavior.

## Progress

- [x] 2026-08-28 04:09 UTC: Located the course editor and preview display
      surfaces plus the demo advertisement.
- [x] 2026-08-28 04:42 UTC: Narrowed the implementation after scope
      clarification and removed all backend and protocol changes.
- [x] 2026-08-28 04:42 UTC: Hid the variable from editor recommendations and
      preview controls while preserving the internal preview variable map.
- [x] 2026-08-28 04:42 UTC: Added focused display coverage and removed the demo
      advertisement.
- [x] 2026-08-28 05:17 UTC: Completed focused and repository-level validation,
      regenerated the knowledge index, and archived this plan.

## Surprises & Discoveries

- The course editor receives the complete system-variable definition list and
  separately passes the same keys into preview storage and runtime requests.
  Filtering the shared store would therefore change behavior beyond display.
- `LessonPreview` already supports hidden display keys without removing them
  from the variable map, which keeps the compatibility boundary narrow.

## Decision Log

- Make this a frontend presentation rule, not a profile-definition policy.
- Keep backend definition reads, legacy profile APIs, MarkdownFlow parse/save,
  local storage routing, and runtime substitution byte-for-byte unchanged.
- Keep the global definition and all historical values; add no migration or
  grandfather marker.

## Outcomes & Retrospective

The course editor no longer recommends `sys_user_style`, the preview variable
panel no longer renders it, and the built-in demo no longer advertises it. The
existing definition, profile APIs, parser, persistence, storage routing, and
runtime code were left unchanged. Focused frontend and demo tests, type-check,
lint, repository harness, architecture boundaries, and the complete pre-commit
gate passed.

## Context and Orientation

Course editor variable recommendations and the preview variable panel are
assembled in `src/web/src/components/shifu-edit/ShifuEdit.tsx`. The built-in
course content is in `src/api/demo_shifus/cn_demo.json`. Profile services,
MarkdownFlow parsing, and runtime resolution are deliberately outside the code
change.

## Plan of Work

Filter `sys_user_style` only when constructing the MarkdownFlow editor's visible
system-variable list. Add it to the preview panel's hidden display keys while
leaving the preview variable map and request parameters untouched. Remove its
advertisement from the built-in demo and verify both display paths.

## Concrete Steps

1. Filter `sys_user_style` from `systemVariablesList` in the course editor.
2. Hide `sys_user_style` in the preview variable panel without deleting it from
   parsed variables, local storage, or runtime requests.
3. Remove the style row from the Chinese demo's supported system-variable list.
4. Add focused frontend and demo-content regressions, then run repository gates.

## Validation and Acceptance

- The MarkdownFlow editor does not receive `sys_user_style` as a recommended
  system variable.
- The preview variable panel does not render a control for `sys_user_style`.
- Existing parse results and preview request data can still carry
  `sys_user_style`.
- Backend source and API contracts remain unchanged.
- Focused tests, type-check, lint, repository harness, architecture boundaries,
  developer-tool check, and pre-commit pass.

## Idempotence and Recovery

All changes are frontend presentation, test, demo, and documentation edits. No
database state changes or API rollout coordination are required.

## Interfaces and Dependencies

No backend interface changes. The editor continues consuming the existing
profile-definition and MarkdownFlow parse responses and only filters the key at
render time.

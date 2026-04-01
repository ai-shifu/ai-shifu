# Design Docs And Task Checklists

For complex design work, create a dedicated topic folder under `docs/`.

Repository-wide evergreen references such as `docs/engineering-baseline.md`
may live directly under `docs/`. Topic folders are required for scoped design
work that needs implementation tracking.

## Required Structure

- `docs/<topic>/design.md`
- `docs/<topic>/tasks.md`

## Rules

- Write the design first, then implement.
- Keep `tasks.md` in the same topic folder as the design doc.
- Reference the design doc at the top of `tasks.md`.
- When `tasks.md` exists, execute the implementation against its checklist and
  keep the file current as the visible progress tracker.
- Use markdown checkboxes in `tasks.md`:
  - `- [ ]` for pending work
  - `- [x]` for completed work
- Update `tasks.md` as work progresses instead of keeping a separate hidden
  checklist.
- After finishing one checklist item, update `tasks.md` immediately and create
  one atomic commit for that completed item before starting the next item.

## Minimal Example

`docs/ai-collab-split/design.md`

`docs/ai-collab-split/tasks.md`

```md
# Tasks

Design: [AI collaboration split design](./design.md)

- [x] Finalize scope and folder layout
- [ ] Implement generated AGENTS.md files
- [ ] Validate coverage and formatting
```

# Design Docs And Root Task Checklist

For complex design work, create a flat design doc at `docs/<topic>.md` and
track active implementation in repository-root `tasks.md`.

Repository-wide evergreen references such as `docs/engineering-baseline.md`
may live directly under `docs/`. One branch should track only one active
complex topic in `tasks.md` at a time.

## Required Structure

- Active implementation topics:
  `docs/<topic>.md` and `/tasks.md`
- Completed topics:
  `docs/<topic>.md` remains required, and `tasks.md` should be deleted after
  the checklist is fully complete

## Rules

- Write the design first, then implement.
- Use repository-root `tasks.md` as the active checklist for the current
  complex topic.
- Reference the active design doc at the top of `tasks.md`.
- When `tasks.md` exists, execute the implementation against its checklist and
  keep the file current as the visible progress tracker.
- Use markdown checkboxes in `tasks.md`:
  - `- [ ]` for pending work
  - `- [x]` for completed work
- Update `tasks.md` as work progresses instead of keeping a separate hidden
  checklist.
- After finishing one checklist item, update `tasks.md` immediately and create
  one atomic commit for that completed item before starting the next item.
- Do not start a second complex topic on the same branch until `tasks.md` is
  completed and deleted or intentionally replaced.
- Once every checklist item is complete and the topic no longer needs active
  execution tracking, deleting `tasks.md` is required.
- Do not delete `tasks.md` while any item remains pending.

## Minimal Example

`docs/ai-collab-split.md`

`tasks.md`

```md
# Tasks

Design: [AI collaboration split design](./docs/ai-collab-split.md)

- [x] Finalize scope and folder layout
- [ ] Implement generated AGENTS.md files
- [ ] Validate coverage and formatting
```

After every checklist item is marked `- [x]` and the topic no longer needs
active execution tracking, deleting repository-root `tasks.md` is required.

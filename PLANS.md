# AI-Shifu ExecPlans

This repository uses execution plans ("ExecPlans") for complex features,
architecture changes, and multi-hour refactors. `PLANS.md` is the canonical
specification for how those plans are written and maintained.

## When To Use An ExecPlan

Use an ExecPlan when work:

- spans multiple modules or engineering surfaces
- changes repository structure, architecture, or shared workflows
- requires staged rollout, validation, or design decisions that must remain
  legible after the current conversation ends

Store active plans in `docs/exec-plans/active/<slug>.md`. Move them to
`docs/exec-plans/completed/<slug>.md` only after implementation and
verification are complete.

## Required Structure

Every ExecPlan must be self-contained and must contain these sections:

- `## Purpose / Big Picture`
- `## Progress`
- `## Surprises & Discoveries`
- `## Decision Log`
- `## Outcomes & Retrospective`
- `## Context and Orientation`
- `## Plan of Work`
- `## Concrete Steps`
- `## Validation and Acceptance`
- `## Idempotence and Recovery`
- `## Interfaces and Dependencies`

## Working Rules

- Treat the plan as the implementation source of truth for the topic.
- Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and
  `Outcomes & Retrospective` current while work is active.
- Write the plan so a stateless coding agent or a new engineer can continue
  the task using only the repository and the ExecPlan file.
- Record resolved ambiguities in the plan instead of leaving them in chat.
- Phrase validation as observable behavior, not only as internal code edits.

## Progress Format

`## Progress` must use markdown checkboxes with timestamps.

Example:

- [x] 2026-04-17 15:00 CST: Added the knowledge index generator.
- [ ] 2026-04-17 15:10 CST: Wire the generated inventory into the repository
  harness checker.

## Relationship To Other Docs

- `ARCHITECTURE.md` explains where repository knowledge and runtime surfaces
  live.
- `docs/engineering-baseline.md` remains the stable engineering handbook.
- `AGENTS.md` files route contributors to the right local rules and source
  documents.

## Retired Workflow

Repository-root `tasks.md` is retired. Do not create new task checklists there.
Use ExecPlans under `docs/exec-plans/` instead.

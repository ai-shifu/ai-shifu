# Repository Knowledge Store

This repository treats versioned files as the system of record for product
intent, engineering rules, and long-running execution context.

## Layout

- `../ARCHITECTURE.md`: top-level map of product surfaces and knowledge entry
  points
- `../PLANS.md`: canonical ExecPlan specification for complex work
- `engineering-baseline.md`: stable engineering handbook
- `QUALITY_SCORE.md`: current quality grades and next cleanup actions
- `RELIABILITY.md`: current validation loop and reliability constraints
- `SECURITY.md`: repository security rules for harness and diagnostics work
- `design-docs/`: architecture and implementation decision records
- `product-specs/`: product workflow and page behavior specifications
- `references/`: evergreen operational references
- `exec-plans/active/`: currently active ExecPlans
- `exec-plans/completed/`: archived ExecPlans
- `generated/`: generated indexes and inventory files
  Includes `doc-inventory.md`, `harness-health.md`, and the committed
  architecture-boundary baseline.

## Workflow

- Complex work must start from an ExecPlan under `exec-plans/active/`.
- `PLANS.md` defines the required ExecPlan structure and maintenance rules.
- Generated knowledge docs are owned by scripts and must not be edited
  manually.
- Architecture boundary rules live in `references/architecture-boundaries.md`,
  and the committed baseline is checked by
  `python scripts/check_architecture_boundaries.py`.
- Historical flat topic docs are retired; new docs should be placed in the
  directory that matches their ownership and purpose.

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
- `history/`: dated audits and superseded journals; not current execution instructions
- `exec-plans/active/`: currently active ExecPlans
- `exec-plans/completed/`: archived ExecPlans
- `generated/`: generated indexes and inventory files
  Includes committed indexes, `doc-inventory.md`, and architecture-boundary
  and unit-of-work baselines. The optional `harness-health.md` snapshot is
  ignored by Git.

## Workflow

- Complex work must start from an ExecPlan under `exec-plans/active/`.
- `PLANS.md` defines the required ExecPlan structure and maintenance rules.
- Generated knowledge docs are owned by scripts and must not be edited
  manually.
- Architecture boundary rules live in `references/architecture-boundaries.md`,
  and the committed baseline is checked by
  `python scripts/check_architecture_boundaries.py`.
- Place topic docs under their owning specifications or references directory.
  `status: needs-review` identifies a migrated source whose complete runtime
  contract has not been re-reviewed. A move does not establish implementation
  status or a review date; keep unknown `last_reviewed` values empty.
- Use `src/i18n/locales.json` as the shared language inventory; README links
  and frontend/backend locale lists must follow that source.

## Harness Health Snapshots

`generated/harness-health.md` is a derived report, generated locally and in CI.
Only this health report is excluded from version control; the other generated
documents, indexes, inventory, and enforcement baselines remain committed.

Refresh just the report from the repository root:

```bash
python scripts/build_repo_knowledge_index.py --health-only
```

The default command without `--health-only` refreshes both the committed
knowledge documents and this ignored report. Local development and
`python scripts/check_repo_harness.py` do not require the report to exist or
be current. The checker still validates source documents, required assets,
and committed generated indexes.

An ignored snapshot can become stale after switching branches or changing
documents or baseline entries. Regenerate it before relying on its counts;
asset presence in the report does not prove that tests or runtime checks pass.

In GitHub Actions, open a **Static Checks** or **Harness Gardening** run to read
the report in its job summary. Download the `harness-health` artifact from
Static Checks, or the `harness-gardening-summary` artifact from Harness
Gardening, for the Markdown report generated from that run's checkout.

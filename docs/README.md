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
  and unit-of-work baselines. `harness-health.md` and
  `harness-gardening-summary.md` are ignored local/CI snapshots.

## Workflow

- Complex work must start from an ExecPlan under `exec-plans/active/`.
- `PLANS.md` defines the required ExecPlan structure and maintenance rules.
- Generated knowledge docs are owned by scripts and must not be edited
  manually.
- Architecture boundary rules live in `references/architecture-boundaries.md`,
  and the committed baseline is checked by
  `python scripts/check_architecture_boundaries.py`.
- Place architecture and implementation topics in `design-docs/`, product
  contracts in `product-specs/`, and evergreen operational guidance in `references/`.
  `status: needs-review` identifies a migrated source whose complete runtime
  contract has not been re-reviewed. A move does not establish implementation
  status or a review date; keep unknown `last_reviewed` values empty.
- Use `src/i18n/locales.json` as the shared language inventory; README links
  and frontend/backend locale lists must follow that source.

## Harness Health Snapshots

`generated/harness-health.md` is a derived report, generated locally and in CI.
The gardening summary is also an ignored local/CI report. Committed indexes,
skill catalogs, inventory, and enforcement baselines remain versioned. Each
report records its UTC generation time and checkout HEAD; local edits may differ
from that revision, and report presence is not proof of test or runtime health.

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

## Inventory and validation

The inventory enumerates all Git-tracked Markdown and MDX, including staged
additions. If sparse checkout omits tracked documents, generation fails before
writing an inventory, catalog or health report; restore the omitted documents
(or disable sparse checkout) first. Normal unstaged deletions remain subject to
the pending-commit staging guard. It distinguishes instructions, focused skills, skill routers,
current specifications/references, active/completed plans, historical records,
generated documents and compatibility aliases. `GEMINI.md` and the minimal
Copilot entry are aliases, not alternate instruction owners.
ExecPlan location determines lifecycle status and authority: active plans have
`status=active` and are canonical; completed plans have `status=completed` and
are not canonical. Stale `status` or `canonical` frontmatter retained during a
move cannot override these values. Other document categories continue to honor
that metadata.

Stage new or moved documents before regenerating indexes. Skill catalogs in
`src/api/skills/README.md` and `src/web/skills/README.md` are generated from each
focused `SKILL.md`'s `name` and `description`; do not edit the lists manually.
The name must match its directory slug and be unique; descriptions may wrap
across indented metadata lines. Routing `SKILL.md` files remain hand-authored.

The harness checks catalog freshness, required plan sections, pending work in
completed plans, and local Markdown/MDX links, including literal HTML links and
heading anchors. Code fences and remote URLs are not interpreted or fetched.
Historical records can refer to retired runtime files, but their document
navigation must resolve. An active plan without unchecked work produces a
review reminder; archival still requires evidence of completed scope.

Unknown review dates remain empty. An old or missing date is review debt, not
proof of incorrect content and not a reason to overwrite it with today's date.
Run `python scripts/run_harness_gardening.py` for the current review-debt report;
CI uploads that run's report instead of maintaining a permanent green snapshot.

# Quality Score

## Purpose

Track repository quality from an agent-first perspective so cleanup and
governance work can be prioritized mechanically.

## Surfaces

### repo docs

- Current grade: `B`
- Gaps: the knowledge layout is versioned and indexed, but durable health still
  depends on scheduled gardening to keep `last_reviewed` data and retired-term
  cleanup current.
- Next action: keep the generated inventory and harness health report green, and
  let the gardening workflow shrink stale references continuously.

### api

- Current grade: `B+`
- Gaps: strong unit and contract coverage exists, but the default Docker dev
  stack now depends on a compatibility repair step plus live observability
  services to keep browser smoke validation stable.
- Next action: keep the migration repair path self-healing, and keep
  `scripts/harness_diagnostics.py` plus the local observability stack in the
  standard smoke-failure workflow.

### cook-web

- Current grade: `B`
- Gaps: route and component tests exist, but the browser harness still covers
  only the minimum login, admin, and learner paths.
- Next action: keep the Playwright smoke suite green under the default dev
  harness and widen it only after the current three paths stay stable.

### runtime harness

- Current grade: `B`
- Gaps: the default dev stack now includes logs, traces, metrics, and browser
  smoke plumbing, but the ongoing quality bar still depends on keeping the
  smoke suite green and paying down the committed boundary baseline.
- Next action: keep the default Docker dev stack healthy, reduce baseline
  entries incrementally, and widen smoke coverage only after the current paths
  stay stable.

### tests

- Current grade: `B`
- Gaps: strong targeted tests exist, but cross-surface verification depends on
  contributors choosing the right commands.
- Next action: keep pre-commit and the repo harness checker authoritative for
  docs and instruction changes.

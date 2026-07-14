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
- Gaps: the Phase 2 backend overhaul added a golden SSE/JSON regression
  harness, moved transaction boundaries onto a shared unit-of-work with a
  commit-site ratchet (155 grandfathered `db.session.commit()` sites outside
  `dao/` remain, down from 213), decomposed the /run runtime into
  emitter/recorder/state collaborators, and removed roughly 800 lines of dead
  code while the backend suite grew from 1,862 to 1,942 tests; the remaining
  debt is the grandfathered commit sites, the widespread legacy `Model.query`
  style, and a default Docker dev stack that still depends on a compatibility
  repair step plus live observability services for browser smoke validation.
- Next action: ratchet the commit-site baseline down as touched modules
  migrate to `unit_of_work()`, keep the golden fixtures byte-stable across
  refactors, and keep `scripts/harness_diagnostics.py` plus the local
  observability stack in the standard smoke-failure workflow.

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
- Next action: keep lefthook and the repo harness checker authoritative for
  docs and instruction changes.

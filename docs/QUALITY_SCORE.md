# Quality Score

## Purpose

Track repository quality from an agent-first perspective so cleanup and
governance work can be prioritized mechanically.

## Surfaces

### repo docs

- Current grade: `B`
- Gaps: the knowledge layout is being restructured; some historical docs still
  describe retired workflows.
- Next action: keep the generated inventory green and convert remaining stale
  references to ExecPlans.

### api

- Current grade: `B`
- Gaps: strong unit and contract coverage exists, but the default Docker dev
  stack is currently blocked by a migration import failure before browser
  smoke flows can reach steady state.
- Next action: fix the startup migration coupling, then keep
  `scripts/harness_diagnostics.py` in the standard smoke-failure workflow.

### cook-web

- Current grade: `B-`
- Gaps: route and component tests exist, but browser-driven validation was not
  previously a standard path.
- Next action: keep the Playwright smoke suite green and widen it only after
  the minimum harness loop is stable.

### runtime harness

- Current grade: `C+`
- Gaps: the repository now defines a browser-plus-log harness and captures
  request ids plus failure artifacts, but the smoke paths are still red while
  the backend startup migration failure returns `502` responses.
- Next action: make the three smoke paths green in the default Docker dev
  stack, then collect evidence on whether a richer local telemetry stack is
  worth the extra maintenance cost.

### tests

- Current grade: `B`
- Gaps: strong targeted tests exist, but cross-surface verification depends on
  contributors choosing the right commands.
- Next action: keep pre-commit and the repo harness checker authoritative for
  docs and instruction changes.

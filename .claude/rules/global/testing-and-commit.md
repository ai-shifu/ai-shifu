# Claude Rule: Testing And Commit

Use this Claude-only rule to route testing and commit hygiene without
duplicating the shared repository guidance already stored in `AGENTS.md`.

- Prefer the nearest `CLAUDE.md` and `AGENTS.md` pair before reading any
  deeper path-specific rule in this folder.

- Before changing code, inspect the current implementation and reuse existing
  abstractions where possible instead of building a parallel solution from
  scratch.

- Keep the repository hard rules visible in the primary manual docs:
  English-only code-facing text, no hardcoded user-facing strings or secrets,
  and shared-contract doc updates in the same change.

- Use `docs/engineering-baseline.md` for the stable engineering handbook, and
  use the layered `AGENTS.md` files for AI execution rules.

- Before each commit, review the nearest `AGENTS.md` and `CLAUDE.md` files for
  the touched areas; if the implementation change makes them inaccurate,
  update those docs in the same commit.

- For complex design work, create an ExecPlan under
  `docs/exec-plans/active/` and maintain it according to `PLANS.md`.

- Keep the ExecPlan current as work progresses. Record progress, discoveries,
  and decisions in the plan instead of relying on chat-only context.

- Move completed ExecPlans to `docs/exec-plans/completed/` once
  implementation and verification are done.

- When Claude is asked for a commit-sized change, run the smallest relevant
  verification first and widen only when shared contracts are affected.

- Keep commit hygiene aligned with the shared repository rule set:
  Conventional Commit subjects, English-only code-facing text, and no skipped
  migration review after backend schema changes.

- If a task changes only docs or AI-instruction files, the minimum
  verification target is `python scripts/check_repo_harness.py`.

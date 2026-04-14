# Claude Rule: Skills Routing

Use this Claude-only rule to decide when to follow a skill instead of
inflating `AGENTS.md` with procedural troubleshooting steps.

- Shared structural rules belong in `AGENTS.md`; repeatable multi-step
  workflows belong in `SKILL.md` files.

- Prefer `src/api/SKILL.md` for backend workflows and `src/cook-web/SKILL.md`
  for Cook Web workflows.

- When a module-level `AGENTS.md` points to a focused skill, load that skill
  before improvising a new troubleshooting process.

- If a workflow repeats and no skill exists yet, add one instead of copying
  the same playbook into multiple directory-level docs.

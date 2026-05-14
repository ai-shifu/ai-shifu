# api Skills

## Layering

- Keep durable structural rules in `AGENTS.md` and `CLAUDE.md`.
- Use `SKILL.md` only for repeatable workflows, debugging playbooks, and
  migration checklists that would otherwise bloat directory-level rules.
- Backend module `AGENTS.md` files may point here or to focused skills under
  `src/api/skills/`.

## Backend Skill Index

- `skills/shifu-authoring-flow/SKILL.md`
- `skills/user-auth-flows/SKILL.md`
- `skills/gen-mdf-proxy/SKILL.md`

## When To Add A Skill

- Add a focused backend skill when the same provider, auth, streaming, or
  persistence workflow is repeated across multiple tasks.
- Keep each skill actionable: trigger, core rules, workflow, and regression
  checklist.

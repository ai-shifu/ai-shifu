# ai-shifu Skills Entry

## Scope

- This file only keeps repository-level skill routing and boundary notes.
- Backend and frontend maintain their own skill entry points so this file does not grow into a mixed troubleshooting manual.

## Placement Rules

- Keep `ai-shifu/SKILL.md` for cross-project skill routing, ownership boundaries, and migration notes.
- Keep `src/api/SKILL.md` for backend project-level skill entry points and focused skill indexes.
- Keep `src/cook-web/SKILL.md` for long-lived cook-web constraints and focused skill indexes.
- Keep `src/api/skills/xxx/SKILL.md` or `src/cook-web/skills/xxx/SKILL.md` for focused skills with triggers, workflows, and regression checklists.

## Entry Points

- Backend: `src/api/SKILL.md`
- Frontend: `src/cook-web/SKILL.md`
- Frontend skills index: `src/cook-web/skills/README.md`
- Backend skills index: `src/api/skills/README.md`

## Migration Notes

- Stable rules belong in layered `AGENTS.md / CLAUDE.md`.
- Troubleshooting knowledge that needs step-by-step execution or long-term reuse belongs in the relevant subproject `SKILL.md` system.

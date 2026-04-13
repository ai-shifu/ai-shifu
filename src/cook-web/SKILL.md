# cook-web Skills

## Layering Rules

- Keep `SKILL.md` for long-lived cross-page or cross-module constraints and the skill index.
- Keep `skills/xxx/SKILL.md` for scenario-specific triggers, execution steps, and acceptance checks.
- `SKILL.md` must not carry long troubleshooting playbooks; workflow-heavy content belongs in focused skills.
- Stable structural rules should go to the local `AGENTS.md / CLAUDE.md` first. Only workflow-oriented guidance should live in a skill.

## Project-Wide Constraints

- Treat URL parameters as a single source of truth: use `lessonid` for lesson targeting and the `listen` query parameter for listen mode.
- Streaming chat must use `element_bid` as the stable render key, with compatibility fields backfilled in the shared normalization entry point.
- When the same logic is reused by more than two files, extract it into shared `utils/constants/hooks` instead of duplicating it.
- For system interaction buttons such as `_sys_pay`, prefer ai-shifu-side render overrides to keep repeatable CTAs clickable without patching `markdown-flow-ui`.

## Skills Index

- `skills/chat-layout-width-detection/SKILL.md`
- `skills/interaction-user-input-defaults/SKILL.md`
- `skills/deep-link-lessonid-routing/SKILL.md`
- `skills/chat-element-streaming/SKILL.md`
- `skills/chat-actionbar-ask-placement/SKILL.md`
- `skills/listen-mode-audio-streaming/SKILL.md`
- `skills/listen-mode-slide-mobile-integration/SKILL.md`
- `skills/fullscreen-dialog-portal/SKILL.md`
- `skills/markdownflow-controlled-sync/SKILL.md`
- `skills/next-build-node-runtime/SKILL.md`
- `skills/module-augmentation-guardrails/SKILL.md`
- `skills/hook-contract-refactor-safety/SKILL.md`
- `skills/chat-system-interaction-button-overrides/SKILL.md`
- `skills/lesson-reset-run-gating/SKILL.md`

## Usage Rules

- Module-level `AGENTS.md` files may reference skills from here, but they must not copy skill content back into directory rules.
- If the same frontend troubleshooting workflow repeats across tasks, add a focused skill instead of expanding `AGENTS.md`.

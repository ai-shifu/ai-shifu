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
- 后台侧边栏这类上下分区布局优先使用 `flex flex-col`，让菜单容器承担 `flex-1 min-h-0`，把会员卡、账户卡这类摘要信息固定在底部，避免它们随着菜单高度漂移。
- 侧边栏摘要卡片遇到“0 值”和“有值”两种状态时，优先做条件化布局而不是只替换数字；零值状态保持简洁头部，有值状态再展开明细和跳转入口。
- 当卡片或快捷入口跳转到带页签的页面时，优先使用显式的查询参数或可还原状态直达目标页签，避免用户落到默认页签后再二次操作。
- 会员、订阅这类标题或徽标文案需要由真实订阅数据推导，不要把“月订阅”之类的周期标签写死在侧边栏或摘要卡片里。

## Skills Index

- `skills/chat-layout-width-detection/SKILL.md`
- `skills/interaction-user-input-defaults/SKILL.md`
- `skills/deep-link-lessonid-routing/SKILL.md`
- `skills/chat-element-streaming/SKILL.md`
- `skills/chat-actionbar-ask-placement/SKILL.md`
- `skills/listen-mode-audio-streaming/SKILL.md`
- `skills/next-build-node-runtime/SKILL.md`
- `skills/module-augmentation-guardrails/SKILL.md`
- `skills/hook-contract-refactor-safety/SKILL.md`

## Usage Rules

- Module-level `AGENTS.md` files may reference skills from here, but they must not copy skill content back into directory rules.
- If the same frontend troubleshooting workflow repeats across tasks, add a focused skill instead of expanding `AGENTS.md`.

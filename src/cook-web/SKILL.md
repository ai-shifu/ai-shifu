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
- 套餐页里的“非会员/免费”卡片属于月套餐的一部分，应稳定展示；当用户当前没有有效订阅时，这张卡需要作为默认当前态，而不是被试用开关直接隐藏。
- 套餐介绍卡片的默认态、hover 态和当前选中态应共用一套设计 token：默认态走基础边框/卡片背景/阴影，hover 与当前态走高亮边框、渐变背景和同一套阴影，避免不同套餐卡片各自维护一套视觉规则。
- 套餐价格区的主价格和周期/说明后缀需要拆成独立标签，分别应用字号与颜色，不要把 `¥9.9 /月` 或免费说明拼成同一个文本样式块。
- 套餐权益列表需要统一标题层级、左右 icon 尺寸、图文间距和垂直居中规则，避免不同卡片里出现看起来没有对齐的权益项。

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

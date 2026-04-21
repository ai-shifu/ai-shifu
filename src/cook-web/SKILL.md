# cook-web Skills

## Layering Rules

- Keep `SKILL.md` for long-lived cross-page or cross-module constraints and the skill index.
- Keep `skills/xxx/SKILL.md` for scenario-specific triggers, execution steps, and acceptance checks.
- `SKILL.md` must not carry long troubleshooting playbooks; workflow-heavy content belongs in focused skills.
- Stable structural rules should go to the local `AGENTS.md / CLAUDE.md` first. Only workflow-oriented guidance should live in a skill.

## Project-Wide Constraints

- Treat URL parameters as explicit overrides: use `lessonid` for lesson targeting, let `listen` query override learner mode when present, and fall back to course-level `tts_enabled` to decide whether listen mode is available while keeping read mode as the default.
- 当 `listen=true` 先以听课模式初始化、后续又因为旧课兼容或能力检查回退到阅读模式时，要基于当前模式重新同步移动端正文里的追问按钮，不要只依赖首轮数据装配结果。
- Streaming chat must use `element_bid` as the stable render key, with compatibility fields backfilled in the shared normalization entry point.
- When the same logic is reused by more than two files, extract it into shared `utils/constants/hooks` instead of duplicating it.
- 做 i18n key usage 排查时，不要把 `*.test.*`、`*.spec.*`、`__tests__` 里的断言文案、namespace 字符串或拼接后的展示文本当成真实翻译 key；优先统计生产代码里的 `t()`、`i18n.t()`、`Trans` 和符合完整 key 结构的常量。
- 积分套餐权益文案优先以 `BillingOverviewCards` 里的共享 feature key 列表作为单一来源；删除某项权益时，要同时清理 `billing.json`、预注册翻译使用代码、相关测试数据和 `i18n-keys.d.ts` 残留。
- For system interaction buttons such as `_sys_pay`, prefer ai-shifu-side render overrides to keep repeatable CTAs clickable without patching `markdown-flow-ui`.
- When adapting cook-web payloads into `markdown-flow-ui` slide elements, normalize optional API fields into the stricter slide contract first instead of passing broader API types through render layers.
- When listen-mode misses trailing interaction cards, check whether `outline_item_update: completed` arrived before the final `element` events; completion must not cause post-completion interaction markers to be dropped.

## Skills Index

- `skills/chat-layout-width-detection/SKILL.md`
- `skills/interaction-user-input-defaults/SKILL.md`
- `skills/deep-link-lessonid-routing/SKILL.md`
- `skills/chat-element-streaming/SKILL.md`
- `skills/chat-actionbar-ask-placement/SKILL.md`
- `skills/listen-mode-audio-streaming/SKILL.md`
- `skills/listen-mode-slide-mobile-integration/SKILL.md`
- `skills/fullscreen-dialog-portal/SKILL.md`
- `skills/async-confirm-dialog-loading/SKILL.md`
- `skills/markdownflow-controlled-sync/SKILL.md`
- `skills/next-build-node-runtime/SKILL.md`
- `skills/module-augmentation-guardrails/SKILL.md`
- `skills/hook-contract-refactor-safety/SKILL.md`
- `skills/chat-system-interaction-button-overrides/SKILL.md`

## Usage Rules

- Module-level `AGENTS.md` files may reference skills from here, but they must not copy skill content back into directory rules.
- If the same frontend troubleshooting workflow repeats across tasks, add a focused skill instead of expanding `AGENTS.md`.

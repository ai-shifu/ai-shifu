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
- 账务/积分页面如果同一类时间展示同时出现在卡片、表格或 tooltip 中，优先抽到 `src/lib/billing.ts` 的共享格式化方法；涉及中英文文案时，同步更新 `zh-CN/en-US`、`i18n-keys.d.ts` 和对应组件测试，避免只改页面不改类型与回归用例。
- 钱包余额、可用积分、侧边会员卡余额这类“积分余额”展示统一只保留整数部分且不加千分位分隔；套餐赠送额度、购买额度、消耗量等非余额数字继续使用通用积分格式化方法，避免把两类数字口径混用。
- 当产品要求把套餐赠送积分数、免费体验积分和积分充值包额度也统一成整数展示时，优先复用 `src/lib/billing.ts` 的共享积分数量格式化方法，确保套餐卡、免费卡、充值卡和对应测试口径一致。
- admin 侧边会员卡如果改成双层信息布局，保持整卡点击跳转 `packages`、底部“查看详情”独立跳转 `details`，并把积分余额与到期时间放在同一信息层；卡片整体内边距优先保持 `py-14px / pl-16px`，右侧需要贴设计微调时可收敛成 `pr-12px`。若设计稿要求顶部“积分 + 升级”这一整行整体左收 `4px`，优先给这一行的外层容器补 `padding-right`，不要误加到升级按钮本身；`查看详情` 默认不要额外补右侧内边距。头部与信息层之间优先用弱分隔线 `rgba(0,0,0,0.05)`，分隔线下余额行 `pt-3`、到期/详情行 `pt-2.5`，正文颜色优先复用 `--base-card-foreground` 和既有 `text-sm` typography token。
- 14px 文字旁边的 chevron 类图标，优先收敛到 `h-4 w-4`，并让容器使用 `items-center + leading-none`、文字单独保留 `leading-5`，避免图标因继承文本行高出现视觉不对齐。
- 同一 billing 页面如果两个 section title 需要完全一致，优先把标题 class 抽成 `src/components/billing/` 下的共享常量或共享组件，再让各面板复用，不要在两个文件里各写一份近似但不一致的字号。
- 同一 billing 页面如果多个 section title 需要保持一致，除了标题字号本身，还要同步检查标题到卡片/表格主体的纵向间距；当前这类 section 优先统一为 `24px`，避免一个 `space-y-4`、一个 `space-y-6` 的情况。
- admin 页面里这种二选一 tabs/switch 如果产品要求“选中态和未选中态的圆角一致”，优先在具体页面同时覆写 `TabsList` 和 `TabsTrigger` 的圆角，不要只改外层容器导致内部 trigger 仍保留另一套圆角。
- admin 页面头部如果有单一主创建动作（如“新建课程”），优先复用 `Button` 的默认主按钮样式，保持蓝底白字；不要继续沿用 `outline` 让主 CTA 在信息层级上变弱。
- admin 课程卡片如果要提升 hover 反馈，优先避免再叠加强 box-shadow；默认保留现有静态阴影，并改用 `primary` 的低透明度淡蓝背景来表达 hover 态，减少界面抖动。
- admin 课程卡片如果产品要求更扁平的视觉，优先直接去掉 box-shadow，只保留边框和 hover 淡蓝底色，不要同时保留阴影和背景变色造成层级过重。
- 课程设置这类 `Sheet` 表单弹层如果头部下方有分隔线，表单滚动内容区优先显式补 `padding-top: 24px`，不要让第一组字段紧贴分隔线开始。
- 对于明确暂不支持移动端的页面，优先复用共享的国际化弹窗组件统一提示，避免在多个页面分别写一套移动端拦截文案和状态逻辑。
- For system interaction buttons such as `_sys_pay`, prefer ai-shifu-side render overrides to keep repeatable CTAs clickable without patching `markdown-flow-ui`.
- When adapting cook-web payloads into `markdown-flow-ui` slide elements, normalize optional API fields into the stricter slide contract first instead of passing broader API types through render layers.
- When listen-mode misses trailing interaction cards, check whether `outline_item_update: completed` arrived before the final `element` events; completion must not cause post-completion interaction markers to be dropped.
- 当新增共享 loading 动画时，优先放在 `src/components/loading/` 并以命名导出追加能力，不要直接替换已有默认 loading；动画节奏、尺寸和间距用可配置 props 暴露，保证旧调用方零破坏。
- 听课模式字幕尾部清洗只移除不允许的结束标点，遇到右引号、右括号这类成对符号的结尾符必须保留；即使这些结尾符后面还跟着句号、逗号等待过滤标点，也要按从右向左的顺序先保留结尾符、再剥离无效标点，并补齐 `。”`、`），`、`？”。` 一类回归测试。

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
- `skills/shared-loading-dots/SKILL.md`

## Usage Rules

- Module-level `AGENTS.md` files may reference skills from here, but they must not copy skill content back into directory rules.
- If the same frontend troubleshooting workflow repeats across tasks, add a focused skill instead of expanding `AGENTS.md`.

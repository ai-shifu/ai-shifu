# cook-web Skills

## Layering Rules

- Keep `SKILL.md` for long-lived cross-page or cross-module constraints and the skill index.
- Keep `skills/xxx/SKILL.md` for scenario-specific triggers, execution steps, and acceptance checks.
- `SKILL.md` must not carry long troubleshooting playbooks; workflow-heavy content belongs in focused skills.
- Stable structural rules should go to the local `AGENTS.md / CLAUDE.md` first. Only workflow-oriented guidance should live in a skill.

## Project-Wide Constraints

- Treat URL parameters as explicit overrides: use `lessonid` for lesson targeting, let `listen` query override learner mode when present, and fall back to course-level `tts_enabled` to decide whether listen mode is available while keeping `read` as the default. When no course-scoped `course_learning_mode:*` storage exists yet and there is no explicit URL override, persist the resolved default mode immediately so first-load behavior and local storage stay in sync.
- 学习页如果要新增和初始化模式有关的埋点，优先在写回 `course_learning_mode:*` 之前先读取并上报原始 localStorage 值，避免“首进自动补写默认值”覆盖掉用户上一次真实固定的模式。
- 当 `listen=true` 先以听课模式初始化、后续又因为旧课兼容或能力检查回退到阅读模式时，要基于当前模式重新同步移动端正文里的追问按钮，不要只依赖首轮数据装配结果。
- Streaming chat must use `element_bid` as the stable render key, with compatibility fields backfilled in the shared normalization entry point.
- When the same logic is reused by more than two files, extract it into shared `utils/constants/hooks` instead of duplicating it.
- 做 i18n key usage 排查时，不要把 `*.test.*`、`*.spec.*`、`__tests__` 里的断言文案、namespace 字符串或拼接后的展示文本当成真实翻译 key；优先统计生产代码里的 `t()`、`i18n.t()`、`Trans` 和符合完整 key 结构的常量。
- 积分套餐权益文案优先以 `BillingOverviewCards` 里的共享 feature key 列表作为单一来源；删除某项权益时，要同时清理 `billing.json`、预注册翻译使用代码、相关测试数据和 `i18n-keys.d.ts` 残留。
- 账务/积分页面如果同一类时间展示同时出现在卡片、表格或 tooltip 中，优先抽到 `src/lib/billing.ts` 的共享格式化方法；涉及多语言文案时，同步更新所有支持的 locale、`i18n-keys.d.ts` 和对应组件测试，避免只改页面不改类型与回归用例。
- 钱包余额、可用积分、侧边会员卡余额这类“积分余额”展示统一只保留整数部分且不加千分位分隔；套餐赠送额度、购买额度、消耗量等非余额数字继续使用通用积分格式化方法，避免把两类数字口径混用。
- 当产品要求把套餐赠送积分数、免费体验积分和积分充值包额度也统一成整数展示时，优先复用 `src/lib/billing.ts` 的共享积分数量格式化方法，确保套餐卡、免费卡、充值卡和对应测试口径一致。
- admin 侧边会员卡如果改成双层信息布局，保持整卡点击跳转 `packages`、底部“查看详情”独立跳转 `details`，并把积分余额与到期时间放在同一信息层；卡片整体内边距优先保持 `py-14px / pl-16px`，右侧需要贴设计微调时可收敛成 `pr-12px`。若设计稿要求顶部“积分 + 升级”这一整行整体左收 `4px`，优先给这一行的外层容器补 `padding-right`，不要误加到升级按钮本身；`查看详情` 默认不要额外补右侧内边距。头部与信息层之间优先用弱分隔线 `rgba(0,0,0,0.05)`，分隔线下余额行 `pt-3`、到期/详情行 `pt-2.5`，正文颜色优先复用 `--base-card-foreground` 和既有 `text-sm` typography token。
- 14px 文字旁边的 chevron 类图标，优先收敛到 `h-4 w-4`，并让容器使用 `items-center + leading-none`、文字单独保留 `leading-5`，避免图标因继承文本行高出现视觉不对齐。
- 同一 billing 页面如果两个 section title 需要完全一致，优先把标题 class 抽成 `src/components/billing/` 下的共享常量或共享组件，再让各面板复用，不要在两个文件里各写一份近似但不一致的字号。
- 同一 billing 页面如果多个 section title 需要保持一致，除了标题字号本身，还要同步检查标题到卡片/表格主体的纵向间距；当前这类 section 优先统一为 `24px`，避免一个 `space-y-4`、一个 `space-y-6` 的情况。
- admin 页面里这种二选一 tabs/switch 如果产品要求“选中态和未选中态的圆角一致”，优先在具体页面同时覆写 `TabsList` 和 `TabsTrigger` 的圆角，不要只改外层容器导致内部 trigger 仍保留另一套圆角。
- admin 页面头部如果有单一主创建动作（如“新建课程”），优先复用 `Button` 的默认主按钮样式，保持蓝底白字；不要继续沿用 `outline` 让主 CTA 在信息层级上变弱。
- `/admin` 课程首页里整张课程卡片如果承担的是进入作者工作台的导航，默认使用新标签页打开，避免打断当前课程列表浏览和筛选上下文。
- admin 课程卡片如果要提升 hover 反馈，优先避免再叠加强 box-shadow；默认保留现有静态阴影，并改用 `primary` 的低透明度淡蓝背景来表达 hover 态，减少界面抖动。
- admin 课程卡片如果产品要求更扁平的视觉，优先直接去掉 box-shadow，只保留边框和 hover 淡蓝底色，不要同时保留阴影和背景变色造成层级过重。
- 后台页面和 `shifu` 详情页这类桌面工作台如果要新增右侧固定联系入口，优先抽成共享悬浮组件挂在 layout 或页面根层；颜色复用 `bg-primary / text-primary-foreground`，外链统一新开页跳转，避免在多个页面各写一份定位和跳转逻辑。
- `/shifu/[id]` 作者工作台页默认不要展示右侧 `ContactSideRail`；这类全局悬浮入口是否出现要按页面场景单独决策，避免把后台或营销辅助入口直接带进创作主流程。
- `/shifu/[id]` 作者工作台顶部这类会触发新开页或路由跳转的工具按钮，如果要补埋点，优先直接挂在真实点击入口上调用 `useTracking().trackEvent`，并在导航发生前上报；产品没要求业务参数时不要额外补自定义参数，保持事件语义单一。
- 如果前端要新增一个和 `HOME_URL` 类似的运行时配置项，优先沿 `common/config.py -> route/config.py -> billing runtime DTO -> cook-web environment/envStore/initializeEnvData` 这条链路一次性补齐；默认值、creator branding override、store 字段和页面显隐逻辑一起落地，避免只改页面读取不改 runtime config。
- 课程设置这类 `Sheet` 表单弹层如果头部下方有分隔线，表单滚动内容区优先显式补 `padding-top: 24px`，不要让第一组字段紧贴分隔线开始。
- 这类带右侧倍率或状态徽标的下拉选项，如果选中态需要显示勾选标记，优先把勾放进右侧预留列，并通过共享 `SelectItem` 暴露定位能力；左侧不要额外保留空列占位，且 trigger / option 的左内边距要和表单里的 `Input` 基线一致，再给右侧徽标和勾选标记留出足够间距。
- 登录页图形验证码图片按钮如果设计要求跟随验证码图片宽度自适应，优先让按钮固定目标高度、图片使用 `h-full w-auto`，不要保留固定宽度；刷新入口优先合并到验证码图片按钮的 hover/focus 蒙层，不要额外放独立刷新按钮；验证码图片按钮和获取验证码按钮需要视觉对齐时，优先统一 `min-width` 并允许倒计时等长文案自适应撑开，必要时在具体按钮上覆盖默认 padding。
- 登录页表单新增字段标题或提示文案时，必须同步更新所有支持的 locale 翻译文件和 `src/types/i18n-keys.d.ts`，不要在组件里写死中文、英文或其它用户可见文案。
- 对于明确暂不支持移动端的页面，优先复用共享的国际化弹窗组件统一提示，避免在多个页面分别写一套移动端拦截文案和状态逻辑。
- For system interaction buttons such as `_sys_pay`, prefer ai-shifu-side render overrides to keep repeatable CTAs clickable without patching `markdown-flow-ui`.
- When adapting cook-web payloads into `markdown-flow-ui` slide elements, normalize optional API fields into the stricter slide contract first instead of passing broader API types through render layers.
- When listen-mode misses trailing interaction cards, check whether `outline_item_update: completed` arrived before the final `element` events; completion must not cause post-completion interaction markers to be dropped.
- 当新增共享 loading 动画时，优先放在 `src/components/loading/` 并以命名导出追加能力，不要直接替换已有默认 loading；动画节奏、尺寸和间距用可配置 props 暴露，保证旧调用方零破坏。
- 听课模式字幕尾部清洗只移除不允许的结束标点，遇到右引号、右括号这类成对符号的结尾符必须保留；即使这些结尾符后面还跟着句号、逗号等待过滤标点，也要按从右向左的顺序先保留结尾符、再剥离无效标点，并补齐 `。”`、`），`、`？”。` 一类回归测试。
- 听课模式移动端 fullscreen header 的标题文案不要硬编码白色，优先继承 `markdown-flow-ui` 的 `--slide-mobile-fullscreen-chrome-foreground`，这样宿主侧浅色毛玻璃 header 和返回按钮颜色才能保持一致。
- 阅读模式首个渲染项的顶部留白要在统一容器层处理，优先把 `loading`、首个 content、首个 ask 和首个 interaction 都视为“第一个 element”，共用同一套 top padding，避免只改普通内容块导致首屏间距不一致。
- `/c/:id` 页面 preview 模式如果要在 learner header 增加提示 banner，优先作为 header 内部第二行渲染，并同步抬高 mobile sticky header 高度、desktop header 占位和正文 top padding，不要把 banner 放成 header 同级导致吸顶和内容错位。
- 学习页初始化排查如果需要给 QA 或运营直接复现链路，优先提供 `debug=1` 这类显式 URL 开关，把请求层、`1001` 鉴权恢复链路和页面初始化日志同步显示在页内调试面板，而不是只依赖远程控制台。
- 预览/调试 SSE 如果在开始流式输出前就返回业务错误（如 `7101`），前端不要只停留在 `loading` 占位；应把后端返回的 `message` 直接落到聊天列表里替换 loading，保证作者侧能看到真实失败原因。
- 作者侧预览区如果要对特定业务错误提供后续操作，优先把错误码挂在预览错误项上，再由 `LessonPreview` 按错误码渲染定向 CTA；像 `7101` 积分不足这类场景，应直接提供跳转 `/admin/billing?tab=packages` 的充值入口，而不是靠文案匹配做分支。
- 作者侧预览/调试模式如果要补阅读模式风格的打字机节奏，优先在 `src/components/lesson-preview/` 下独立维护一套 preview gate 和缓存完成态，不要直接复用 learner 页 `readModeTypewriterGate`，避免作者侧交互节奏与学习页状态机互相耦合。
- 作者侧预览里的喇叭辅助行要视作正文 text element 的后置 helper：只有父级是 `text` element 且该正文块打字机完成后才显示；父级是 `html`、`interaction` 等非 text element 时不要渲染这行辅助能力。

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

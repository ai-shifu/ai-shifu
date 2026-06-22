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
- 账务/积分相关用户可见文案必须遵守产品命名边界：不要使用“充值”或 top-up / recharge 语义；覆盖套餐和积分包两种补充积分路径的正文，使用“开通订阅或购买积分”，且订阅优先；明确只指 `topup` 商品、订单、账本来源或 checkout 时使用“积分包”；按钮和短 CTA 保持简洁，使用“购买积分”；用户可见文案使用“账户”而不是“钱包”。内部 `topup` / `wallet` 字段、路由、枚举和 i18n key 可保留技术命名，但不得直接作为展示文案。
- 积分详情页的“积分消耗明细”表格优先复用 `src/app/admin/components/AdminTableShell.tsx` 和标准 `Table` 组件；分页走 `AdminTableShell.pagination`，不要在 billing 组件里另写卡片表格和独立分页外壳。
- 仅服务后台路由且依赖 `src/app/admin/components/*` 的 billing 组件，应放在 `src/app/admin/billing/components/` 这类同路由作用域下；`src/components/*` 里的共享组件不要直接 import `src/app/*` 的 route-internal 实现，避免触发架构边界校验。
- `AdminTableShell` 内的表头默认保持左对齐；如果某些 body 单元格需要右对齐，只在 body 内容层处理，不要把表头也右对齐。自定义骨架屏行放进 `AdminTableShell` 时要禁用 hover 背景，避免加载翻页时出现整行灰色条。
- 账户余额、可用积分、侧边会员卡余额这类“积分余额”展示统一只保留整数部分且不加千分位分隔；套餐赠送额度、购买额度、消耗量等非余额数字继续使用通用积分格式化方法，避免把两类数字口径混用。
- 当产品要求把套餐赠送积分数、免费体验积分和积分包额度也统一成整数展示时，优先复用 `src/lib/billing.ts` 的共享积分数量格式化方法，确保套餐卡、免费卡、积分包卡和对应测试口径一致。
- 积分购买页的当前页面标题优先通过后台面包屑承载；页面主体不要再重复展示同名大标题，避免“首页 > 积分购买”下方再次出现“积分购买”。
- 积分消耗明细表格迁移到 `AdminTableShell` 后，列宽优先让“消耗项”占最大宽度，时间列居中偏右，数量列贴近最右侧对齐；不要在时间列保留旧版 grid 表格里的 `text-right`、`justify-end` 或 `ml-auto` 残留，数量列如需靠右可只在该列内容层使用 `justify-end`/`ml-auto`。加载骨架屏行需要同时禁用 `tr:hover` 和 `td:hover` 背景，避免翻页 loading 时出现整行灰色条。
- admin 侧边会员卡如果改成双层信息布局，保持整卡点击跳转 `packages`、底部“查看详情”独立跳转 `details`，并把积分余额与到期时间放在同一信息层；卡片整体内边距优先保持 `py-14px / pl-16px`，右侧需要贴设计微调时可收敛成 `pr-12px`。若设计稿要求顶部“积分 + 升级”这一整行整体左收 `4px`，优先给这一行的外层容器补 `padding-right`，不要误加到升级按钮本身；`查看详情` 默认不要额外补右侧内边距。头部与信息层之间优先用弱分隔线 `rgba(0,0,0,0.05)`，分隔线下余额行 `pt-3`、到期/详情行 `pt-2.5`，正文颜色优先复用 `--base-card-foreground` 和既有 `text-sm` typography token。
- 14px 文字旁边的 chevron 类图标，优先收敛到 `h-4 w-4`，并让容器使用 `items-center + leading-none`、文字单独保留 `leading-5`，避免图标因继承文本行高出现视觉不对齐。
- 同一 billing 页面如果两个 section title 需要完全一致，优先把标题 class 抽成 `src/components/billing/` 下的共享常量或共享组件，再让各面板复用，不要在两个文件里各写一份近似但不一致的字号。
- 同一 billing 页面如果多个 section title 需要保持一致，除了标题字号本身，还要同步检查标题到卡片/表格主体的纵向间距；当前这类 section 优先统一为 `24px`，避免一个 `space-y-4`、一个 `space-y-6` 的情况。
- admin 页面里这种二选一 tabs/switch 如果产品要求“选中态和未选中态的圆角一致”，优先在具体页面同时覆写 `TabsList` 和 `TabsTrigger` 的圆角，不要只改外层容器导致内部 trigger 仍保留另一套圆角。
- admin 页面头部如果有单一主创建动作（如“新建课程”），优先复用 `Button` 的默认主按钮样式，保持蓝底白字；不要继续沿用 `outline` 让主 CTA 在信息层级上变弱。
- `/admin` 课程首页顶部布局中，标题下方操作区左侧放课程筛选 tabs（如“全部/归档”），右侧放课程创建入口；OpenClaw 智能建课引导文案应放在新建课程按钮左侧，不要和标题挤在同一行。
- `/admin` 课程首页的 tabs 与新建课程工具行默认不要额外添加上下 padding，底部间距保持 `32px`；新建课程按钮默认只展示文字，不展示左侧加号图标，确保右侧操作视觉更简洁。
- `/admin` 课程首页课程筛选 tabs 外层使用 `10px` 圆角、`--base-muted` 背景和 `3px` padding；选中项使用 `8px` 圆角、`1px` 边框、白色背景、`shadow-sm` 变量阴影和 `4px 8px` padding。
- `/admin` 课程首页里整张课程卡片如果承担的是进入作者工作台的导航，默认使用新标签页打开，避免打断当前课程列表浏览和筛选上下文。
- `/admin` 课程首页课程卡片头像统一使用 `28px` 正方形和 `8px` 圆角，头像与课程名间距保持 `12px` 且垂直居中；无头像时背景使用 `#CFCED4`，占位图标使用 `public/icons/logo.svg` 且尺寸保持 `16px x 19px`，不要再使用 `TrophyIcon` 作为占位图标。
- `/admin` 课程首页课程卡片标题使用黑色、16px、500、20px line-height，描述距离头像所在标题行下方 `16px`，描述使用 `rgba(10,10,10,0.65)`、14px、400、20px line-height。
- `/admin` 课程首页课程卡片容器统一使用 `--border-radius-rounded-xl`、`--base-border`、`--base-card` 和 `shadow-sm` 对应 CSS 变量，不要再使用 slate border 或默认背景替代。
- admin 课程卡片如果要提升 hover 反馈，优先避免再叠加强 box-shadow；默认保留现有静态阴影，并改用 `primary` 的低透明度淡蓝背景来表达 hover 态，减少界面抖动。
- admin 数据统计数字卡片（包含数据页 KPI 和课程详情核心数据）优先复用 `src/app/admin/components/AdminCountCard.tsx`；容器使用 rounded-xl、base-border、base-card 渐变背景、shadow-sm 和 `24px` padding，标题用 muted-foreground/text-sm/normal，数字用 card-foreground/text-3xl/semibold，标题和数字间距保持 `6px`。
- admin 课程卡片如果产品要求更扁平的视觉，优先直接去掉 box-shadow，只保留边框和 hover 淡蓝底色，不要同时保留阴影和背景变色造成层级过重。
- 后台页面和 `shifu` 详情页这类桌面工作台如果要新增右侧固定联系入口，优先抽成共享悬浮组件挂在 layout 或页面根层；颜色复用 `bg-primary / text-primary-foreground`，外链统一新开页跳转，避免在多个页面各写一份定位和跳转逻辑。
- admin 页面标题区域默认不要在右侧添加额外 padding，`AdminTitle` 的内容容器右侧应保持 `pr-0`，确保标题 actions 能和下方卡片、表格右边缘对齐。
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
- 听课模式追问弹层的展开/收起应和阅读模式一样透传给 `AskBlock.isExpanded`，不要在关闭时直接卸载 `AskBlock`；这样 `AskBlock` 内部的追问打字机收起清理和未完成流式追问状态才能保持一致。
- 当新增共享 loading 动画时，优先放在 `src/components/loading/` 并以命名导出追加能力，不要直接替换已有默认 loading；动画节奏、尺寸和间距用可配置 props 暴露，保证旧调用方零破坏。
- 听课模式字幕尾部清洗只移除不允许的结束标点，遇到右引号、右括号这类成对符号的结尾符必须保留；即使这些结尾符后面还跟着句号、逗号等待过滤标点，也要按从右向左的顺序先保留结尾符、再剥离无效标点，并补齐 `。”`、`），`、`？”。` 一类回归测试。
- 听课模式移动端 fullscreen header 的标题文案不要硬编码白色，优先继承 `markdown-flow-ui` 的 `--slide-mobile-fullscreen-chrome-foreground`，这样宿主侧浅色毛玻璃 header 和返回按钮颜色才能保持一致。
- 阅读模式首个渲染项的顶部留白要在统一容器层处理，优先把 `loading`、首个 content、首个 ask 和首个 interaction 都视为“第一个 element”，共用同一套 top padding，避免只改普通内容块导致首屏间距不一致。
- `/c/:id` 页面 preview 模式如果要在 learner header 增加提示 banner，优先作为 header 内部第二行渲染，并同步抬高 mobile sticky header 高度、desktop header 占位和正文 top padding，不要把 banner 放成 header 同级导致吸顶和内容错位。
- 学习页初始化排查如果需要给 QA 或运营直接复现链路，优先提供 `debug=1` 这类显式 URL 开关，把请求层、`1001` 鉴权恢复链路和页面初始化日志同步显示在页内调试面板，而不是只依赖远程控制台。
- 预览/调试 SSE 如果在开始流式输出前就返回业务错误（如 `7101`），前端不要只停留在 `loading` 占位；应把后端返回的 `message` 直接落到聊天列表里替换 loading，保证作者侧能看到真实失败原因。
- 作者侧预览区如果要对特定业务错误提供后续操作，优先把错误码挂在预览错误项上，再由 `LessonPreview` 按错误码渲染定向 CTA；像 `7101` 积分不足这类场景，应直接提供跳转 `/admin/billing?tab=packages` 的订阅或积分购买入口，而不是靠文案匹配做分支。
- 作者侧预览/调试模式如果要补阅读模式风格的打字机节奏，优先在 `src/components/lesson-preview/` 下独立维护一套 preview gate 和缓存完成态，不要直接复用 learner 页 `readModeTypewriterGate`，避免作者侧交互节奏与学习页状态机互相耦合。
- 作者侧预览里的喇叭辅助行要视作正文 text element 的后置 helper：只有父级是 `text` element 且该正文块打字机完成后才显示；父级是 `html`、`interaction` 等非 text element 时不要渲染这行辅助能力。
- cook-web App Router 错误兜底页应同时覆盖 `src/app/error.tsx` 与 `src/app/global-error.tsx`，并在页面上直接展示错误 `name/message/digest/cause/URL/stack` 等排障信息；复制错误信息时还要带上当前链接、来源链接和简要浏览器环境（浏览器名称、操作系统），但不要复制用户信息、token 或密码。
- 根布局、错误兜底页和全局 Provider 这类基础入口不要从 `@/store` barrel 静态引入状态模块；优先 import 精确子模块，避免 barrel 触发 `useShifu/useTracking/useUiLayoutStore` 等无关模块副作用。

- 后台管理页筛选区布局优先复用 `src/app/admin/components/AdminFilter.tsx`；筛选项 label 使用 `--base-foreground` 与 text-sm/medium token，需要纵向对齐时传入固定 label 宽度；查询和重置按钮左右内边距保持 `16px`，展开按钮使用 `--base-foreground` 并保持与查询按钮 `24px`、与 chevron `4px` 的间距；当筛选项数量不超过收起态展示数量时不要显示展开/收起按钮。
- 后台管理页筛选项只有两种响应式形态：`xl` 及以上用固定三列横向展示，`xl` 以下直接切换为纵向一行一个筛选项，不要使用 `auto-fit` 或 `md:grid-cols-2` 造成两列加一列的中间态；输入控件最大宽度限制应跟随横向断点启用，共享筛选项容器需要 `min-w-0`，避免窄屏时控件被提前压缩。
- 后台管理页独立筛选操作区如果暂未接入 `AdminFilter`，查询/重置按钮仍要和订单页保持一致：重置在前、查询在后，均使用 `Button size="sm"` 且左右内边距 `16px`，操作组靠右对齐。
- 后台管理页表格视觉优先复用 `src/app/admin/components/AdminTableShell.tsx` 和 `src/app/admin/components/adminTableStyles.ts`；外框边框用 `--base-border`，表头背景用 `--base-muted`，表头文字用 `--base-foreground` 与 text-sm/medium/20px token，tbody 单元格保持原生 table-cell 布局并使用 `53px` 高度、`8px` padding 和 text-sm/normal/20px token，表格单元格默认不展示右侧 border 且内容左对齐，首列左侧优先用 `16px` padding，整行 hover 背景要覆盖 sticky 操作列，溢出文本优先复用 `AdminTooltipText` 查看完整内容，默认不添加示意用拖拽列或 checkbox 选择列。
- 后台数据页的课程列表也应复用 `AdminTableShell`，标题区域用 `header` 配置，统计范围说明用 `footnote` 配置，分页用 `pagination` 配置；需要 loading 时仍展示分页和说明时传入 `showFooterWhenLoading`。
- 后台数据页课程列表如果产品要求精简表格顶部区域，可以不传 `header`；课程总数和统计范围说明合并到同一条 `footnote` 中，优先使用“课程数：{count}（统计范围说明...）”这类单行文案。
- admin 表格所有操作列都应和订单表格一致固定在右侧：表头使用 `getAdminStickyRightHeaderClass`，单元格使用 `getAdminStickyRightCellClass`，不要只把操作列放在最后但随横向滚动移出视口。
- 后台数据页课程列表需要操作列时，操作列放在最右侧并固定，提供“查看课程”和“查看订单”文本按钮并承载跳转；课程列和订单数列保持普通黑色文本，不要额外加蓝色、underline 或点击行为。
- 后台数据页课程列表的课程列默认只展示课程名，不展示课程 ID；如需查看详情应通过右侧操作列进入课程详情。
- 后台数据页课程详情的基础信息区 label 和 value 应保持紧凑纵向间距，不要给 `dt` 添加固定大高度；优先使用 text-sm/20px line-height 和父级 `space-y-1` 控制间距。
- 后台管理页表格左下注脚（如总数、选中行数）优先通过 `AdminTableShell` 的 `footnote` 配置渲染，保持在 table 外侧 `16px`，文字使用 `--base-muted-foreground` 与 text-sm/normal/20px token。
- 后台管理页表格分页器优先通过 `AdminTableShell` 的 `pagination` 配置渲染；除非产品明确要求隐藏，否则即使只有一页也要展示分页器，不要在页面里用 `pageCount > 1` 或 `hideWhenSinglePage` 隐藏。
- 后台管理页表格分页器的末尾“下一页”需要和 table 右边缘视觉对齐时，优先在共享 `AdminPagination` 包装层处理最后一个分页按钮的右侧内边距，不要在单个页面里用 margin 偏移。
- 后台管理页分页器页码按钮统一使用 `36px` 宽高、`8px 16px` padding 和 `8px` gap；优先改共享 `PaginationLink` 的 icon 尺寸，不要在单个页面覆盖。
- admin 表格内只承载文本跳转的操作按钮默认去掉额外 padding、圆角和 hover 背景，并跟随单元格内容左对齐；不要沿用 ghost 按钮默认 hover 底色造成操作列视觉块状高亮。
- admin 表格单元格如果使用省略号截断，优先通过 `AdminTooltipText` 渲染完整内容，并确保 tooltip trigger 带 `block w-full min-w-0 truncate` 这类父宽度约束；当省略号由 `td` 或 table layout 外层裁剪产生、trigger 自身无法稳定判断 overflow 时，传入 `forceTooltip` 保证 hover 可查看完整内容。
- admin 页面标题右侧如果是弱化的文本工具操作，优先用 `Button variant="ghost"` 搭配 `--base-foreground`，图标和文字共用当前色，14px/medium/20px token 对齐，图标尺寸优先 `16px`，图文间距优先 `6px`。

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
- `skills/app-error-boundary-display/SKILL.md`
- `skills/admin-breadcrumbs/SKILL.md`
- `skills/admin-filter-layout/SKILL.md`
- `skills/admin-table-visual-system/SKILL.md`

## Usage Rules

- Module-level `AGENTS.md` files may reference skills from here, but they must not copy skill content back into directory rules.
- If the same frontend troubleshooting workflow repeats across tasks, add a focused skill instead of expanding `AGENTS.md`.

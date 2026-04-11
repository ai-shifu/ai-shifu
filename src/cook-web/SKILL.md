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
- 积分充值卡片优先使用自适应 grid 做 `auto-fit + minmax` 排布，保证大屏可多列、小屏可自动换列；单卡默认态统一走白底、基础边框和阴影，hover 只做浅色背景反馈，不要再为充值包单独维护一套漂浮感过强的旧样式。
- 积分充值卡片头部优先使用“双行信息”结构：首行是裸露图标加积分标题，次行是补充说明文案；不要给图标再包一层胶囊底板，标题需与图标垂直居中对齐。
- 后台账务页如果只有少量固定层级，优先用 breadcrumb 表达“首页 > 会员 > 积分详情”这类信息架构，不再用分段 tab 承担页面层级导航；其中中间层级在子页应保持可回跳。
- 账务页的面包屑与标题区需要分层控制：breadcrumb 统一使用 `14px` 信息密度，套餐主标题与说明文案则分别走 `36/40` 和 `16/24` 的层级，并保持 `20px` 垂直间距。
- 积分耗尽这类高频提醒不要继续沿用通用黄色告警条；优先改成白底信息卡，用更友好的标题和补充说明承载状态，不再暴露原始告警 code 文本。
- 套餐页顶部的周期/充值切换优先做成居中的分段控件：外层使用 `36px` 高的浅灰容器，内层选中项用白底、`8px` 圆角和 `shadow/sm`，并保证控件与下方卡片区至少留出 `32px` 间距。
- 当套餐页头部同时出现“标题说明”和“当前订阅摘要卡”时，优先保持标题区简洁；如果摘要卡会压缩核心套餐信息或干扰主视觉，应直接移除，而不是继续堆叠在标题和套餐列表之间。
- 积分详情这类二级页面头部优先只保留主标题；如果 breadcrumb 已经表达了层级，就不要再额外堆叠 badge 标签或重复性的说明文案。
- 积分详情页里的“总积分”摘要卡优先使用浅蓝背景的单层容器，标题/数值统一到 `24/32` 层级，说明文案走 `14/20`，右上角主按钮保持 `36px` 高、深色实底和 `shadow/xs`。
- 积分详情里的余额分类表优先做成“无外壳表格”：不要再包白底圆角框，直接用 `40px` 高的表头、`1px` 分隔线和单元格 `8px` 水平 padding；帮助 icon 使用 `16px` 的低对比度样式即可。
- 后台账务页如果核心任务已经聚焦到套餐/积分详情本身，顶部的营销型 Hero、统计概览和 capability summary 应优先移除，避免把真正的操作内容压到首屏下方。
- 积分详情页底部的活动区如果只需要表达“积分用了什么、何时发生、变更多少”，优先收敛成单个三列表格；付款记录和详情抽屉这类辅助模块可以先移除，避免与核心积分信息并列竞争注意力。
- 积分详情页的使用记录表默认按 `page_size=10` 拉取，并在表格底部提供页码分页器；翻页应直接驱动新的 `page_index` 请求，而不是一次性拉全量后前端切片。
- 后台页面如果需要整页滚动，优先让 `admin/layout` 的右侧主内容容器承担 `overflow-y-auto`，并把左右 `padding` 放到内层最大宽度容器里；业务页面本身不要再套一层整页 `overflow-auto`，避免滚动条掉进内容留白区域。
- 套餐卡片里如果按钮处于“当前使用 / 当前套餐”这类不可点击状态，但用户仍可能疑惑为什么不能操作，优先给 disabled 按钮补一个 hover tooltip，并把提示文案放进国际化配置。

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

# Admin 后台设计规范

本文档用于约束 `/admin` 后台所有现有页面和未来新增页面的设计风格、布局结构与组件复用方式。所有 admin 页面应优先复用本次 UI 升级中新增或改造的共享组件，避免在单个页面内重复拼装近似结构或局部覆盖样式。

## 1. 设计目标

- 保持所有 `/admin` 页面在布局、标题、面包屑、筛选器、表格、分页、数据卡片、操作按钮上的视觉一致性。
- 优先使用项目已有 CSS 变量和 Tailwind class，减少硬编码色值、字号、阴影和边距。
- admin 页面新增能力时，优先扩展共享组件能力，而不是在具体页面复制样式。
- 页面结构要适配现有后台工作台场景：左侧固定导航，右侧内容区滚动。
- 所有用户可见文案必须走 i18n，不允许在组件内硬编码中文或英文文案。

## 2. 基础页面布局

### 2.1 Admin Layout

所有 `/admin` 页面默认处于 `src/app/admin/layout.tsx` 提供的后台布局中：

- 左侧导航栏固定宽度：`280px`
- 右侧内容区：
  - 背景：`bg-background`
  - 横向溢出隐藏：`overflow-x-hidden`
  - 纵向滚动：`overflow-y-auto`
- 内容容器：
  - 最大宽度：`max-w-6xl`
  - 横向居中：`mx-auto`
  - 页面内边距：`px-6 py-[22px]`
  - 高度继承：`h-full`
  - 页面级子容器可使用 `flex h-full flex-col`

新增 admin 页面不要额外在页面根部叠加大面积 padding。若需要局部间距，应在页面内部具体区块控制。

### 2.2 页面根结构建议

列表页推荐结构：

```tsx
<div className='flex h-full flex-col'>
  <AdminBreadcrumb items={[{ label: pageTitle }]} />
  <AdminTitle
    title={pageTitle}
    actions={actions}
  />
  {filters}
  {summaryCards}
  {table}
</div>
```

详情页推荐结构：

```tsx
<div className='flex h-full flex-col'>
  <AdminBreadcrumb
    items={[{ label: parentTitle, href: parentHref }, { label: currentTitle }]}
  />
  <AdminTitle
    title={currentTitle}
    actions={actions}
  />
  {summaryCards}
  {detailSections}
</div>
```

## 3. 面包屑

所有 admin 页面必须使用：

```text
src/app/admin/components/AdminBreadcrumb.tsx
```

### 3.1 使用规则

- 所有 `/admin` 页面都必须展示面包屑。
- 面包屑必须独占页面内容区最顶端的一行。
- `首页` 链接固定指向 `/admin`。
- 如果调用方未传入 `/admin`，`AdminBreadcrumb` 会自动补齐首页。
- 列表页结构：`首页 > 当前页`
- 详情页结构：`首页 > 上级页 > 当前页`
- 最后一项为当前页，不可点击。
- 只有一个面包屑项时，当前项使用弱提示样式。
- 面包屑下方到标题或内容区的间距统一由 `AdminBreadcrumb` 控制，默认 `mb-[22px]`。

### 3.2 文案规则

- 面包屑文案必须使用 i18n。
- 新增文案时同步更新：
  - `src/i18n/<locale>/...`
  - `src/cook-web/src/types/i18n-keys.d.ts`

## 4. 页面标题区

所有 admin 页面标题区必须优先使用：

```text
src/app/admin/components/AdminTitle.tsx
```

### 4.1 标题样式

统一标题规格：

- 字号：`var(--heading-md-font-size, 30px)`
- 字重：`var(--heading-md-font-weight, 700)`
- 行高：`var(--heading-md-line-height, 36px)`
- 颜色：`var(--base-foreground, #0A0A0A)`

### 4.2 标题布局

`AdminTitle` 负责承接：

- `title`
- `description`
- `actions`
- `tabs`

不要在页面里手写重复的标题行布局。

标题区默认：

- 上下内边距：`py-6`
- 左右内边距：`pl-0 pr-0`
- 标题与右侧操作区在大屏下左右分布
- 小屏下垂直排列

### 4.3 右侧操作区

- 页面主操作按钮放在 `AdminTitle.actions` 中。
- 主 CTA 使用默认 `Button` 样式，保持主按钮视觉权重。
- 弱操作使用 `Button variant="ghost"` 或 `variant="outline"`。
- 右侧操作不额外添加右侧 padding，确保和表格、卡片右边缘对齐。

## 5. Tabs 规范

### 5.1 大号标题 Tabs

如果页面使用大号 tab 代替普通标题，使用 `AdminTitle` 暴露的 headline tabs class：

```text
ADMIN_TITLE_HEADLINE_TABS_LIST_CLASSNAME
ADMIN_TITLE_HEADLINE_TABS_TRIGGER_CLASSNAME
ADMIN_TITLE_HEADLINE_TABS_TRIGGER_STYLE
```

视觉规则：

- tab 字号跟随标题：`30px`
- active 状态使用黑色下划线
- 下划线高度：`4px`
- 下划线与文字底部间距：约 `12px`
- tab 容器不使用默认背景和圆角

### 5.2 普通二选一 Tabs

例如 `/admin` 课程首页的“全部 / 归档”：

- 外层圆角：`10px`
- 背景：`var(--base-muted, #F5F5F5)`
- padding：`3px`
- trigger 圆角：`8px`
- trigger padding：`4px 8px`
- 文字：`14px / 20px / 500`
- active 状态：
  - 背景白色
  - 1px 边框
  - 使用 `shadow-sm` 变量阴影

课程首页这类 tabs 与工具行默认不额外添加上下 padding，底部间距保持 `32px`。

## 6. 筛选器

后台筛选区域优先使用：

```text
src/app/admin/components/AdminFilter.tsx
```

### 6.1 使用场景

- 用户列表筛选
- 订单筛选
- 数据统计筛选
- 运营后台筛选
- 未来新增后台列表页筛选

不要在页面内重复写筛选项 label、按钮组、展开/收起布局。

### 6.2 布局规则

收起态：

- 默认展示主要筛选项，默认数量由 `collapsedCount` 控制。
- `xl` 及以上横向三列布局。
- `xl` 以下纵向排列。
- 操作按钮位于右侧。

展开态：

- 展示全部筛选项。
- 筛选项使用三列网格。
- 操作按钮仍靠右。

### 6.3 筛选项 label

统一样式：

- 字号：`var(--text-sm-font-size, 14px)`
- 字重：`var(--font-weight-medium, 500)`
- 行高：`var(--text-sm-line-height, 20px)`
- 颜色：`var(--base-foreground, #0A0A0A)`

如果需要 label 纵向对齐，通过 `labelClassName`、`collapsedLabelClassName`、`expandedLabelClassName` 传入固定宽度，不要在具体页面硬写多套布局。

### 6.4 操作按钮

按钮顺序：

1. 重置
2. 查询
3. 展开 / 收起

规则：

- 重置和查询均使用 `Button size="sm"`
- 左右内边距统一 `px-4`
- 展开 / 收起使用 `variant="ghost"`
- 展开按钮颜色使用 `--base-foreground`
- 展开按钮与查询按钮间距保持 `24px`
- chevron 图标使用 `h-4 w-4`

当筛选项数量不超过收起态展示数量时，不展示展开 / 收起按钮。

## 7. 表格系统

后台所有表格优先使用：

```text
src/app/admin/components/AdminTableShell.tsx
src/app/admin/components/adminTableStyles.ts
src/components/ui/Table.tsx
```

不要在页面内重复写表格外框、表头背景、单元格高度、分页容器等视觉样式。

### 7.1 表格外框

统一外框：

- 圆角：`rounded-xl`
- 边框：`var(--base-border, #E5E5E5)`
- 背景：白色 / `var(--base-card, #FFF)`
- 阴影：默认无阴影
- overflow 由具体表格滚动容器控制

### 7.2 表头

表头统一规则：

- 高度：`40px`
- 最小宽度：`85px`
- 背景：`var(--base-muted, #F5F5F5)`
- 字号：`14px`
- 字重：`500`
- 行高：`20px`
- 颜色：`var(--base-foreground, #0A0A0A)`
- 左右内边距：`8px`
- 默认左对齐
- 首列表头左侧 padding：`16px`

### 7.3 表格单元格

tbody 单元格统一规则：

- 高度：`53px`
- 最小宽度：`85px`
- 内边距：`8px`
- 字号：`14px`
- 字重：`400`
- 行高：`20px`
- 颜色：`var(--base-foreground, #0A0A0A)`
- 默认左对齐
- 垂直居中
- 不展示右侧 border
- 首列左侧 padding：`16px`

不要在 `td` 上强制 `flex`，避免破坏原生 table 布局。如需某一列右对齐，仅在单元格内容层包一层元素处理。

### 7.4 行 hover

- 普通行 hover 背景使用 `var(--base-muted, #F5F5F5)`。
- sticky 操作列也要同步 hover，不允许固定列保持白底造成断层。
- loading 骨架屏行需要禁用 `tr:hover` 和 `td:hover` 背景，避免翻页时出现整行灰色条。

### 7.5 空态与 loading

`AdminTableShell` 负责：

- `loading`
- `emptyContent`
- `emptyColSpan`
- `pagination`
- `footnote`
- `footer`

页面不要在表格外另写重复空态结构。

loading 态需要保持底部分页和说明时，传入 `showFooterWhenLoading`。

### 7.6 表格注脚

表格底部左侧说明、总数、统计范围说明等，优先使用 `AdminTableShell.footnote`。

统一样式：

- 字号：`14px`
- 字重：`400`
- 行高：`20px`
- 颜色：`var(--base-muted-foreground, #737373)`

例如数据页课程列表：

```text
课程数：37（统计范围说明...）
```

### 7.7 分页器

表格分页统一走：

```tsx
<AdminTableShell pagination={paginationConfig} />
```

底层使用：

```text
src/app/admin/components/AdminPagination.tsx
```

规则：

- 分页位于表格底部右侧。
- 页码按钮统一 `36px` 宽高。
- 页码按钮 padding：`8px 16px`
- gap：`8px`
- “下一页”末尾需要和表格右边缘视觉对齐，统一由 `AdminPagination` 处理，不在页面里用 margin 偏移。
- 除非产品明确要求隐藏，否则后台列表表格即使只有一页也默认展示分页器。

### 7.8 操作列

所有 admin 表格操作列都应固定在右侧。

表头使用：

```tsx
getAdminStickyRightHeaderClass();
```

单元格使用：

```tsx
getAdminStickyRightCellClass();
```

规则：

- 操作列放在最右侧。
- 横向滚动时操作列始终可见。
- 文本型操作按钮默认去掉额外 padding、圆角和 hover 背景。
- 不要沿用 `ghost` 按钮默认 hover 底色，避免形成块状高亮。
- 操作列不应通过普通最后一列替代 sticky right。

### 7.9 文本溢出

长文本、省略号、课程名、用户信息等，优先使用：

```text
src/app/admin/components/AdminTooltipText.tsx
```

规则：

- 能截断的文本需要 hover 查看完整内容。
- 如果省略由外层 table layout 裁剪导致无法可靠判断 overflow，可启用强制 tooltip。
- 多行信息单元格应分别给关键文本加 tooltip，而不是只包外层。

## 8. 数据卡片

后台数据统计卡片统一使用：

```text
src/app/admin/components/AdminCountCard.tsx
```

### 8.1 使用场景

- 数据页 KPI
- 课程详情核心指标
- 运营后台核心统计
- 未来新增的统计概览卡片

### 8.2 视觉规则

容器：

- padding：`24px`
- 圆角：`var(--border-radius-rounded-xl, 14px)`
- 边框：`var(--base-border, #E5E5E5)`
- 背景：`var(--base-card, #FFF)` + 轻微渐变
- 阴影：`shadow-sm` 对应 CSS 变量

标题：

- 字号：`14px`
- 字重：`400`
- 行高：`20px`
- 颜色：`var(--base-muted-foreground, #737373)`

数值：

- 字号：`30px`
- 字重：`600`
- 行高：`36px`
- 颜色：`var(--base-card-foreground, #0A0A0A)`
- 标题与数值间距：`6px`

## 9. 课程首页卡片

`/admin` 课程首页课程卡片为后台卡片视觉基准之一，未来类似“卡片型入口”可参考该规范。

### 9.1 卡片容器

统一规则：

- 最小高度：`118px`
- 圆角：`var(--border-radius-rounded-xl, 14px)`
- 边框：`var(--base-border, #E5E5E5)`
- 背景：`var(--base-card, #FFF)`
- 阴影：`shadow-sm` CSS 变量
- hover：使用低透明度 `primary` 背景，不额外增强阴影，避免抖动

### 9.2 卡片内容

- 内边距：`16px`
- 整卡作为进入作者工作台的导航时，默认新标签页打开，避免打断当前筛选上下文。
- hover 菜单、更多操作必须阻止事件冒泡，避免触发整卡导航。

### 9.3 课程头像

- 尺寸：`28px x 28px`
- 圆角：`8px`
- 与课程名间距：`12px`
- 头像与课程名垂直居中
- 有头像时：`object-cover`
- 无头像时：
  - 背景：`#CFCED4`
  - 图标：`public/icons/logo.svg`
  - 图标尺寸：`16px x 19px`
  - 不再使用 `TrophyIcon` 作为占位图标

### 9.4 课程名

- 颜色：黑色
- 字号：`16px`
- 字重：`500`
- 行高：`20px`
- 单行省略

### 9.5 课程描述

- 距离头像 / 标题行：`16px`
- 颜色：`rgba(10, 10, 10, 0.65)`
- 字号：`14px`
- 字重：`400`
- 行高：`20px`
- 最多三行截断

## 10. 积分与会员页面特殊规则

会员与积分页面同样属于 admin 后台页面，应遵循上述面包屑、标题、表格、分页和卡片规范。

### 10.1 积分购买页

- 当前页面标题优先通过面包屑承载。
- 页面主体不要再重复展示同名大标题，避免出现：
  - `首页 > 积分购买`
  - 下方又展示一个 `积分购买`

### 10.2 积分消耗明细表格

积分消耗明细表格应复用 `AdminTableShell` 和标准 `Table`。

规则：

- “消耗项”占最大宽度。
- “时间”列居中偏右。
- “数量”列贴近最右侧对齐。
- 数量列如需右对齐，只在内容层使用 `justify-end` 或 `ml-auto`。
- 时间列不要保留旧版 grid 表格中的 `text-right`、`justify-end`、`ml-auto`。
- loading 骨架屏行必须禁用 hover 背景，避免翻页时底部出现灰色条。

## 11. 按钮规范

### 11.1 主按钮

页面主 CTA 使用默认 `Button`：

```tsx
<Button size='sm'>新建课程</Button>
```

规则：

- 保持蓝底白字。
- 不要为了弱化视觉而使用 `outline`。
- 如果设计没有要求，不默认添加左侧图标。

### 11.2 弱按钮

弱操作使用：

```tsx
<Button variant='outline' />
<Button variant='ghost' />
```

适用场景：

- 返回
- 查看详情
- 展开 / 收起
- 弱化辅助入口

### 11.3 表格文本操作

表格里的文本操作按钮：

- 去掉额外 padding
- 去掉圆角
- 去掉 hover 背景
- 跟随单元格内容左对齐
- 需要 sticky right 时放在固定操作列中

## 12. 图标规范

- 14px 文字旁边的 chevron 图标统一使用 `h-4 w-4`。
- 图标容器使用 `items-center` 和 `leading-none`。
- 文本自身保留 `leading-5`，避免图标因继承文本行高导致视觉不对齐。

## 13. 响应式规则

admin 页面以桌面工作台为主，但仍需保持窄屏基本可用。

- 筛选器：
  - `xl` 及以上横向三列
  - `xl` 以下纵向排列
- 标题 actions：
  - 大屏右侧对齐
  - 小屏换行或垂直排列
- 表格：
  - 允许横向滚动
  - sticky 操作列保持可见
  - 不通过压缩字号破坏可读性
- 不使用 `vh`，如需视口高度使用 `dvh`。
- 不使用 `env(safe-area-inset-bottom)`。

## 14. i18n 与类型同步

新增或修改 admin 页面文案时，必须同步：

- `src/i18n/zh-CN/...`
- `src/i18n/en-US/...`
- `src/i18n/fr-FR/...`
- `src/cook-web/src/types/i18n-keys.d.ts`

新增 i18n key 后运行：

```bash
npm run i18n:keys
```

或项目对应的 key 生成脚本。

## 15. 新增 admin 页面检查清单

新增 `/admin` 页面时，应逐项检查：

- 是否使用 `AdminBreadcrumb`
- 是否使用 `AdminTitle`
- 是否复用 `AdminFilter`
- 是否复用 `AdminTableShell`
- 是否通过 `AdminTableShell.pagination` 渲染分页
- 表格操作列是否 sticky right
- 长文本是否使用 `AdminTooltipText`
- 数据卡片是否使用 `AdminCountCard`
- 页面文案是否走 i18n
- 是否避免硬编码颜色、字号、阴影
- 是否避免重复实现已有共享组件能力
- 是否运行相关 focused test 或 `npm run type-check`

## 16. 推荐组件索引

后台页面优先复用以下组件：

```text
src/app/admin/components/AdminBreadcrumb.tsx
src/app/admin/components/AdminTitle.tsx
src/app/admin/components/AdminFilter.tsx
src/app/admin/components/AdminTableShell.tsx
src/app/admin/components/AdminCountCard.tsx
src/app/admin/components/AdminPagination.tsx
src/app/admin/components/AdminTooltipText.tsx
src/app/admin/components/adminTableStyles.ts
```

除非有明确业务原因，不应在具体页面重新实现上述组件已覆盖的布局和视觉能力。

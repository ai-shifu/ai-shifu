# Admin Table Visual System

## 触发场景

- 修改后台管理页表格外框、表头、列对齐或通用表格容器样式时使用。
- 需要把多个后台页面的表格视觉收敛到共享样式时使用。

## 复用规则

- 后台管理页表格优先复用 `src/app/admin/components/AdminTableShell.tsx` 和 `src/app/admin/components/adminTableStyles.ts`，不要在单个页面重复写表格外框、表头 token 和 sticky 列样式。
- 表格外框边框统一使用 `--base-border`，表头背景统一使用 `--base-muted`，表头文字统一使用 `--base-foreground` 与 text-sm/medium/20px line-height token。
- 表头单元格默认高度为 `40px`、最小宽度为 `85px`、左右内边距为 `8px`、文字左对齐；不要为了模拟设计稿额外添加拖拽列或 checkbox 选择列。
- tbody 单元格默认保持原生 table-cell 布局，高度为 `53px`、最小宽度为 `85px`、内边距为 `8px`、文字左对齐、垂直居中，并使用 `--base-foreground` 与 text-sm/normal/20px line-height token；不要在 `td` 上强制 flex，避免破坏表格列布局。
- 单元格默认不展示右侧 border；页面内遗留的 `border-r`、`text-center` 应由共享表格样式覆盖，避免逐页重复清理。
- 首列左侧间距优先用 `16px`，避免表格左边缘过挤；整行 hover 背景必须覆盖 sticky 操作列，不要让固定列保持白底。
- 单元格出现省略号时优先复用 `AdminTooltipText` 暴露完整文本；多行信息单元格需要分别给各行补 tooltip，避免只处理外层单元格导致具体文本仍不可见。
- 分页器优先通过 `AdminTableShell` 的 `pagination` 配置统一渲染在表格底部右侧；除非产品明确要求隐藏，否则单页也展示分页器，不要在页面里用 `pageCount > 1` 或 `hideWhenSinglePage` 隐藏。
- 分页器末尾“下一页”需要和 table 右边缘视觉对齐时，优先在共享 `AdminPagination` 包装层处理最后一个分页按钮的右侧内边距，不要在单个页面里用 margin 偏移。
- 分页器页码按钮统一使用 `36px` 宽高、`8px 16px` padding 和 `8px` gap；优先改共享 `PaginationLink` 的 icon 尺寸，不要在单个 admin 页面覆盖页码按钮。
- 表格内只承载文本跳转的操作按钮默认去掉额外 padding、圆角和 hover 背景，并跟随单元格内容左对齐；避免 `ghost` 按钮默认 hover 底色形成块状高亮。
- 如果页面需要列宽拖拽，只复用 `ADMIN_TABLE_RESIZE_HANDLE_CLASS` 作为交互热区，视觉分隔仍由共享表头与边框样式控制。

## 验收要点

- 表头行背景、表头文字样式和表格边框在不同 admin 页面保持一致。
- 新增 admin 表格时默认不包含设计稿中用于示意的拖拽手柄列和勾选列，除非业务明确需要行排序或批量选择。
- 改动后至少运行受影响页面的 focused test 或 `npm run type-check`，无法运行时在最终说明中明确原因。

# Admin Filter Layout

## 触发场景

- 修改后台管理页的筛选区域布局、筛选项 label、查询/重置/展开按钮样式时使用。
- 需要把多个后台页面的筛选器收敛到共享布局时使用。

## 复用规则

- 后台管理页筛选区优先复用 `src/app/admin/components/AdminFilter.tsx`，不要在页面内重复拼装 label、按钮组和展开/收起布局。
- 筛选项 label 统一使用 `--base-foreground`、`--text-sm-font-size`、`--font-weight-medium`、`--text-sm-line-height` 这组 token；同一筛选区需要纵向对齐时，通过 `expandedLabelClassName` 或 `labelClassName` 传入固定宽度和右对齐，避免收起态第一行被固定 label 宽度额外顶开。
- 查询和重置按钮保持 `Button size="sm"`，左右内边距统一覆盖为 `px-4`；展开/收起按钮颜色使用 `--base-foreground`，与查询按钮间距保持 `24px`，文字和 chevron 间距保持 `4px`，hover 区域要保留可见的左内边距。
- 具体输入框、下拉框、日期筛选等控件样式由调用方保留，`AdminFilter` 只负责外层布局和通用动作区。

## 验收要点

- 收起态默认只展示主要筛选项，操作按钮位于右侧；展开态展示全部筛选项，操作按钮仍靠右，筛选器外层默认不额外添加上下 padding。
- 不要为了适配单个页面在共享组件里写业务字段名；字段顺序、控件内容和默认展示数量由调用方传入。
- 改动后至少运行受影响页面的 focused test 或 type-check，无法运行时在最终说明中明确原因。

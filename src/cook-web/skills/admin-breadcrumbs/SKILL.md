# Admin Breadcrumbs

## 触发场景

- 修改 `/admin` 下页面、标题、导航层级或新增后台页面时使用。
- 调整课程、订单、数据、运营、会员与积分等后台页面面包屑时使用。

## 规则

- `/admin` 后台页面优先复用 `src/app/admin/components/AdminBreadcrumb.tsx`，不要在各页面重复拼装 shadcn breadcrumb 结构。
- `/admin` 页面标题区优先复用 `src/app/admin/components/AdminTitle.tsx`，统一承接标题、右侧操作区和顶部 tab，不要在页面里重复拼接标题行布局。
- `/admin` 后台子页面内容区统一使用 `padding: 22px 24px`，优先通过 `src/app/admin/layout.tsx` 收口，不要在页面头部额外叠加顶部留白。
- 面包屑必须独占页面内容区最顶端的一行；标题、筛选器、按钮等操作区放到下一行。
- 面包屑字号保持 `14px`，并且面包屑所在行距离下方内容保持 `22px`，优先在通用组件中统一处理。
- 标题区使用 `30px / 36px / 700` 的统一 heading 规格，标题容器内边距统一为 `24px`。
- 所有 `/admin` 页面面包屑都要带 `首页`，并且 `首页` 链接固定跳转 `/admin`。
- `首页` 后面的层级按页面关系继续追加；列表页展示 `首页 > 当前页`，详情页或子页面展示 `首页 > 上级页 > 当前页`。
- 只有一个面包屑项时，该项使用灰色弱提示样式，不使用当前页黑色强调。
- 会员与积分页面也按后台页面处理，使用同一套 `AdminBreadcrumb`；如果页面内容受 tab 控制，面包屑文案要跟随当前 tab 状态切换。
- 如果标题区域使用大号 tab 代替标题，active tab 使用黑色 `4px` 下划线，且下划线与文字底部间距为 `12px`。
- 新增面包屑文案时同步更新 `src/i18n/<locale>/...` 和 `src/cook-web/src/types/i18n-keys.d.ts`。

## 验证

- 修改后优先运行相关页面测试；如果新增 i18n key，运行 `node scripts/generate_i18n_keys.js`。
- 面包屑需要检查单项、两项和多项都能渲染，且最后一项不可点击。

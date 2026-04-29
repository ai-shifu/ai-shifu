---
name: fullscreen-dialog-portal
description: 当 cook-web 页面在浏览器 fullscreen 场景下需要展示基于 Dialog 的支付弹窗、设置弹窗或业务弹层时，使用本技能排查 portal 容器是否落在全屏节点外。
---

# 浏览器全屏 Dialog Portal

## 核心规则

- 浏览器 fullscreen 模式下，只有全屏节点及其后代会继续可见；基于 `Dialog` 的弹层若仍 portal 到 `document.body`，就会出现“状态已打开但界面看不到”的现象。
- 优先在通用弹层封装层处理 fullscreen portal 容器，不要在每个业务弹窗里各自复制一套 `document.fullscreenElement` 监听逻辑。
- 若通用封装允许外部传入 `container`，fullscreen 自动兜底必须保留显式覆盖能力，避免影响已有定制挂载点。
- 监听 fullscreen 状态变化时，要兼容进入和退出全屏两个方向，确保弹层在切换后仍能落到当前正确的容器上。
- 若首帧就可能在 fullscreen 内打开弹窗，容器解析不能只依赖异步 effect；需要提供首屏同步兜底，避免弹窗先挂到 `body` 导致闪烁或不可见。
- 若 fullscreen 的宿主节点承载了播放器或阅读器主容器，切换 lesson / chapter 时不要用 loading skeleton 把该宿主整棵卸载掉；应保留原节点并在内部叠加 loading，否则浏览器会因 fullscreen owner 被移除而自动退出全屏。
- 不止 `Dialog`，像追问浮层、评分卡片、引导卡片这类普通业务浮层若定位依赖 `absolute/fixed`，在 fullscreen 下也要确认它们是否仍渲染在 fullscreen 视口树内；若不是，同样需要 portal 到 `slide__viewport` 之类的宿主节点。
- 移动端基于 `src/components/ui/Dialog.tsx` 的基础弹窗默认要保留稳定的视口边距，优先在通用 `DialogContent` 上统一约束宽度，而不是在每个业务弹窗里分别补 `w-[calc(100vw-32px)]`。

## 工作流

1. 先确认异常弹层是否基于 `src/components/ui/Dialog.tsx` 这类通用封装，而不是业务侧自己 `createPortal`。
2. 复现时重点观察触发弹层时页面是否已经进入浏览器 fullscreen，而不是仅仅组件内部切换了“全屏样式”。
3. 若是浏览器 fullscreen，优先检查 `DialogPortal` 的 `container` 是否仍为空，导致默认挂到 `body`。
4. 在通用封装层补齐 fullscreen 容器解析与 `fullscreenchange` 监听，并保留外部 `container` 的覆盖入口。
5. 若问题发生在章节切换、重新加载或数据刷新后，再检查 fullscreen owner 在 loading 阶段是否被条件渲染卸载；优先改成保留宿主节点、仅在内部显示 loading overlay。
6. 修改后至少验证一次“进入 slide fullscreen 后直接触发支付弹窗/业务弹窗”或“fullscreen 中切换章节仍保持屏幕状态”的路径，并补一次定向类型检查。

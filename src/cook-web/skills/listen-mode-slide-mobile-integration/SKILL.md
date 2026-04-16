---
name: listen-mode-slide-mobile-integration
description: 当 learner 端听课模式需要接入 markdown-flow-ui 的移动端播放器新能力时使用本技能。覆盖横竖屏状态透传、自定义横屏 header、以及播放器文案国际化接入。
---

# 听课模式 Slide 移动端接入

## 核心规则

- 优先在 `ListenModeSlideRenderer` 这一层完成 `Slide` 新 props 的业务接入，再按需把状态回调向 `NewChatComp`、`ChatUi`、页面层逐层透传。
- 横屏 header 的业务内容由 ai-shifu 自己渲染，不要把头像、标题等默认值写回 `markdown-flow-ui`。
- 播放器文案必须走 `src/i18n/<locale>/modules/chat.json`，不要在组件里写死字符串。
- 当 `Slide` 新增 `playerTexts.subtitleLabel`、`playerTexts.subtitleToggleAriaLabel` 这类播放器字幕文案时，ai-shifu 侧也要在 `ListenModeSlideRenderer` 同步透传，并补齐 `chat.json` 与 `i18n-keys.d.ts`，避免 history slide 设置面板回退到英文。
- 若 `markdown-flow-ui` 发布版类型暂未同步，使用 `src/cook-web/src/types/markdown-flow-ui.d.ts` 做最小化 module augmentation，避免覆盖上游完整声明。
- 课程级展示信息优先复用 `useCourseStore`，章节/课时标题优先复用当前 `lessonTitle` 或 `sectionTitle`，不要在聊天组件里重复请求课程信息。
- 当移动端 learner header 需要与 fullscreen header 对齐头像/课程标题时，优先直接复用 `useCourseStore` 的 `courseAvatar/courseName`，并把 header 高度抽成共享 CSS 变量，避免 `page`、`NavDrawer`、`ChatUi` 各自写死不同高度。
- 若业务层的悬浮入口需要跟随移动端展示模式切换定位，优先在 `ListenModeSlideRenderer` 本地消费 `onMobileViewModeChange` 维护 view mode，再用 modifier class 做定位差异，不要把这种纯展示状态继续上抛到更多层。
- 当新增 `onMobileViewModeChange` 这类上抛回调并逐层透传时，中间层组件优先保持可选参数，并为页面层保留安全退化，避免只改一半导致 `next build` 在 JSX 调用点直接报 props 缺失。
- 若横屏悬浮入口或面板通过 portal 挂到 `Slide` 内部视口，业务层要为 portal 容器尚未就绪的首帧提供回退渲染，避免按钮因容器时序问题直接消失。
- 若 `Slide` 的 fullscreen 态来自“设备自动检测 + 用户手动切换”混合模型，业务层消费 `onMobileViewModeChange` 时应以“当前生效态”为准，不要再额外假设物理横屏一定不可退出。
- 当移动端听课模式需要兼容横屏 fullscreen 场景下的 `dvh` 视口误差时，优先在页面根节点切换 class，并通过全局 CSS 变量统一把相关高度从 `dvh` 映射到 `vh`，不要在多个组件里散落同一套条件判断。

## 工作流

1. 先确认 `Slide` 的新增能力已经在 `markdown-flow-ui` 暴露，重点核对 `fullscreenHeader`、`playerTexts`、`onMobileViewModeChange` 的真实类型。
2. 若上游 `markdown-flow-ui` 已把移动端模式字段从 `landscape / portrait` 改为 `fullscreen / nonFullscreen`，ai-shifu 侧的 handler、props、state 与文案字段也要同步换名，例如 `onListenMobileViewModeChange`、`mobileViewMode`、`fullscreenHeader`、`fullscreenLabel`、`nonFullscreenLabel`。
3. 在 ai-shifu 的听课模式接入层补齐 props，并把需要给外部感知的状态回调逐层向上透传。
4. 若需要切换整页 `dvh/vh` 计算，优先把 fullscreen + landscape + mobile 的命中条件收敛到页面根节点 class，再由全局变量驱动页面与弹层样式。
5. 使用课程 store 和当前 lesson 标题组装横屏 header 内容，保证无数据时仍可安全退化。
6. 把播放器设置文案补到 `chat` i18n 命名空间，并同步更新生成型的 key 类型文件。
7. 变更后至少执行一次定向类型检查，确认 module augmentation 和新 props 没有引入类型回归。

---
name: listen-mode-slide-mobile-integration
description: 当 learner 端听课模式需要接入 markdown-flow-ui 的移动端播放器新能力时使用本技能。覆盖横竖屏状态透传、自定义横屏 header、以及播放器文案国际化接入。
---

# 听课模式 Slide 移动端接入

## 核心规则

- 优先在 `ListenModeSlideRenderer` 这一层完成 `Slide` 新 props 的业务接入，再按需把状态回调向 `NewChatComp`、`ChatUi`、页面层逐层透传。
- 横屏 header 的业务内容由 ai-shifu 自己渲染，不要把头像、标题等默认值写回 `markdown-flow-ui`。
- 播放器文案必须走 `src/i18n/<locale>/modules/chat.json`，不要在组件里写死字符串。
- learner 端 header 上的学习模式名称、切换学习模式按钮、目录开关 `aria-label` 也必须走 `module.chat` 命名空间；共享 TS 模块只保留 mode 和 i18n key，禁止导出已经翻译好的“听课/阅读”等渲染文案。
- 若需要抽象共享翻译逻辑给多个组件复用，优先在共享 helper 里直接写 `t('module.chat.xxx')` 这类字面量调用；不要只导出 key 常量再在调用方 `t(dynamicKey)`，否则 `check_translation_usage.py` 的静态扫描会把文案误判为未使用。
- 当 `Slide` 新增 `playerTexts.subtitleLabel`、`playerTexts.subtitleToggleAriaLabel` 这类播放器字幕文案时，ai-shifu 侧也要在 `ListenModeSlideRenderer` 同步透传，并补齐 `chat.json` 与 `i18n-keys.d.ts`，避免 history slide 设置面板回退到英文。
- 若 `markdown-flow-ui` 发布版类型暂未同步，使用 `src/cook-web/src/types/markdown-flow-ui.d.ts` 做最小化 module augmentation，避免覆盖上游完整声明。
- 课程级展示信息优先复用 `useCourseStore`，章节/课时标题优先复用当前 `lessonTitle` 或 `sectionTitle`，不要在聊天组件里重复请求课程信息。
- 当移动端 learner header 需要与 fullscreen header 对齐头像/课程标题时，优先直接复用 `useCourseStore` 的 `courseAvatar/courseName`，并把 header 高度抽成共享 CSS 变量，避免 `page`、`NavDrawer`、`ChatUi` 各自写死不同高度。
- 当移动端 learner header 需要切换学习模式时，优先使用常驻的内联 segmented switch，而不是额外的图标下拉菜单；短文案要走 `module.chat` 下的独立 i18n key（例如“听 / 读”），并把 `BETA` 徽标挂在“听”按钮的右上角。
- learner header 里的 `BETA` 徽标若需要视觉升级，优先在共享 `HeaderBetaBadge` 组件内统一处理，并复用主题色变量 `primary / base-primary-foreground`、统一圆角与 shadow token，不要在 `LearningModeSwitch` 或其他 header 调用方各自写一份 badge 样式。
- 当 learner header 的学习模式 segmented switch 需要调整“读 / 听”的左右顺序时，优先修改共享 `learningModeOptions` 中的选项顺序，让移动端和桌面端一起复用同一套展示顺序，不要在单个组件里额外写条件分支。
- 当桌面端 learner header 也需要展示课程信息或学习模式切换时，优先直接复用移动端已经抽好的共享头部组件与 segmented switch，不要再单独维护一套桌面端按钮文案、图标按钮或课程标题样式。
- 当桌面端顶部 header 已经展示课程信息时，左侧 nav drawer 不要再重复渲染课程头像和课程标题；若桌面端 segmented switch 视觉偏小，优先通过共享开关组件增加桌面尺寸变体，而不是再派生一套桌面专用按钮实现。
- 当桌面端顶部课程标题或学习模式开关尺寸需要微调时，优先通过共享头部组件的样式透传能力和共享开关的 `desktop` 尺寸变体做定向覆盖，不要回退成桌面端单独实现。
- 当 learner 学习页需要记住课程级“听 / 读”学习模式偏好时，优先按 `courseId` 维度使用 `localStorage` 保存，并把“读取缓存决定初始模式”和“用户切换后回写缓存”都收敛在学习页 `layout` 或共享 storage helper 中，避免按钮组件直接耦合存储细节。
- 若业务层的悬浮入口需要跟随移动端展示模式切换定位，优先在 `ListenModeSlideRenderer` 本地消费 `onMobileViewModeChange` 维护 view mode，再用 modifier class 做定位差异，不要把这种纯展示状态继续上抛到更多层。
- 当新增 `onMobileViewModeChange` 这类上抛回调并逐层透传时，中间层组件优先保持可选参数，并为页面层保留安全退化，避免只改一半导致 `next build` 在 JSX 调用点直接报 props 缺失。
- 若横屏悬浮入口或面板通过 portal 挂到 `Slide` 内部视口，业务层要为 portal 容器尚未就绪的首帧提供回退渲染，避免按钮因容器时序问题直接消失。
- 若 `Slide` 的 fullscreen 态来自“设备自动检测 + 用户手动切换”混合模型，业务层消费 `onMobileViewModeChange` 时应以“当前生效态”为准，不要再额外假设物理横屏一定不可退出。
- 当移动端听课模式需要兼容横屏 fullscreen 场景下的 `dvh` 视口误差时，优先在页面根节点切换 class，并通过全局 CSS 变量统一把相关高度从 `dvh` 映射到 `vh`，不要在多个组件里散落同一套条件判断。
- 当移动端听课模式的交互浮层输入框因为键盘弹起而失焦时，优先检查 `page` 或宿主层是否把键盘触发的 `resize` / `visualViewport.resize` 当成横竖屏变化处理；输入框聚焦期间应过滤这类 resize，避免整页布局状态重算导致浮层或输入组件重渲染。
- 当移动端听课模式里单个 markdown/code element 把页面撑宽时，优先在 ai-shifu 的 `ListenModeRenderer.scss` 约束 slide 外层 flex/grid 链路的 `min-width: 0`、`max-width: 100%` 和局部 `overflow-x`，让代码块内部滚动，不要先改 `markdown-flow-ui`。

## 工作流

1. 先确认 `Slide` 的新增能力已经在 `markdown-flow-ui` 暴露，重点核对 `fullscreenHeader`、`playerTexts`、`onMobileViewModeChange` 的真实类型。
2. 若上游 `markdown-flow-ui` 已把移动端模式字段从 `landscape / portrait` 改为 `fullscreen / nonFullscreen`，ai-shifu 侧的 handler、props、state 与文案字段也要同步换名，例如 `onListenMobileViewModeChange`、`mobileViewMode`、`fullscreenHeader`、`fullscreenLabel`、`nonFullscreenLabel`。
3. 在 ai-shifu 的听课模式接入层补齐 props，并把需要给外部感知的状态回调逐层向上透传。
4. 若需要切换整页 `dvh/vh` 计算，优先把 fullscreen + landscape + mobile 的命中条件收敛到页面根节点 class，再由全局变量驱动页面与弹层样式。
5. 使用课程 store 和当前 lesson 标题组装横屏 header 内容，保证无数据时仍可安全退化。
6. 把播放器设置文案补到 `chat` i18n 命名空间，并同步更新生成型的 key 类型文件。
7. 变更后至少执行一次定向类型检查，确认 module augmentation 和新 props 没有引入类型回归。

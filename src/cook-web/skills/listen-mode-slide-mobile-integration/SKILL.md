---
name: listen-mode-slide-mobile-integration
description: 当 learner 端听课模式需要接入 markdown-flow-ui 的移动端播放器新能力时使用本技能。覆盖横竖屏状态透传、自定义横屏 header、以及播放器文案国际化接入。
---

# 听课模式 Slide 移动端接入

## 核心规则

- 优先在 `ListenModeSlideRenderer` 这一层完成 `Slide` 新 props 的业务接入，再按需把状态回调向 `NewChatComp`、`ChatUi`、页面层逐层透传。
- 横屏 header 的业务内容由 ai-shifu 自己渲染，不要把头像、标题等默认值写回 `markdown-flow-ui`。
- 播放器文案必须走 `src/i18n/<locale>/modules/chat.json`，不要在组件里写死字符串。
- 若 `markdown-flow-ui` 发布版类型暂未同步，使用 `src/cook-web/src/types/markdown-flow-ui.d.ts` 做最小化 module augmentation，避免覆盖上游完整声明。
- 课程级展示信息优先复用 `useCourseStore`，章节/课时标题优先复用当前 `lessonTitle` 或 `sectionTitle`，不要在聊天组件里重复请求课程信息。
- 若业务层的悬浮入口需要跟随横竖屏切换定位，优先在 `ListenModeSlideRenderer` 本地消费 `onMobileScreenModeChange` 维护 screen mode，再用 modifier class 做定位差异，不要把这种纯展示状态继续上抛到更多层。

## 工作流

1. 先确认 `Slide` 的新增能力已经在 `markdown-flow-ui` 暴露，重点核对 `landscapeHeader`、`playerTexts`、`onMobileScreenModeChange` 的真实类型。
2. 在 ai-shifu 的听课模式接入层补齐 props，并把需要给外部感知的状态回调逐层向上透传。
3. 使用课程 store 和当前 lesson 标题组装横屏 header 内容，保证无数据时仍可安全退化。
4. 把播放器设置文案补到 `chat` i18n 命名空间，并同步更新生成型的 key 类型文件。
5. 变更后至少执行一次定向类型检查，确认 module augmentation 和新 props 没有引入类型回归。

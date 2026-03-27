---
name: chat-layout-width-detection
description: 当修复 ai-shifu 聊天页在移动端与桌面端布局判定不一致的问题时使用本技能。基于真实可见视口宽度而不是仅 `#root.clientWidth` 计算 `frameLayout`，在 `resize` 与 `visualViewport.resize` 时同步，并在断点纠正后关闭过期的移动端抽屉状态。
---

# 聊天布局宽度判定

## 核心规则

对于 `ai-shifu/src/cook-web/src/app/c/[[...id]]`，优先把聊天布局视为“视口问题”，而不只是“容器问题”。

## 工作流

1. 从多个 DOM 来源计算布局宽度：`#root.clientWidth`、`document.documentElement.clientWidth`、`window.innerWidth`、`window.visualViewport?.width`。
2. 选择最小的正数宽度作为有效布局宽度，避免移动端 WebView 在“桌面网站模式”下被误判为桌面布局。
3. 将断点映射集中维护在 `uiConstants`，并在 store 与页面间复用。
4. 在 `resize`、`orientationchange`、`visualViewport.resize` 时重新计算布局。
5. 当布局切换到移动端时，关闭遗留的“桌面态已打开抽屉”状态。
6. 为 `calcFrameLayout` 增加或更新测试，覆盖 root 节点缺失与移动端 WebView 容器宽度异常偏大的场景。

## 备注

- 不要仅依赖 `react-device-detect` 进行聊天布局切换。
- 注释保持英文，且避免在多个文件重复断点逻辑。

# lesson-reset-run-gating

## 适用场景

- 排查课程目录里的“重修/重置”按钮点击后，没有进入“思考中”也没有发送 `/run` 请求。
- 排查课节重置后，目录状态已变化，但聊天区没有自动重新开始生成内容。

## 核心检查点

- 先确认目录按钮只是触发重置链路，不是直接调用 `/run`；真正的自动开跑通常发生在 `useChatLogicHook` 的 `refreshData` 里。
- 重点检查 `lessonStatus` 是否仍然是 `completed`。如果 `isCompletedLesson` 为 `true`，`refreshData` 在空记录和非交互结尾两条分支里都会跳过 `runRef.current`。
- 处理这类问题时优先修正课节树中的本地状态，例如在确认重修后把目标课节手动更新为 `not_started`，而不是在聊天 hook 里强行绕过 completed 守卫。
- 重点检查 `resetedLessonId`、当前 `lessonId`、树刷新后的 `selectedLessonId` 三者的时序。若订阅回调触发时 `curr !== lessonId`，当前 hook 不会执行 `refreshData`；后续当 `lessonId` 切到被重置课节时，`resetedLessonId === lessonId` 又会让另一个 effect 直接 return。

## 建议排查顺序

1. 从目录按钮组件确认是否只做 `resetChapter`、`updateLessonId` 和 reset 事件派发。
2. 查看 store 中 `resetedLessonId` 的写入时机，以及聊天 hook 里基于它的订阅和 effect 条件。
3. 查看 `refreshData` 中调用 `runRef.current` 的守卫条件，尤其是 `isCompletedLesson`。
4. 对照树刷新逻辑，确认 `lessonStatus` 的新值何时传入 `useChatLogicHook`，避免旧状态先参与重置后的首轮判断；必要时在 reset 事件里先做本地状态矫正。

## 回归关注点

- 当前选中的课节点击重修后，是否稳定进入“思考中”。
- 非当前课节点击重修并切换过去后，是否会自动拉起 `/run`。
- 已完成课节和进行中课节两种状态下，重修后的行为是否一致。

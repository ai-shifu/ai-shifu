---
name: listen-element-finalization
description: 当排查学习页 run 接口、阅读模式或听课模式里的 element 流式收尾问题时使用本技能，重点检查 fallback element、BREAK/DONE 收尾与 SSE 最终态是否一致。
---

# 学习页 Element 收尾排查

## 核心规则

- `element.is_final` 表示当前 element 是否已经完成渲染，不能只依赖 `audio_segments[].is_final`。
- 只要最终态会写入 `LearnGeneratedElement`，对应的 live SSE 也必须发出同一条最终 element snapshot，避免“库里是 final，流里不是 final”。
- 优先检查 `GeneratedType.BREAK`、`GeneratedType.DONE`、fallback element 收尾和 audio patch 分支，确认最终 element 是否真正 `yield` 到流里。

## 工作流

1. 从 `src/api/flaskr/service/learn/listen_elements.py` 看 `CONTENT/AUDIO/BREAK/DONE` 事件如何进入 adapter。
2. 再查 `src/api/flaskr/service/learn/listen_element_run_stream.py`，确认 `_finalize_block`、`_finalize_stream_elements`、fallback 分支是否同时做了“持久化 + SSE 发出”。
3. 同步检查 `src/api/flaskr/service/learn/listen_element_run_persistence.py`，确认 `_element_message` 与 `_persist_element` 的职责没有被绕开。
4. 修改后补回归测试到 `src/api/tests/service/learn/`，至少覆盖一条 live stream 中能观察到 `content.is_final is True` 的用例。

## 回归清单

- 纯文本 fallback block 在 live SSE 中先收到 `is_final=false`，块结束后再收到同 `element_bid` 的 `is_final=true`。
- mdflow stream element 在 BREAK 后能收到最终 `is_final=true` 快照。
- audio patch 场景不会把 element 最终态只留在数据库里。

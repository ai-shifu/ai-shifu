# learn_generated_elements 设计文档（v1.2，2026-03-19）

## 1. 范围与目标（仅后端）

本版仅规划后端改造，不包含前端实现计划。

目标：

1. 统一 `run` 与 `records` 的 `elements` 协议。
2. 在 element 层补齐渲染/增量/导航标记/音频合成相关字段。
3. 将 `type` 产出逻辑收敛到状态机，不再散落在分支中硬编码。

---

## 2. 现状核对（As-Is）

基于当前代码（`src/api/flaskr/service/learn`）：

1. `element_type` 仅有 `interaction/sandbox/picture/video`。
2. `LearnGeneratedElement` 已有 `element_type/change_type/target_element_bid/is_navigable/is_final/content_text/payload`，但没有本次新增字段。
3. `run` 写链路中：
   - `audio_segment` 已并入当前 element patch，不再单独作为 SSE 事件输出；
   - `audio_complete` 仍作为非 element 事件落库；
   - 终态音频合并在 `payload.audio`；
   - 可选 `payload.diff_payload` 支持。
4. `records` 读链路默认返回 `elements`，`include_non_navigable=true` 时附带 `events`。

结论：当前实现已具备 element 化基础，但字段语义和枚举粒度与本次目标不一致。

---

## 3. 目标协议（To-Be）

## 3.1 element_type（冻结）

`element_type` 固定为：

- `html`
- `svg`
- `diff`
- `img`
- `interaction`
- `tables`
- `code`
- `latex`
- `md_img`
- `mermaid`
- `title`
- `text`

备注：

1. 旧 `sandbox/picture/video` 不再作为对外枚举值。
2. 当前 `video` 视觉边界在本版映射为 `html`（后端通过 `<video>` 片段归类）。
3. final 阶段不能把 narration 合并回视觉 element。`text` 必须作为独立 element 保留；视觉 element 仅承载视觉快照。

## 3.2 Element 数据结构（后端输出）

每个 `elements[]` 项是一个 element 对象，包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_type` | string | 固定 `element` |
| `element_bid` | string | 当前 element 唯一业务 ID |
| `generated_block_bid` | string | 来源 block |
| `role` | string | `teacher/student/ui` |
| `element_type` | string | 见 3.1 |
| `is_renderable` | bool | 是否参与前端渲染 |
| `is_new` | bool | 是否创建新 element；`false` 表示应用到已有 element |
| `target_element_bid` | string? | `is_new=false` 或 `element_type=diff` 时目标 element |
| `is_marker` | bool | 是否作为导航标记；`text=false`，其他 element 默认为 `true` |
| `sequence_number` | int | 当前 run 会话内 element 生成序号（严格递增） |
| `is_speakable` | bool | 是否需要语音合成 |
| `audio_url` | string | 完整音频地址（无则空字符串） |
| `audio_segments` | array | 音频流分段（见 3.3） |
| `content_text` | string | 文本快照 |
| `payload` | object? | 结构化内容（含 visuals、diff 等） |
| `is_final` | bool | 是否终态 |
| `run_session_bid` | string | run 会话 ID |
| `run_event_seq` | int | run 事件序号（保持现有链路） |

约束：

1. `is_new=false` 时必须提供 `target_element_bid`。
2. `is_marker` 由 `element_type` 推导：
   - `text=false`
   - 其他 `element_type=true`
3. `audio_url` 仅在音频完成后写入；未完成时可为空。
4. `sequence_number` 作用于 element 维度，和 `run_event_seq` 并存。

## 3.3 audio_segments 结构

`audio_segments` 每个节点建议结构：

```json
{
  "position": 0,
  "segment_index": 3,
  "duration_ms": 240,
  "is_final": false,
  "audio_data": "base64..."
}
```

字段来源与当前 `AudioSegmentDTO` 对齐，后端保存为 element 级别增量轨迹。

## 3.4 type 统一状态机判断

`RunElementSSEMessageDTO.type` 必须由状态机统一产出，不允许业务分支直接拼字符串。

状态定义：

- `IDLE`：当前无开放 element
- `BUILDING`：正在累积当前 element
- `PATCHING`：对既有 element 增量应用（`is_new=false`）
- `TERMINATED`：已结束（`done`/`error`）

触发与输出：

| 当前状态 | 输入事件 | 输出 `type` | 下一状态 |
|---|---|---|---|
| `IDLE` | 内容/视觉开始 | `element` | `BUILDING` |
| `BUILDING` | 增量更新且 `is_new=false` | `element` | `PATCHING` |
| `PATCHING` | 连续增量更新 | `element` | `PATCHING` |
| `BUILDING/PATCHING` | block break | `break` | `IDLE` |
| 任意非终态 | 音频分段 | `element` | 原状态保持 |
| 任意非终态 | 音频完成 | `audio_complete` | 原状态保持 |
| 任意非终态 | 正常结束 | `done` | `TERMINATED` |
| 任意非终态 | 异常结束 | `error` | `TERMINATED` |

`heartbeat` 为传输层事件，不参与 element 状态迁移。

---

## 4. 现状到目标的映射规则

## 4.1 视觉类型映射（后端归类）

| 当前来源 | 新 `element_type` |
|---|---|
| `svg` | `svg` |
| `iframe/sandbox` | `html` |
| `html_table/md_table` | `tables` |
| `fence` | `code` |
| `md_img` | `md_img` |
| `img` | `img` |
| `video` | `html` |
| `mermaid` 代码块 | `mermaid` |
| 公式片段 | `latex` |
| 标题行 | `title` |
| 普通叙述文本 | `text` |
| 交互块 | `interaction` |
| 对既有 element 的补丁 | `diff` |

## 4.2 新字段与现实现对应关系

| 新字段 | 现状 | 后端处理 |
|---|---|---|
| `is_renderable` | 无 | 新增列与 DTO 字段；按 element_type 决定默认值 |
| `is_new` | 无 | 新增列与 DTO 字段；写链路决定新建或补丁 |
| `is_marker` | 无 | 新增列与 DTO 字段；按 `element_type` 推导，`text=false`，其他为 `true` |
| `sequence_number` | 无 | 新增列与 DTO 字段；run 内 element 单独计数 |
| `is_speakable` | 无 | 新增列与 DTO 字段；由 AV 合约与 block 类型推导 |
| `audio_url` | 仅在 payload.audio | 顶层冗余字段，便于快速读取 |
| `audio_segments` | 仅作为独立事件 | 合并进 element，保留流式轨迹；live SSE 不再单独输出 `audio_segment` |

## 4.3 final 组装规则

1. 有 `visual_boundaries` 且有 `speakable_segments` 时，最终输出按时间顺序交错组装：
   - 先输出视觉 element
   - 再输出对应 narration 的 `text` element
2. 视觉 element 的 `content_text` 为空字符串，`payload.previous_visuals` 承载视觉内容。
3. narration 的 `text` element 独立承载：
   - `content_text`
   - `is_speakable=true`
   - 对应位置的 `audio_url/audio_segments/payload.audio`
4. 若 narration 出现在第一个视觉之前，则直接输出独立 `text` element。

---

## 5. 数据层改造（后端）

`learn_generated_elements` 需要新增字段：

1. `is_renderable`（bool，default true，index）
2. `is_new`（bool，default true，index）
3. `is_marker`（bool，default false，index）
4. `sequence_number`（int，default 0，index）
5. `is_speakable`（bool，default false，index）
6. `audio_url`（varchar，default ""）
7. `audio_segments`（text/json，default "[]")

同时更新：

1. `element_type` 字段注释与校验口径为 3.1 枚举。
2. `element_type_code` 的映射表与枚举同步（可保留 int code 以兼容排序/埋点）。

---

## 6. 写链路改造（后端）

## 6.1 writer 核心

1. 增加 `TypeStateMachine`（纯后端模块）统一产出 `type`。
2. element 组装时写入新增字段：
   - `is_renderable`
   - `is_new`
   - `is_marker`
   - `sequence_number`
   - `is_speakable`
   - `audio_url`
   - `audio_segments`
3. `audio_segment` 不再单独发 SSE，改为输出当前 element 的 patch，并同步更新 `audio_segments`；`audio_complete` 继续发事件，同时回填当前 element 的 `audio_url`。
4. `is_new=false` 必须命中 `target_element_bid`；命中失败写 `error` 事件并终止该分支。

## 6.2 序号策略

1. `run_event_seq`：保持现有 run 事件级递增。
2. `sequence_number`：仅在输出 `type=element` 时递增。
3. 两者均落库，便于回放与排障。

---

## 7. 读链路改造（后端）

1. `records` 默认返回最终 `elements` 快照。
2. `include_non_navigable=true` 时返回 `events`；其中 `audio_segment` 已折叠为 `element` patch，`audio_complete` 仍保留。
3. `elements` 默认按 `sequence_number` + `run_event_seq` 排序。
4. `is_new=false` 的数据在回放层按 `target_element_bid` 应用后再输出最终快照。

---

## 8. 回填与兼容策略（后端）

1. 历史 `sandbox/picture/video` 数据按 4.1 规则映射到新枚举。
2. 历史数据回填新增字段默认值：
   - `is_renderable=true`
   - `is_new=true`
   - `is_marker` 按 `element_type` 推导，`text=false`，其他为 `true`
   - `sequence_number` 按历史顺序重建
   - `is_speakable` 依据是否存在音频
   - `audio_url` 从终态音频提取
   - `audio_segments` 无法恢复时置空数组
3. 回填脚本支持 `dry_run/overwrite`，并输出统计。

---

## 9. 测试要求（后端）

1. DTO 序列化单测：新字段完整性与默认值。
2. 状态机单测：状态迁移与 `type` 输出正确性。
3. 写链路单测：`is_new=false` 应用到目标 element。
4. 音频链路单测：`audio_segments` 累积与 `audio_url` 终态回填。
5. records 单测：排序、快照合并、`include_non_navigable`。
6. 回填单测：旧枚举映射到新枚举，新增字段补值正确。

---

## 10. 非目标

1. 不在本版规划前端消费改造细节。
2. 不在本版规划 UI 展示策略与交互动画。

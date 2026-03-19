# learn_generated_elements 设计文档（v1.3，2026-03-19）

## 1. 范围与目标（仅后端）

本版仅规划后端改造，不包含前端实现计划。

目标：

1. 统一 `run` 与 `records` 的 `elements` 协议。
2. 在 element 层补齐渲染/增量/导航标记/音频合成相关字段。
3. 将 `type` 产出逻辑收敛到状态机，不再散落在分支中硬编码。
4. 让学习过程中的“追问（ask）”也成为独立、可持久化、可回放的 element。
5. 让追问入口与上下文装载从 `generated_block_bid` 迁移到 `element_bid`。

---

## 2. 现状核对（As-Is）

基于当前代码（`src/api/flaskr/service/learn`）：

1. `element_type` 仅有 `interaction/sandbox/picture/video`。
2. `LearnGeneratedElement` 已有 `element_type/change_type/target_element_bid/is_navigable/is_final/content_text/payload`，但 `ElementDTO` 对外协议中的文本字段统一为 `content`。
3. `run` 写链路中：
   - `audio_segment` 已并入当前 element patch，不再单独作为 SSE 事件输出；
   - `audio_complete` 仍作为非 element 事件落库；
   - 终态音频合并在 `payload.audio`；
   - 可选 `payload.diff_payload` 支持。
4. `records` 读链路默认返回 `elements`，`include_non_navigable=true` 时附带 `events`。
5. 追问（`mdask`）当前仅持久化在 `LearnGeneratedBlock`：
   - 用户追问会写入 `LearnGeneratedBlock.type=MDASK`
   - AI 回答会写入 `LearnGeneratedBlock.type=MDANSWER`
   - live `CONTENT` 流目前复用“追问块”的 `generated_block_bid` 承载老师回答
   - 因此追问本身不会稳定出现在 `LearnGeneratedElement` 中
6. 当前追问入口仍然依赖 block 身份：
   - 前端/接口侧挂载和刷新追问时使用 `generated_block_bid`
   - 追问上下文历史也是从 `LearnGeneratedBlock` 查询并组装
   - 这与 element 协议已经成为主展示协议的方向不一致

结论：当前实现已具备 element 化基础，但字段语义、ask/answer 分块方式与本次目标不一致。

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
| `is_renderable` | bool | 是否参与前端渲染；`text=false`，其他 element 默认为 `true` |
| `is_new` | bool | 是否创建新 element；`false` 表示应用到已有 element |
| `target_element_bid` | string? | `is_new=false` 或 `element_type=diff` 时目标 element |
| `is_marker` | bool | 是否作为导航标记；`text=false`，其他 element 默认为 `true` |
| `sequence_number` | int | 当前 run 会话内 element 生成序号（严格递增） |
| `is_speakable` | bool | 是否需要语音合成 |
| `audio_url` | string | 完整音频地址（无则空字符串） |
| `audio_segments` | array | 音频流分段（见 3.3） |
| `content` | string | 文本快照 |
| `payload` | object? | 结构化内容（含 visuals、diff 等） |
| `is_final` | bool | 是否终态 |
| `run_session_bid` | string | run 会话 ID |
| `run_event_seq` | int | run 事件序号（保持现有链路） |

约束：

1. `is_new=false` 时必须提供 `target_element_bid`。
2. `is_renderable` 由 `element_type` 推导：
   - `text=false`
   - 其他 `element_type=true`
3. `is_marker` 由 `element_type` 推导：
   - `text=false`
   - 其他 `element_type=true`
4. `audio_url` 仅在音频完成后写入；未完成时可为空。
5. `sequence_number` 作用于 element 维度，和 `run_event_seq` 并存。

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

## 3.5 追问（ask）element 化目标

追问在目标协议中必须满足：

1. 用户追问本身要作为一个独立 `text` element 出现在 live SSE 与 records 中。
2. 用户追问与老师回答必须分属两个不同的 `generated_block_bid`，不能共用同一个 block 标识。
3. 用户追问默认不参与前端直接渲染：
   - `role=student`
   - `element_type=text`
   - `is_renderable=false`
4. `text` element 默认需要语音能力：
   - `is_speakable=true`
   - `audio_url=""`
   - `audio_segments=[]`
5. 用户追问不是 `interaction`，也不是 `diff`，而是普通终态文本 element：
   - `is_new=true`
   - `is_marker=false`
   - `is_renderable=false`
   - `is_final=true`
6. 老师回答继续走现有内容 element 链路，可拆分为视觉 element 与 narration `text` element。
7. 追问的入口锚点必须改成 `element_bid`，不再暴露 `generated_block_bid` 给追问入口。
8. 追问上下文的首选来源必须是 `LearnGeneratedElement`，而不是 `LearnGeneratedBlock`。

建议的 ask element 最小结构：

```json
{
  "event_type": "element",
  "role": "student",
  "element_type": "text",
  "is_new": true,
  "is_marker": false,
  "is_renderable": false,
  "is_speakable": true,
  "audio_url": "",
  "audio_segments": [],
  "is_final": true,
  "content": "用户追问内容",
  "payload": {
    "audio": null,
    "previous_visuals": []
  }
}
```

---

## 3.6 ask/answer 分块规则（新增）

现有 ask 流程的问题不是“缺一个字段”，而是 block 归属错位：

1. 用户追问块（`mdask`）已经存在。
2. 老师回答块（`mdanswer`）目前是在回答完成后才写入。
3. 回答流式 `CONTENT` 在此之前复用了用户追问块的 `generated_block_bid`。

这会导致：

1. 用户追问 element 和老师回答 element 无法稳定区分。
2. `LearnGeneratedElement.generated_block_bid` 失去“一个 block 对应一组 element”的语义。
3. records 如果完全信任持久化 elements，就拿不到 ask 本身。

To-Be 规则：

1. 进入 ask 流程后，先创建并持久化 `mdask` block。
2. ask block 创建完成后，立即产出一个“仅供 element 链路消费”的 ask 事件。
3. 在任何老师侧文本输出前，先创建并持久化 `mdanswer` block。
4. 后续老师侧的 `content/audio_complete/break` 全部绑定到 answer block 的 `generated_block_bid`。
5. 用户 ask element 不需要 `break` 才能封口；它天然是单条终态 element。

这样分块后：

1. ask element 永远挂在 ask block 上。
2. teacher answer element 永远挂在 answer block 上。
3. backfill / records / live SSE 三条链路可以共享同一套 block 归属。

## 3.7 追问入口与上下文来源（新增）

### 3.7.1 追问入口标识

To-Be 约束：

1. 触发追问时，客户端传递的锚点从 `generated_block_bid` 改为 `element_bid`。
2. 该 `element_bid` 必须指向一个已存在、可追问的终态 element。
3. 服务端通过 `element_bid` 反查：
   - `generated_block_bid`
   - `progress_record_bid`
   - `outline_item_bid`
   - `run_session_bid`
4. `generated_block_bid` 仍保留在内部落库与回放中使用，但不再作为追问入口参数。

设计原因：

1. 前端主渲染协议已经是 element。
2. 一个 block 在未来可能对应多个 elements，追问入口需要锚定到用户实际点击/看到的那个 element。
3. 以 `element_bid` 作为入口，才能天然支持“追问内容挂在 elements 下面”的完整闭环。

### 3.7.2 上下文来源切换

To-Be 约束：

1. 追问历史上下文优先从 `LearnGeneratedElement` 读取。
2. 仅在目标 progress 尚未完成 element 化或没有足够 element 数据时，才回退到 `LearnGeneratedBlock`。
3. 上下文组装按 element 顺序进行，而不是 block 顺序：
   - `role=student` 的 `text` element -> user turn
   - `role=teacher` 的 `text` element -> assistant turn
   - 视觉型 element 默认不直接进问答上下文
4. 对同一 `target_element_bid` 的 patch，要先聚合成最终快照，再参与上下文装载。

上下文裁剪规则：

1. 历史窗口以 element 为单位裁剪，而不是以 block 为单位裁剪。
2. ask element 与 answer text element 都计入历史轮次。
3. interaction element 不直接作为用户发言文本进入 ask 历史，除非未来单独定义转换规则。

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
| `is_renderable` | 无 | 新增列与 DTO 字段；按 `element_type` 推导，`text=false`，其他为 `true` |
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
2. 视觉 element 的 `content` 为空字符串，`payload.previous_visuals` 承载视觉内容。
3. narration 的 `text` element 独立承载：
   - `content`
   - `is_speakable=true`
   - 对应位置的 `audio_url/audio_segments/payload.audio`
4. 若 narration 出现在第一个视觉之前，则直接输出独立 `text` element。

---

## 5. 数据层改造（后端）

`learn_generated_elements` 需要新增字段：

1. `is_renderable`（bool，default true，index；读取时对 `text` 归一化为 `false`）
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

## 6.3 ask 写链路改造（新增）

原则：尽量不改数据库表，仅调整运行事件与 block 写入时机。

### 6.3.1 事件层设计

新增一个内部事件类型：

- `GeneratedType.ASK`

约束：

1. `GeneratedType.ASK` 只用于 run -> element adapter 的内部桥接。
2. 非 listen/raw mdflow 消费链路不对外暴露 `ASK`。
3. `ASK` 事件只承载用户追问文本，不承载音频。

### 6.3.2 handle_input_ask 流程调整

新的 ask 流程建议为：

1. 创建 `mdask` 的 `LearnGeneratedBlock`，写入用户追问文本。
2. 立即产出一条 `GeneratedType.ASK`，`generated_block_bid` 指向 ask block。
3. 在任何老师侧输出前，创建 `mdanswer` 的 `LearnGeneratedBlock`。
4. 所有老师侧：
   - `GeneratedType.CONTENT`
   - `GeneratedType.AUDIO_COMPLETE`
   - `GeneratedType.BREAK`
   均改为使用 answer block 的 `generated_block_bid`。

### 6.3.3 ListenElementRunAdapter 行为

adapter 新增 `_handle_ask()`：

1. 直接输出一个终态 `text` element。
2. `role` 固定为 `student`。
3. 不进入当前 block 的增量拼装状态，不等待 `break`。
4. 不影响后续 answer block 的 state machine。

### 6.3.4 非 listen 兼容

为了不破坏现有 raw run 链路：

1. `run_script_inner()` 在 `element_adapter is None` 时忽略 `GeneratedType.ASK`。
2. 现有前端若仍使用传统 run 流，不会额外收到 ask 事件。
3. listen 模式下由 element adapter 消费 `ASK` 并产出 SSE `element`。

---

## 7. 读链路改造（后端）

1. `records` 默认返回最终 `elements` 快照。
2. `include_non_navigable=true` 时返回 `events`；其中 `audio_segment` 已折叠为 `element` patch，`audio_complete` 仍保留。
3. `elements` 默认按 `sequence_number` + `run_event_seq` 排序。
4. `is_new=false` 的数据在回放层按 `target_element_bid` 应用后再输出最终快照。
5. ask element 一旦已落库，records 优先直接返回持久化 student `text` element，不再依赖 legacy block fallback 才能看到追问。

---

## 8. 回填与兼容策略（后端）

1. 历史 `sandbox/picture/video` 数据按 4.1 规则映射到新枚举。
2. 历史数据回填新增字段默认值：
   - `is_renderable=false`
   - `is_new=true`
   - `is_marker` 按 `element_type` 推导，`text=false`，其他为 `true`
   - `sequence_number` 按历史顺序重建
   - `is_speakable` 依据是否存在音频
   - `audio_url` 从终态音频提取
   - `audio_segments` 无法恢复时置空数组
3. 回填脚本支持 `dry_run/overwrite`，并输出统计。
4. 对历史 `LearnGeneratedBlock.type=MDASK` 但尚未存在 ask element 的 progress：
   - 允许回填脚本直接合成 `role=student` 的 `text` element
   - `generated_block_bid` 复用原 ask block
   - 不新增任何表字段

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
3. 不在本版引入新的数据库表，也不优先新增 `LearnGeneratedElement` 字段。

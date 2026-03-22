# learn_generated_elements 设计文档（v1.4，2026-03-20）

## 1. 范围与目标（仅后端）

本版仅规划后端改造，不包含前端实现计划。

目标：

1. 统一 `run` 与 `records` 的 `elements` 协议。
2. 在 element 层补齐渲染/增量/导航标记/音频合成相关字段。
3. 将 `type` 产出逻辑收敛到状态机，不再散落在分支中硬编码。
4. 让学习过程中的”追问（ask）”内嵌在被追问的 anchor element 的 `payload.asks` 中，不产生独立 element 行。
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

## 3.5 追问（ask）内嵌 anchor element 模型

追问问答对不产生独立 `LearnGeneratedElement` 行，而是内嵌在被追问的 anchor element 的 `payload.asks` 数组中。

核心规则：

1. 追问问答对存储在 anchor element 的 `payload.asks` 数组中，按 role 交替排列。
2. 不产生独立 `LearnGeneratedElement` 行，不占用 `sequence_number`。
3. anchor element 本身的 `element_type`、`is_renderable`、`is_marker`、`sequence_number` 等字段不变。
4. 追问入口改为 `reload_element_bid`（指向 anchor element）。
5. 追问上下文从 anchor element 的 `payload.asks` 读取。
6. 被追问的锚点 element（无论 `text` 还是视觉 element）以聚合后的最终快照进入 ask 上下文。
7. 老师回答在 live SSE 阶段作为独立事件推送（`is_new=false` + `target_element_bid=anchor`），落库时合并到 `payload.asks`。

`payload.asks` 示意结构：

```json
"asks": [
  {"role": "student", "content": "用户追问"},
  {"role": "teacher", "content": "老师回答"},
  {"role": "student", "content": "第二次追问"},
  {"role": "teacher", "content": "第二次回答"}
]
```

asks 条目字段集（冻结）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `role` | string | 是 | `student` 或 `teacher` |
| `content` | string | 是 | 追问或回答文本 |
| `generated_block_bid` | string | 否 | 对应的 mdask/mdanswer block bid，用于溯源 |
| `timestamp` | string | 否 | ISO 8601 时间戳 |

asks 数组上限与 `ASK_MAX_HISTORY_LEN=10` 对齐，即最多 5 轮 Q&A，10 条条目。

---

## 3.6 ask/answer block 归属规则

现有 ask 流程的问题不是”缺一个字段”，而是 block 归属错位：

1. 用户追问块（`mdask`）已经存在。
2. 老师回答块（`mdanswer`）目前是在回答完成后才写入。
3. 回答流式 `CONTENT` 在此之前复用了用户追问块的 `generated_block_bid`。

To-Be 规则：

1. 进入 ask 流程后，先创建 `mdask` block。
2. **在任何老师侧输出前**（包括 guardrail 响应），创建 `mdanswer` block。
3. 所有老师侧 `CONTENT`/`AUDIO_COMPLETE`/`BREAK` 绑定 answer block 的 `generated_block_bid`。
4. guardrail 命中时也必须先创建 answer block（修复 `handle_input_ask.py:225-239` 早返回路径）。
5. guardrail 路径的 `INTERACTION` 事件（`handle_input_ask.py:232-237`）在 listen 模式下不再需要，非 listen 兼容期内保留。
6. 追问文本和回答文本最终写入 anchor element 的 `payload.asks`。

## 3.7 追问入口与上下文来源

### 3.7.1 追问入口标识

To-Be 约束：

1. 当 `input_type=ask` 时，客户端优先传递 `reload_element_bid`；普通 regenerate 继续使用现有 `reload_generated_block_bid`。
2. 兼容过渡期内，ask 请求若未传 `reload_element_bid`，服务端允许回退读取 `reload_generated_block_bid`，再解析到对应的 askable final element。
3. 该 `reload_element_bid` / 解析后的 `element_bid` 必须指向一个已存在、可追问的终态 element。
4. 服务端通过 `element_bid` 反查 anchor element，获取 `generated_block_bid`、`progress_record_bid`、`outline_item_bid`、`run_session_bid`。
5. 若目标 element 不存在、未终态或不允许追问，直接拒绝 ask，不回退到”最近一个 block”的模糊猜测。
6. `generated_block_bid` 仍保留在内部落库与回放中使用，但不再作为 ask 的长期入口参数。

参数传递链路：`routes.py` 新增 `reload_element_bid` 解析 → `run_script_inner`/`run_script` 签名新增参数 → `context_v2.reload()` 支持 element_bid 入口 → `handle_input_ask`。

设计原因：

1. 前端主渲染协议已经是 element。
2. 一个 block 在未来可能对应多个 elements，追问入口需要锚定到用户实际点击/看到的那个 element。
3. 以 `element_bid` 作为入口，才能天然支持”追问内容内嵌在 anchor element 的 payload.asks 中”的完整闭环。
4. 普通 regenerate 仍然是”回滚某个 block 之后重新生成”，不应和 ask 锚点迁移混为一谈。

### 3.7.2 上下文来源切换

To-Be 约束：

1. 追问上下文优先从 anchor element 的 `payload.asks` 读取。
2. 仅在 `payload.asks` 为空或不存在时回退到 `LearnGeneratedBlock`。
3. 直接将 `payload.asks` 条目按 role 映射为 LLM 消息（`student` → `user`，`teacher` → `assistant`）。
4. 锚点 element 本身的 content 作为首条 assistant context message。
5. 裁剪以 asks 条目为单位，与 `ASK_MAX_HISTORY_LEN` 对齐。
6. 不再需要 `sequence_number` 截断。
7. legacy fallback 条件（严格定义）：
   - anchor element 的 payload 中无 `asks` 字段 → fallback
   - `asks` 为空数组 `[]` → fallback（首次追问，无历史，两条路径结果一致）
   - `asks` 存在但不包含至少一对 student+teacher → fallback（数据不完整）
   - `asks` 存在且包含至少一对 student+teacher → 使用 `payload.asks`

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
| `is_speakable` | 无 | 新增列与 DTO 字段；由 AV 合约与 block 类型推导，teacher narration `text` 通常为 `true`，其余默认 `false` |
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

## 6.3 ask 写链路改造

原则：asks 内嵌在 anchor element 的 `payload.asks` 中，不产生独立 element 行，不新增数据库列。

### 6.3.1 事件层

保留 `GeneratedType.ASK`：用于 adapter 识别并触发 `payload.asks` 写入。

约束：

1. `GeneratedType.ASK` 只用于 run → element adapter 的内部桥接。
2. 非 listen/raw mdflow 消费链路不对外暴露 `ASK`。
3. `ASK` 事件承载：用户追问文本 + `anchor_element_bid`。

### 6.3.2 handle_input_ask 流程

重构策略：先 extract method 拆分为内部函数（纯重构不改行为），再修复 block 归属。

内部函数拆分：

```
handle_input_ask()
  ├── _create_ask_block()          # 创建 mdask block
  ├── _create_answer_block()       # 创建 mdanswer block（空占位）
  ├── _run_guardrail()             # 敏感词检测
  └── _run_answer_stream()         # provider routing + 流式输出
```

改造后调用流程：

1. 通过 `reload_element_bid` 定位 anchor element（兼容 `reload_generated_block_bid`）。
2. 创建 `mdask` block。
3. 创建 `mdanswer` block（content 为空占位，flush 获取 `generated_block_bid`）。
4. 产出 `GeneratedType.ASK`（含追问文本 + `anchor_element_bid`）。
5. 执行 guardrail 检测；命中时用 answer block 的 `generated_block_bid` 输出 CONTENT+BREAK 后结束。
6. 正常路径：所有老师侧 `CONTENT`/`BREAK` 使用 answer block 的 `generated_block_bid`。
7. 流式结束后 UPDATE 回填 answer block 的 `generated_content`。
8. guardrail 路径不再特殊早返回，统一走 answer block 归属。

### 6.3.3 ListenElementRunAdapter 行为

adapter 新增 `_handle_ask()`：

1. 追加 `{role: "student", content}` 到 anchor element 的 `payload.asks` 并 UPDATE，不产出独立 element，不占 `sequence_number`。
2. answer 流式阶段：独立 SSE 事件推送（`is_new=false`，`target_element_bid=anchor`），BREAK 时追加 `{role: "teacher", content}` 到 `payload.asks` 并 UPDATE。

### 6.3.4 非 listen 兼容

`element_adapter is None` 时忽略 `GeneratedType.ASK`。

### 6.3.5 并发安全

1. 前端禁止对同一 anchor 并发 ask。
2. 后端建议乐观锁或 last-write-wins。

---

## 7. 读链路改造（后端）

1. `records` 默认返回最终 `elements` 快照。
2. `include_non_navigable=true` 时返回 `events`；其中 `audio_segment` 已折叠为 `element` patch，`audio_complete` 仍保留。
3. `elements` 默认按 `sequence_number` + `run_event_seq` 排序。
4. `is_new=false` 的数据在回放层按 `target_element_bid` 应用后再输出最终快照。
5. `payload.asks` 随 element 在 records 中直接返回，前端可从 anchor element 的 payload 获取追问历史。
6. ask 上下文从 `payload.asks` 读取；无 `asks` 字段时回退 legacy block。

---

## 8. 回填与兼容策略（后端）

1. 历史 `sandbox/picture/video` 数据按 4.1 规则映射到新枚举。
2. 历史数据回填新增字段默认值：
   - `is_renderable` 按 `element_type` 推导，`text=false`，其他为 `true`
   - `is_new=true`
   - `is_marker` 按 `element_type` 推导，`text=false`，其他为 `true`
   - `sequence_number` 按历史顺序重建
   - `is_speakable` 按 element 语义恢复：teacher narration `text` 或已有音频的 element 为 `true`，其余无法确认时保守置 `false`
   - `audio_url` 从终态音频提取
   - `audio_segments` 无法恢复时置空数组
3. 回填脚本支持 `dry_run/overwrite`，并输出统计。
4. 历史 MDASK/MDANSWER blocks → 匹配 anchor element → 回填到 `payload.asks`：
   - 匹配优先级：
     1. `generated_block_bid` 直接匹配（同一个 block 产生的 element）
     2. `position` 就近匹配（`sequence_number <= ask_block.position` 的最后一个 askable final element）
     3. fallback：同 progress 下最后一个 final element
     4. 全部失败：跳过该 ask block，计入 `skipped` 统计
   - 将 ask block content 作为 `{role: "student", content}` 条目
   - 将 answer block content 作为 `{role: "teacher", content}` 条目（answer block 缺失时只写 student 条目）
   - 追加到匹配到的 anchor element 的 `payload.asks` 数组
   - 不新增 element 行或表字段
   - 回填脚本输出统计：`total_asks/matched/skipped` 及 skipped 详情

---

## 9. 测试要求（后端）

1. DTO 序列化单测：新字段完整性与默认值。
2. 状态机单测：状态迁移与 `type` 输出正确性。
3. ask 写链路单测：`payload.asks` 结构正确性 + MDASK/MDANSWER block 创建。
4. 写链路单测：`is_new=false` 应用到目标 element。
5. 音频链路单测：`audio_segments` 累积与 `audio_url` 终态回填。
6. ask 上下文单测：从 `payload.asks` 组装 LLM 消息，role 映射正确（student→user，teacher→assistant）。
7. ask 上下文单测：视觉锚点聚合快照作为首条 context message。
8. records 单测：排序、快照合并、`include_non_navigable`。
9. 兼容单测：ask 请求双读 `reload_element_bid` / `reload_generated_block_bid`，普通 regenerate 仍沿用 block 入口。
10. 回填单测：旧枚举映射到新枚举，新增字段补值正确，历史 mdask/mdanswer 正确回填到 `payload.asks`。
11. 并发 ask 单测：并发 ask 不丢失 `payload.asks` 条目。
12. guardrail 单测：guardrail 命中时 answer block 创建且 `payload.asks` 包含 student+teacher 条目。
13. answer SSE 单测：answer SSE 事件携带 `target_element_bid=anchor`。

---

## 10. 非目标

1. 不在本版规划前端消费改造细节。
2. 不在本版规划 UI 展示策略与交互动画。
3. 不在本版引入新的数据库表或 ask 专用持久化表。

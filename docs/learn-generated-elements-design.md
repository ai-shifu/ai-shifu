# learn_generated_elements 设计文档（v1.0，2026-03-06）

## 1. 目标与范围

本版目标：把 `run/records` 从旧 `new_slide + slides` 协议，切换到统一的 `element` 协议，并给出三套可评审方案。

- 范围：`src/api/flaskr/service/learn` 与 `src/cook-web` 听课模式
- 发布策略：不做兼容，不保留旧协议
- 评审输出：在 `A-Flat / A-Tree / B` 三选一

---

## 2. 当前代码现状（As-Is）

### 2.1 run SSE

接口：`PUT /api/learn/shifu/{shifu_bid}/run/{outline_bid}`

当前仍输出旧事件模型（含 `new_slide`），并保留传输层 `heartbeat`。

### 2.2 records

接口：`GET /api/learn/shifu/{shifu_bid}/records/{outline_bid}`

当前返回 `records + interaction + slides`，`slides` 为读时组装。

### 2.3 数据层

已存在：
- `learn_generated_blocks`
- `learn_generated_audios`

未落地：
- `learn_generated_elements`
- `run_session_bid / run_event_seq / element_index` 的统一持久化链路

### 2.4 前端现状（对照代码）

当前前端主要依赖：
- `new_slide`
- `slides`
- `markdown/sandbox` 主路径

结论：如果后端直接切协议，前端必须同版本同步改造。

---

## 3. 三方案共用协议（固定不变）

以下内容在三套方案里都一致。

### 3.1 run SSE 事件包

统一事件包：`RunElementSSEMessageDTO`

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `element/audio_segment/audio_complete/variable_update/outline_item_update/break/done/error/heartbeat` |
| `event_type` | string | 与 `type` 对齐 |
| `run_session_bid` | string | run 会话 ID（`heartbeat` 可空） |
| `run_event_seq` | int | run 内递增序号（`heartbeat` 可空） |
| `content` | object/string | 按 `type` 决定结构 |

规则：
1. `run_event_seq` 对业务事件严格递增。
2. `heartbeat` 仅传输保活，不落 element。
3. 保留 `audio_segment/audio_complete`，但不单独生成 element。
4. 异常时先 `error` 后 `done`，正常结束最后一条是 `done`。

### 3.2 Element 共用字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `element_bid` | string | element 业务 ID |
| `generated_block_bid` | string? | 旧 block 关联 |
| `element_index` | int | 导航顺序号 |
| `role` | string | `teacher/student/ui` |
| `element_type` | string | 方案相关 |
| `element_type_code` | int | 方案相关 |
| `change_type` | string? | 仅方案 B 使用：`render/diff` |
| `target_element_bid` | string? | diff 目标锚点（A: `element_type=diff`；B: `change_type=diff`） |
| `is_navigable` | int | `0/1` |
| `is_final` | int | `0/1` |
| `content_text` | string? | 文本内容 |
| `payload` | object? | 结构化内容 |

### 3.3 SSE 部分态语义（关键）

`run` 阶段默认是部分内容：

1. `is_final=0`：部分态，可持续更新。
2. `is_final=1`：终态，后续不允许再改该稳定锚点。
3. 前端 run 态必须做 upsert，不得每条都 append。

### 3.4 DIFF 通用定义（三方案共用能力）

DIFF 在三方案里都支持，但表达方式不同：

1. 方案 A-Flat / A-Tree：`element_type=diff`
2. 方案 B：`change_type=diff`（`element_type` 仍是渲染器类型）

统一约束：
1. 补丁载荷放在 `payload.diff_payload`（建议 JSON Patch）。
2. `target_element_bid` 必须可解析到当前稳定锚点。
3. 前端应用 `diff` 失败时，必须回退到等待下一条全量快照（`render` 或非 diff 全量 event）。
4. 终态（`is_final=1`）建议带完整可回放快照。

### 3.5 语音与图像合并语义

内容 element 的 `payload` 统一约定：
- `payload.audio`：`is_final=0` 可为 `null`；终态需完整（若本单元有语音）
- `payload.previous_visuals`：语音对应的上一组视觉（可空数组）

`audio_segment/audio_complete` 用于流式传输，最终音频信息并入 `payload.audio`。

### 3.6 records 共用外层结构

接口：`GET /api/learn/shifu/{shifu_bid}/records/{outline_bid}`

`data` 统一：
- `elements`: 默认返回导航 element 终态快照
- `events`: 仅 `include_non_navigable=true` 返回（含非导航事件与中间态）

### 3.7 接口返回示例（共用）

说明：示例中的 `element_type_code` 仅示意，最终以评审冻结枚举为准。

run SSE（`type=element`）示例：

```json
{
  "type": "element",
  "event_type": "element",
  "run_session_bid": "run_abc123",
  "run_event_seq": 12,
  "content": {
    "element_bid": "el_001",
    "element_index": 35,
    "role": "teacher",
    "element_type": "picture",
    "element_type_code": 105,
    "is_navigable": 1,
    "is_final": 0,
    "content_text": "",
    "payload": {
      "audio": null,
      "previous_visuals": [
        {
          "visual_type": "img",
          "content": "https://cdn.example.com/pic-01.png"
        }
      ]
    }
  }
}
```

records 示例（默认 `include_non_navigable=false`）：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "elements": [
      {
        "element_bid": "el_001",
        "element_index": 35,
        "role": "teacher",
        "element_type": "picture",
        "element_type_code": 105,
        "is_navigable": 1,
        "is_final": 1,
        "content_text": "讲解完成",
        "payload": {
          "audio": {
            "audio_bid": "au_001",
            "audio_url": "https://...",
            "duration_ms": 980,
            "position": 5
          },
          "previous_visuals": [
            {
              "visual_type": "img",
              "content": "https://cdn.example.com/pic-01.png"
            }
          ]
        }
      }
    ]
  }
}
```

---

## 4. 方案 A-Flat（细分视觉类型 + 平铺时间线）

### 4.1 方案定义

`element_type`：
- `interaction`
- `svg`
- `html`
- `video`
- `picture`
- `mixed`
- `diff`

不使用父子结构，`parent_element_bid` 不出现。

### 4.2 与现有 visual_kind 映射

- `svg` -> `svg`
- `video` -> `video`
- `img/md_img` -> `picture`
- `iframe/sandbox/html_table/md_table` -> `html`
- 多类型混合或无法单类归类 -> `mixed`
- `diff` 不来自 `visual_kind`，仅表示“对既有 element 的增量变更”。

### 4.3 SSE 组装规则

稳定锚点：同一叙述单元复用同一 `element_bid + element_index`。

A-Flat 的 DIFF 定义：
- 使用 `element_type=diff` 对同一 `element_bid` 做增量更新。
- `target_element_bid` 默认等于当前 `element_bid`。
- `diff` 既可用于文本补充，也可用于 `payload.previous_visuals` 增量追加。
- 当出现类型提升（例如 `svg -> mixed`）时，可先发一次全量快照，再继续 `element_type=diff`。

`SVG -> MD_img` 场景：
1. 首次 `svg` 到达：`element_type=svg`, `is_final=0`
2. 后续 `md_img` 到达：同 `element_bid` 发送 `element_type=diff`, `is_final=0`
3. 单元结束：同 `element_bid` 终态快照 `is_final=1`（含完整 `audio + previous_visuals`）

### 4.4 records 规则

- 默认 `elements`：每个 `element_bid` 仅保留终态（`is_final=1` 优先）
- `events`：可选返回中间态（`is_final=0`）

### 4.5 前端改造影响

- 按 `element_type` 分发：`svg/html/video/picture/mixed/interaction` 走渲染器，`diff` 走补丁处理器
- 需支持 run 中类型提升（如 `svg -> mixed`）

### 4.6 回填口径

- 每个叙述单元回填为一条终态 element
- 混合视觉直接回填为 `mixed`

### 4.7 优缺点

优点：
- 类型语义直观，前端按类型选渲染器最直接
- 埋点统计按视觉类型更清晰

缺点：
- 与现有前端 `sandbox` 主路径差距较大
- run 过程中类型会后验变化，前端要处理类型提升

### 4.8 A-Flat 接口示例（`SVG -> MD_img`）

第一条（先到 `svg`）：

```json
{
  "type": "element",
  "event_type": "element",
  "run_session_bid": "run_a_flat_1",
  "run_event_seq": 20,
  "content": {
    "element_bid": "el_100",
    "element_index": 40,
    "role": "teacher",
    "element_type": "svg",
    "element_type_code": 102,
    "is_navigable": 1,
    "is_final": 0,
    "payload": {
      "audio": null,
      "previous_visuals": [
        {
          "visual_type": "svg",
          "content": "<svg>...</svg>"
        }
      ]
    }
  }
}
```

第二条（增量，`element_type=diff`）：

```json
{
  "type": "element",
  "event_type": "element",
  "run_session_bid": "run_a_flat_1",
  "run_event_seq": 21,
  "content": {
    "element_bid": "el_100",
    "element_index": 40,
    "role": "teacher",
    "element_type": "diff",
    "element_type_code": 199,
    "target_element_bid": "el_100",
    "is_navigable": 1,
    "is_final": 0,
    "payload": {
      "diff_payload": [
        {
          "op": "add",
          "path": "/previous_visuals/-",
          "value": {
            "visual_type": "md_img",
            "content": "https://cdn.example.com/pic-02.png"
          }
        }
      ]
    }
  }
}
```

---

## 5. 方案 A-Tree（细分视觉类型 + 父子结构）

### 5.1 方案定义

`element_type` 同 A-Flat（含 `diff`），并引入父子关系。

新增字段：
- `parent_element_bid`（仅本方案）

约束：
- 父 element：导航节点（`is_navigable=1`）
- 子 element：视觉片段（`is_navigable=0`，必须带 `parent_element_bid`）

### 5.2 SSE 组装规则

稳定锚点：同一叙述单元复用同一父 `element_bid + element_index`。

A-Tree 的 DIFF 定义：
- 父节点可用 `element_type=diff` 增量维护聚合快照（`payload.previous_visuals/audio/content_text`）。
- 子节点可用 `element_type=diff` 更新同一子 `element_bid`，也可直接新建子节点。
- 父节点的 `target_element_bid` 默认指向父 `element_bid`；子节点同理。

`SVG -> MD_img` 场景：
1. 先发父 element（部分态，`is_final=0`）
2. 发 `svg` 子 element（终态子片段）
3. 发 `md_img` 子 element（终态子片段）
4. 回写父 element 终态（`is_final=1`，聚合 `previous_visuals + audio`）

### 5.3 records 规则

- 默认 `elements`：只返回父节点终态（导航稳定）
- `events` 或扩展模式：返回子节点与中间态

### 5.4 前端改造影响

- 除类型渲染外，还要做父子装配（按 `parent_element_bid` 聚合）
- 需支持 `element_type=diff` 对父或子节点的增量应用
- 回放与导航逻辑更复杂，但可细粒度控制子片段

### 5.5 回填口径

- 每个叙述单元至少 1 条父 element
- 视觉片段拆分为多条子 element
- 父节点保留聚合快照，保证默认 records 可直接回放

### 5.6 优缺点

优点：
- 对复杂混合视觉表达能力最强
- 子片段可独立管理，结构清晰

缺点：
- 前后端复杂度最高
- 默认查询与回放逻辑需要额外父子装配

### 5.7 A-Tree 接口示例（`SVG -> MD_img`）

父节点（部分态）：

```json
{
  "type": "element",
  "event_type": "element",
  "run_session_bid": "run_a_tree_1",
  "run_event_seq": 30,
  "content": {
    "element_bid": "el_parent_300",
    "element_index": 42,
    "role": "teacher",
    "element_type": "mixed",
    "element_type_code": 106,
    "is_navigable": 1,
    "is_final": 0,
    "payload": {
      "audio": null,
      "previous_visuals": []
    }
  }
}
```

子节点 diff（挂父）：

```json
{
  "type": "element",
  "event_type": "element",
  "run_session_bid": "run_a_tree_1",
  "run_event_seq": 31,
  "content": {
    "element_bid": "el_child_301",
    "parent_element_bid": "el_parent_300",
    "element_index": 42,
    "role": "teacher",
    "element_type": "diff",
    "element_type_code": 199,
    "target_element_bid": "el_child_301",
    "is_navigable": 0,
    "is_final": 0,
    "payload": {
      "diff_payload": [
        {
          "op": "replace",
          "path": "/content",
          "value": "https://cdn.example.com/pic-03.png"
        }
      ]
    }
  }
}
```

---

## 6. 方案 B（渲染器类型 + diff）

### 6.1 方案定义

`element_type`：
- `interaction`
- `sandbox`
- `picture`
- `video`

B 中的 DIFF 使用是主路径：
- `change_type`: `render/diff`
- `target_element_bid`（`diff` 时必填）
- `payload.diff_payload`（建议 JSON Patch）

说明：`sandbox` 统一承载 `svg/html/div/table/iframe`。

### 6.2 SSE 组装规则

稳定锚点：同一叙述单元复用同一 `element_bid + element_index`。

推荐模式：
1. 初次输出 `change_type=render`, `is_final=0`
2. 增量变化输出 `change_type=diff`, `target_element_bid=element_bid`
3. 终态输出 `is_final=1`，含完整快照（可保留 diff 审计）

`SVG -> MD_img` 场景：
- 先 `sandbox/render` 带 svg
- 后 `sandbox/diff` 追加 md_img
- 终态同一 element 定型

### 6.3 records 规则

- 与 A-Flat 一致：默认终态快照，扩展返回中间态
- `diff_payload` 作为可选审计信息，不影响默认回放

### 6.4 前端改造影响

- 渲染器分发更简单（4 类）
- 需要补丁应用与容错（`diff` 失败回退全量）

### 6.5 回填口径

- 按渲染器归并为 `sandbox/picture/video/interaction`
- 回填终态快照；是否保留 `diff_payload` 由实现成本决定

### 6.6 优缺点

优点：
- 与当前前端 `sandbox` 路径最接近
- 流式后验更新自然（同 bid + diff）

缺点：
- 类型语义粒度更粗，统计需看 `previous_visuals[].visual_type`
- 需要稳定的 diff 合并机制

### 6.7 B 接口示例（`SVG -> MD_img`）

首包（`render`）：

```json
{
  "type": "element",
  "event_type": "element",
  "run_session_bid": "run_b_1",
  "run_event_seq": 40,
  "content": {
    "element_bid": "el_200",
    "element_index": 41,
    "role": "teacher",
    "element_type": "sandbox",
    "element_type_code": 102,
    "change_type": "render",
    "is_navigable": 1,
    "is_final": 0,
    "payload": {
      "audio": null,
      "previous_visuals": [
        {
          "visual_type": "svg",
          "content": "<svg>...</svg>"
        }
      ]
    }
  }
}
```

增量（`change_type=diff`）：

```json
{
  "type": "element",
  "event_type": "element",
  "run_session_bid": "run_b_1",
  "run_event_seq": 41,
  "content": {
    "element_bid": "el_200",
    "element_index": 41,
    "role": "teacher",
    "element_type": "sandbox",
    "element_type_code": 102,
    "change_type": "diff",
    "target_element_bid": "el_200",
    "is_navigable": 1,
    "is_final": 0,
    "payload": {
      "diff_payload": [
        {
          "op": "add",
          "path": "/previous_visuals/-",
          "value": {
            "visual_type": "md_img",
            "content": "https://cdn.example.com/pic-04.png"
          }
        }
      ]
    }
  }
}
```

---

## 7. 三方案集中对比（评审主表）

| 维度 | A-Flat | A-Tree | B |
|---|---|---|---|
| 类型体系 | 细分视觉类型 | 细分视觉类型 | 渲染器类型 |
| `parent_element_bid` | 否 | 是 | 否 |
| 稳定锚点 | 同 `element_bid` | 同父 `element_bid` | 同 `element_bid` |
| DIFF 表达 | `element_type=diff`（可选） | `element_type=diff`（可选） | `change_type=diff`（主路径） |
| `SVG -> MD_img` | 类型提升到 `mixed` | 子节点追加 | `sandbox + diff` |
| 前端渲染分发 | 中等复杂 | 高复杂 | 低复杂 |
| 前端状态管理 | 中等（upsert + 类型提升） | 高（父子装配） | 中高（diff 管理） |
| 与现有代码贴合度 | 中 | 低 | 高 |
| 回填复杂度 | 低 | 高 | 中 |
| 可观测性（按类型） | 高 | 高 | 中 |
| 扩展复杂视觉 | 中 | 高 | 中 |

---

## 8. 评审结论模板（直接填写）

- 最终方案：`A-Flat / A-Tree / B`
- 结论日期：`YYYY-MM-DD`
- 决策人：`xxx`
- 关键理由：
  1. ...
  2. ...
- 放弃方案及原因：
  1. ...
  2. ...

---

## 9. 实施与切换（不兼容）

### Phase 0：冻结

- 冻结最终方案与枚举值
- 冻结 run/records DTO
- 冻结 SSE 部分态与终态语义

### Phase 1：落表与写链路

- 建 `learn_generated_elements`
- 落 `run_session_bid + run_event_seq`
- 接入 element writer

### Phase 2：切接口

- run 只输出新事件包
- records 只返回 `elements/events`
- 删除 `new_slide/slides` 读写路径

### Phase 3：回填与收口

- 历史回填（按选定方案）
- 删除旧 DTO/旧监控/旧处理分支

---

## 10. 非兼容变更清单（上线前核对）

后端：
- 移除 run `new_slide`
- 移除 records 旧字段 `records/slides/interaction`

前端：
- 删除 `new_slide/slides` 处理逻辑
- run 态改为按稳定锚点 upsert
- 仅 `is_final=1` 固化导航节点

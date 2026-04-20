# Tasks (updated 2026-03-23)

Design reference: `docs/learn-generated-elements-design.md`

Superseded note: 2026-03-23 起，旧的“ask 内嵌 anchor payload.asks、不产生独立 element”方案被废弃，改为独立 `ask` element。K/L 中与旧 ask 设计相关的已完成项仅保留历史记录，不代表当前终态。

## 0. 现状核对（已完成）

- [x] 确认当前 `element_type` 仅为 `interaction/sandbox/picture/video`
- [x] 确认 `LearnGeneratedElement` 尚无 `is_renderable/is_new/is_marker/sequence_number/is_speakable/audio_url/audio_segments`
- [x] 确认 `audio_segment/audio_complete` 当前作为非 element 事件落库
- [x] 确认 `records` 已支持 `include_non_navigable`，默认返回 `elements`

## A. 协议冻结（P0）

- [x] 冻结 `element_type`：`html|svg|diff|img|interaction|tables|code|latex|md_img|mermaid|title|text`
- [x] 冻结 element 新字段语义：`is_renderable/is_new/is_marker/sequence_number/is_speakable/audio_url/audio_segments`
- [x] 冻结 `is_new=false` 约束：必须携带 `target_element_bid`
- [x] 冻结 `is_marker` 规则：`text=false`，其他 `element_type=true`
- [x] 冻结 `audio_segments` 节点结构（最小字段集与存储上限）
- [x] 冻结 `type` 状态机输入/状态/输出集合（禁止业务分支硬编码）
- [x] 冻结旧类型映射规则（`sandbox/picture/video` -> 新枚举）

## B. 数据库与模型（P1）

- [x] 更新 `ElementType` 枚举定义与 `element_type_code` 映射
- [x] 更新 `LearnGeneratedElement` 模型注释与校验口径
- [x] 新增列：`is_renderable`（bool）
- [x] 新增列：`is_new`（bool）
- [x] 新增列：`is_marker`（bool）
- [x] 新增列：`sequence_number`（int）
- [x] 新增列：`is_speakable`（bool）
- [x] 新增列：`audio_url`（string）
- [x] 新增列：`audio_segments`（text/json）
- [x] 为高频检索字段补索引（`sequence_number/is_marker/is_new/is_renderable/is_speakable`）
- [x] 生成 Alembic migration 并完成 upgrade/downgrade smoke test

## C. DTO 与序列化（P1）

- [x] 扩展 `ElementDTO` 字段与 `__json__` 输出
- [x] 扩展 payload 结构，保证 `audio_segments` 与 `audio_url` 顶层可直接读取
- [x] 统一 `records` 输出结构中 element 字段顺序与默认值
- [x] 更新 swagger schema 注释，确保新字段对齐

## D. run 写链路（P1）

- [x] 新增 `TypeStateMachine`，统一生成 `RunElementSSEMessageDTO.type`
- [x] 在 writer 中维护 `sequence_number`（仅 element 事件递增）
- [x] 在 writer 中处理 `is_new` 与 `target_element_bid` 绑定逻辑
- [x] 在 writer 中处理 `is_marker` 节点（前进/后退锚点）
- [x] 在 writer 中补齐 `is_renderable/is_speakable` 推导规则
- [x] `audio_segment` 到达时追加 `audio_segments`
- [x] `audio_complete` 到达时回填 `audio_url` 并封口对应 segment
- [x] `done/error` 时写终态并保证状态机进入终止态

## E. records 读链路（P2）

- [x] 默认按 `sequence_number, run_event_seq, id` 返回稳定顺序
- [x] `is_new=false` 的事件在聚合层应用到目标 element 后输出快照
- [x] `include_non_navigable=true` 时返回完整 events 回放序列
- [x] 增加 `is_marker` 过滤/保留策略（默认保留）
- [x] 确认无 `target_element_bid` 命中的异常数据处理策略

## F. 回填与数据修复（P2）

- [x] 回填脚本增加旧 `element_type` 到新枚举映射
- [x] 回填脚本补齐新增字段默认值
- [x] 回填脚本生成 `sequence_number`
- [x] 回填脚本从历史音频恢复 `audio_url`，无法恢复时保留空值
- [x] 回填脚本对 `audio_segments` 采用可恢复即恢复、否则空数组策略
- [x] 输出回填统计：总量、映射结果、异常行、跳过行

## G. 测试与验收（P2）

- [x] 单测：`ElementDTO` 新字段序列化/反序列化
- [x] 单测：`element_type` 新枚举合法性与非法值兜底
- [x] 单测：状态机迁移与 `type` 输出
- [x] 单测：`is_new=false` 应用到历史 element 的正确性
- [x] 单测：`is_marker` 节点规则
- [x] 单测：`audio_segments` 累积和 `audio_url` 回填
- [x] 单测：records 聚合顺序与 include_non_navigable
- [x] 集成测试：run -> records 全链路一致性

## H. 发布门禁（P3）

- [x] pre-commit 通过
- [x] 后端相关 pytest 用例通过（93 passed, 0 failed）
- [ ] migration 在本地与测试库双环境验证通过
- [ ] 回填 dry-run 报告通过评审
- [ ] 线上灰度观测项就绪：写入成功率、回放一致性、异常 target 命中率

## I. final text 保留（P1）

- [x] 更新设计：final 阶段 narration 必须保留为独立 `text` element
- [x] live SSE finalize 改为输出独立 `text` element，而不是把 narration 合并到视觉 element
- [x] legacy records builder 改为与 live SSE 一致的 final element 组装策略
- [x] final `text` element 补齐顶层 `audio_url/audio_segments` 与 `payload.audio`
- [x] 新增回归测试：`svg + text + html + text` final 顺序
- [x] 更新回归测试：视觉前后 narration 在 records 中保持独立 `text`

## J. live audio_segment 合并到 element（P1）

- [x] live SSE 不再单独输出 `audio_segment`
- [x] `audio_segment` 到达时改为输出当前 element 的 patch
- [x] records 聚合在 patch 合并时同步覆盖 `audio_segments/is_speakable/audio_url`
- [x] 更新回归测试：stream events 中 `audio_segment` 被 `element` patch 替代

## K. 追问挂到 element（P1）

- [x] 更新设计文档，冻结 ask element 的协议语义与 block 归属规则
- [x] 更新 `tasks.md`，拆分 ask element 化的实现任务
- [x] 冻结 asks 条目字段集：`role` + `content`（必填），`generated_block_bid` + `timestamp`（可选）
- [x] 冻结 legacy fallback 条件：无 `asks` 字段 / 空数组 / 不含至少一对 student+teacher → fallback
- [x] 冻结回填匹配优先级：block_bid 直接匹配 → position 就近匹配 → 同 progress 最后 final element → 跳过

### K-Phase 1: 基础设施（可并行）

- [x] 扩展 `ElementPayloadDTO` 加入 `asks: List[Dict]` 字段及 `__json__` 序列化
- [x] 扩展 `GeneratedType` 枚举加入 `ASK = "ask"`
- [x] 扩展 `RunMarkdownFlowDTO` 加入 `anchor_element_bid` 可选字段
- [x] `routes.py` 新增 `reload_element_bid` 参数解析，传递到 `run_script`/`run_script_inner`
- [x] `run_script_inner` 和 `context_v2.reload()` 签名新增 `reload_element_bid` 参数，ask 场景支持 element_bid 入口
- [x] 增加服务端反查逻辑：通过 `element_bid` 定位所属 `generated_block_bid/progress_record_bid/outline_item_bid/run_session_bid`
- [x] 冻结兼容策略：`GeneratedType.ASK` 仅作为 listen 内部事件，非 listen 原始 run 流默认忽略（`element_adapter is None` 时跳过）

### K-Phase 2: 写链路核心（串行）

- [x] 重构 `handle_input_ask`（纯 extract method，不改行为）：拆为 `_create_ask_block`/`_create_answer_block`/`_run_guardrail`/`_run_answer_stream`
- [x] 修复 block 归属：answer block 提前创建（空占位 + flush），所有老师侧 CONTENT/BREAK 绑定 answer block 的 `generated_block_bid`
- [x] 修复 guardrail 路径：命中时也先创建 answer block，用 answer block bid 输出 CONTENT+BREAK，不再特殊早返回
- [x] 在 ask 流程中产出 `GeneratedType.ASK` 内部事件（承载追问文本 + `anchor_element_bid`），guardrail/正常路径都产出
- [x] 扩展 `ListenElementRunAdapter.process()`：路由 `GeneratedType.ASK` 到新方法 `_handle_ask()`
- [x] 实现 `_handle_ask()`：追加 `{role: "student", content}` 到 anchor element 的 `payload.asks` 并 UPDATE，不产出独立 element，不占 `sequence_number`
- [x] answer 流式阶段：BREAK 时追加 `{role: "teacher", content}` 到 `payload.asks` 并 UPDATE（`_append_teacher_answer_to_asks`）
- [x] answer 侧流式 `CONTENT/AUDIO_COMPLETE/BREAK` 以及 guardrail/provider fallback 文本统一挂到 answer block

### K-Phase 3: 读链路与上下文（依赖 Phase 2）

- [x] 新增 `_load_ask_context()` 函数：优先从 anchor element 的 `payload.asks` 读取上下文
- [x] 实现 `_is_valid_asks()` 校验：至少一对 student+teacher 才算有效
- [x] 定义 element 到 ask 历史消息的映射规则：`student → user`，`teacher → assistant`
- [x] 锚点 element 本身的 content 作为首条 assistant context message
- [ ] 定义视觉锚点进入 ask 上下文的归一化规则：聚合后的 `content + previous_visuals` 摘要映射为 assistant anchor message
- [x] 裁剪以 asks 条目为单位，与 `ASK_MAX_HISTORY_LEN` 对齐
- [x] 仅在 `_is_valid_asks()` 返回 false 时回退到 legacy block 上下文
- [x] 更新 records 聚合逻辑：`payload.asks` 随 element 在 records 中直接返回，不需要额外聚合

### K-Phase 4: 回填与测试（依赖 Phase 2-3）

- [ ] 实现 `_backfill_asks_to_anchor_elements()`：按匹配优先级回填历史 mdask/mdanswer 到 `payload.asks`
- [ ] 回填容错：匹配失败跳过（不报错），answer block 缺失只写 student 条目，payload 解析失败跳过记录 error
- [ ] 回填统计输出：`total_asks/matched/skipped` 及 skipped 详情
- [ ] 增加回归测试：ask/answer 使用不同 `generated_block_bid`
- [ ] 增加回归测试：ask 请求使用 `reload_element_bid` 仍能正确命中原锚点；legacy `reload_generated_block_bid` 在过渡期仍可用
- [ ] 增加回归测试：ask 上下文来自 `payload.asks` 而不是 blocks
- [ ] 增加回归测试：追问点击较早 element 时，上下文不会包含锚点之后的内容
- [ ] 增加回归测试：追问点击视觉 element 时，锚点快照会进入 ask prompt/context
- [ ] 增加回归测试：非 listen 模式不会额外暴露 `ASK` 事件
- [ ] 增加回归测试：guardrail 命中时 answer block 创建且 `payload.asks` 包含 student+teacher 条目
- [ ] 增加回归测试：answer SSE 事件携带 `target_element_bid=anchor`
- [ ] 增加回归测试：回填脚本正确匹配历史 mdask/mdanswer 到 anchor element
- [ ] 评估并补充 `audio_complete` 在 ask 场景下的 block 归属测试

## L. 前端 Element 集成（P1）

### L-Phase 1: 数据模型扩展
- [x] `StudyRecordItem` 添加 `payload` 字段（含 `asks` 数组）
- [x] `ChatContentItem` 添加 `payload` 字段
- [x] `SSEParams` 添加 `reload_element_bid` 参数

### L-Phase 2: 追问挂到 Element
- [x] `buildElementContentItem` 提取 `payload.asks` 到 `ask_list`
- [x] `mapRecordsToContent` 历史加载时为有 asks 的 element 创建 ASK 项
- [x] `AskBlock` 改用 `reload_element_bid`（兼容期保留 `reload_generated_block_bid`）
- [x] `ListenModeSlideRenderer` 集成追问：当前步骤 element 有 ask_list 时显示 AskBlock

### L-Phase 3: 去除 NEW_SLIDE 依赖
- [x] 删除 `useChatLogicHook` 中 `SSE_OUTPUT_TYPE.NEW_SLIDE` 处理分支
- [x] 删除 `pendingSlidesRef`、`sortSlidesByTimeline`、`upsertListenSlide`
- [x] 删除 `ListenSlideData` 接口和 `SSE_OUTPUT_TYPE.NEW_SLIDE` 枚举
- [x] `ChatContentItem` 移除 `listenSlides` 字段
- [x] 确认 `buildSlideElementList` 在无 slide 数据后仍正常工作

### L-Phase 4: 清理遗留代码
- [x] 删除 `ListenModeRenderer.tsx`（Reveal.js legacy）并清理 NewChatComp 导入
- [x] 简化 `listenModeUtils.ts` 中 `buildSlidePageMapping`（不再依赖 listenSlides）
- [x] 向 `ListenModeSlideRenderer` 传递追问相关 props（toggleAskExpanded, shifuBid 等）
- [x] Listen 模式不再调用独立 TTS 接口，直接消费 run SSE 中内嵌的音频数据
- [x] ELEMENT handler 中 audio_segments 累积合并（后端每个 patch 只发一个 segment）
- [x] 重写 `buildSlideElementList` 视觉+旁白配对：text(is_renderable=false) 的音频合并到前一个视觉 element
- [x] interaction 正确挂到最后一个视觉 element 的 page
- [x] 去掉 `<Slide>` 依赖，用 ContentRender + AudioPlayer 实现步进式渲染器
- [x] 自动播放：音频播完 → onEnded → currentStepIndex+1 → 显示下一个视觉+音频
- [x] interaction 在所有视觉步骤播完后显示，等待用户输入

### L-Phase 5: 验证与回归
- [ ] Read 模式回归：加载有历史记录的课程，确认渲染不受影响
- [ ] Listen 模式历史加载：确认 element 正确转为 SlideElement 并在 `<Slide>` 中展示
- [ ] Listen 模式流式消费：新课程从头开始，确认 element SSE 事件正确驱动 `<Slide>` 更新
- [ ] 追问功能：点击追问按钮，确认 AskBlock 展开、发送问题、收到流式回答
- [ ] 追问历史：加载有追问历史的课程，确认 `payload.asks` 正确展示
- [ ] 音频播放：确认 autoplay chain 在 listen 模式下正常工作
- [ ] `npm run build` 无编译错误

## M. ask 独立 Element 重构（P0）

Superseded note: 2026-03-23 当前阶段进一步升级为 ask/answer 双独立 element；本节中“ask thread element 持有 asks 历史”的旧表述不再是目标终态。

### M-Phase 0: 设计与协议冻结
- [ ] 设计文档改为独立 `ask/answer` element 模型，移除“ask thread element 持有 asks 历史”约束
- [ ] 冻结 `ElementType.ASK`/`ElementType.ANSWER` 语义：sidecar、`is_renderable=false`、`is_marker=false`、`is_navigable=0`
- [ ] 冻结 ask payload：`anchor_element_bid`
- [ ] 冻结 answer payload：`anchor_element_bid` + `ask_element_bid`
- [ ] 冻结 teacher answer live patch 目标：`target_element_bid=answer_element_bid`

### M-Phase 1: 后端协议与 DTO
- [ ] `ElementType` 枚举新增 `ANSWER`
- [ ] `ELEMENT_TYPE_CODES` 与前端 `ELEMENT_TYPE` 同步新增 `answer`
- [ ] `ElementPayloadDTO` 新增 `ask_element_bid`
- [ ] 更新 `is_renderable/is_marker/is_speakable` 推导规则以覆盖 `ask/answer`
- [ ] 更新 swagger/schema 与序列化输出

### M-Phase 2: 后端写链路
- [ ] `ListenElementRunAdapter` 为每次追问创建新的 ask element
- [ ] answer 首次 teacher 输出时创建独立 answer element
- [ ] ask 的 teacher `CONTENT/AUDIO_SEGMENT/AUDIO_COMPLETE/BREAK` 全部 patch 到 answer element
- [ ] answer 封口后，把最近回答快照写回 answer element `content/audio_*`
- [ ] 新写链路停止把 ask 历史作为 `payload.asks` 主存储

### M-Phase 3: 后端读链路与上下文
- [ ] `_load_ask_context()` 优先从 ask/answer element 序列聚合上下文
- [ ] `reload_element_bid` 解析 anchor 后可定位已有 ask/answer 历史
- [ ] records 聚合直接返回 ask + answer elements，由前端按 anchor 聚合
- [ ] legacy fallback 仅在 ask/answer elements 不存在时才回退到 ask payload.asks / blocks

### M-Phase 4: 回填
- [ ] 回填脚本把历史 mdask/mdanswer 聚合成 ask + answer elements
- [ ] ask/answer element payload 回填 `anchor_element_bid`
- [ ] answer element payload 回填 `ask_element_bid`
- [ ] 回填统计输出 `follow_up_elements_created/asks_matched/answers_matched/skipped`

### M-Phase 5: 前端消费
- [ ] `studyV2.ts` 新增 `ELEMENT_TYPE.ANSWER`
- [ ] `useChatLogicHook` 直接把 `element_type=ask/answer` 聚合为 AskBlock 容器项
- [ ] 移除“从 ask element payload.asks 派生 ASK item”旧逻辑
- [ ] `ListenModeSlideRenderer` 忽略 ask/answer elements 的 slide 参与，但能按 anchor 渲染 AskBlock
- [ ] `AskBlock` 改为消费 ask element 的历史与流式 patch，而不是依赖本地影子状态作为主数据源

### M-Phase 6: 验证
- [ ] 后端 ask/answer element 相关 pytest 通过
- [ ] 前端 listen + ask/answer 历史/流式回归通过
- [ ] `npm run build` 通过
- [ ] pre-commit 通过

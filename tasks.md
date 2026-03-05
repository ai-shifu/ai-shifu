# Tasks (updated 2026-03-06)

## 0. 当前状态核对（已完成）

- [x] 确认 `run` SSE 仍基于 `RunMarkdownFlowDTO`，并包含 `new_slide`
- [x] 确认 `run` 传输层仍发送 `heartbeat`
- [x] 确认 `records` 仍返回 `{records, interaction, slides?}`
- [x] 确认历史数据仍存储在 `learn_generated_blocks` + `learn_generated_audios`
- [x] 确认 `learn_generated_audios.position` 已落地（migration: `3ef04a9b5d37`）
- [x] 确认当前尚无 `learn_generated_elements` 表/模型/迁移

## A. 协议冻结（P0）

- [ ] 冻结 `event_type` 枚举值（含 `heartbeat` 是否入库）
- [ ] 评审方案 A(Flat/Tree)/B 并选定唯一口径（必做门禁）
- [ ] 方案 A：`element_type=svg/html/video/picture/mixed/interaction/diff`（评审 A-Flat / A-Tree）
- [ ] 方案 B：`element_type=interaction/sandbox/picture/video` + `change_type=render/diff`
- [ ] 冻结最终 `element_type` 枚举值（按评审结论）
- [ ] 若选方案 A：冻结是否启用父子结构（`A-Flat` 或 `A-Tree`）
- [ ] 冻结 `records` 默认过滤策略（默认仅返回 element）
- [ ] 冻结 `run` 事件包字段：`type/run_session_bid/run_event_seq/event_type/content`
- [ ] 冻结 `run` 事件类型集合（保留 `audio_segment/audio_complete`，移除 `new_slide`）
- [ ] 冻结 `records` 数据结构：`elements/events`
- [ ] 冻结 element 组装规则：平铺时间线 + `element(audio + previous_visuals)`（按评审方案落地）
- [ ] 冻结 SSE 增量规则：A-Flat/B 同一叙述单元复用同一 `element_bid`；A-Tree 复用同一父 `element_bid`（子节点单独 `element_bid`）
- [ ] 冻结 SSE 部分态语义：run 阶段 `type=element` 默认允许部分内容（`is_final=0`）
- [ ] 冻结 `SVG -> MD_img` 后验合并规则（A-Flat/B：同 `element_bid` 更新；A-Tree：同父节点下增量子节点）
- [ ] 冻结类型变化与 DIFF 规则：方案 A 用 `element_type=diff`（并可类型提升 `svg -> mixed`）；方案 B 用 `change_type=diff`/重渲染
- [ ] 冻结“不做兼容”发布策略（不保留 `response_version` 与旧协议）
- [ ] 明确 feature flag 命名与默认值

## B. 数据库与模型（P1）

- [ ] 新增 `LearnGeneratedElement` SQLAlchemy 模型
- [ ] 若选 A-Flat/B：不引入 `parent_element_bid`
- [ ] 若选 A-Tree：引入 `parent_element_bid` 并约束子 element `is_navigable=0`
- [ ] 完整定义字段注释与默认值（`deleted/status/is_navigable/is_final`）
- [ ] 添加普通索引（无唯一索引）
- [ ] 新增 Alembic migration（建表 + 索引）
- [ ] 本地执行 migration smoke test（upgrade/downgrade）

## C. run 写链路（P1）

- [ ] 生成并贯穿 `run_session_bid`
- [ ] 生成 run 内递增 `run_event_seq`
- [ ] 新增 element writer（含应用层幂等去重）
- [ ] 新增“当前开放 element”组装上下文（按 outline item/session 管理）
- [ ] 按评审选定方案组装并落库 element（A-Flat / A-Tree / B）
- [ ] 同一叙述单元增量更新时复用稳定锚点（A-Flat/B: `element_bid + element_index`；A-Tree: 父 `element_bid + element_index`）
- [ ] `is_final=0` 阶段输出可变快照（推荐累积快照）并持续覆盖稳定锚点（A-Flat/B: 同 `element_bid`；A-Tree: 同父 `element_bid`）
- [ ] 在 `break/interaction/done` 或单元结束时写入 `is_final=1` 终态快照
- [ ] 将语音与上一组图像合并进同一 `element.payload`
- [ ] 若选方案 A：实现类型提升（如 `svg -> mixed`）
- [ ] 若选方案 A：实现 `element_type=diff`、`target_element_bid`、`payload.diff_payload`（类型提升建议先全量再 diff）
- [ ] 若选方案 B：实现 `change_type=diff`、`target_element_bid`、`payload.diff_payload`（run 默认 `target_element_bid=element_bid`，必要时支持 `render` 覆盖）
- [ ] 将 `variable_update/outline_item_update/break/done/error` 作为上层事件落库
- [ ] 输出 `RunElementSSEMessageDTO`（唯一协议）
- [ ] 移除 `new_slide` 事件输出
- [ ] 保留并对齐 `audio_segment/audio_complete` 到新事件包字段
- [ ] 明确并实现：`audio_segment/audio_complete` 不单独落 element，最终并入 `element.payload.audio`

## D. records 读链路（P2）

- [ ] 新增 element records DTO
- [ ] `records` 仅读 `learn_generated_elements`
- [ ] 支持 `include_non_navigable` 查询参数
- [ ] `elements` 默认按 `element_bid` 返回终态快照（`is_final=1` 优先）
- [ ] 中间态增量（`is_final=0`）仅在 `events`（`include_non_navigable=true`）返回
- [ ] 若选 A-Tree：默认 `elements` 返回父节点终态，子节点通过 `events` 或父聚合字段回放
- [ ] 保留外层响应包装 `{code,message,data}`
- [ ] 移除 `records/slides/interaction` 旧返回结构

## E. 历史回填与清洗（P2）

- [ ] 新建回填脚本入口（按 `progress_record_bid` 分批）
- [ ] 从 `learn_generated_blocks` 重建顺序（`position,id`）
- [ ] 合并 `learn_generated_audios` 并生成内容 element（按评审方案）
- [ ] 把上一组图像写入 `element.payload.previous_visuals`
- [ ] 执行清洗规则（孤儿音频、空内容、重复记录）
- [ ] 记录回填审计日志与统计
- [ ] 支持断点续跑与重跑

## F. 前端同步改造（P3）

- [ ] Cook Web 新增 element 消费路径（run）
- [ ] Cook Web 新增 element 消费路径（records）
- [ ] 删除对 `new_slide/slides` 的依赖和处理逻辑
- [ ] run 态 `is_final=0` 按 `element_bid` 实时覆盖渲染，`is_final=1` 再固化导航节点
- [ ] 若选 A-Tree：前端实现 `parent_element_bid` 装配逻辑（父导航 + 子视觉）
- [ ] 听课模式回放验证（时间轴、页切换、音频绑定）

## G. 测试与验收（P3）

- [ ] 单测：`event_type/element_type` 序列化
- [ ] 单测：方案 A 下 `element_type=diff` 的序列化与反序列化
- [ ] 单测：run 事件顺序与 `run_event_seq` 递增
- [ ] 单测：同一 `element_bid` 多次更新保持同 `element_index`
- [ ] 单测：`is_final=1` 后禁止继续更新同一 `element_bid`
- [ ] 单测：`is_final=0` 阶段连续部分内容覆盖后，最终态内容一致
- [ ] 单测：场景 `SVG -> MD_img` 聚合同屏（同 `element_bid`）
- [ ] 单测：records 默认仅 element
- [ ] 单测：`include_non_navigable=true` 返回控制事件
- [ ] 单测：应用层去重与幂等
- [ ] 集成测试：回填前后同章节回放一致性

## H. 灰度与发布（P4）

- [ ] 灰度开关：run element 输出
- [ ] 灰度开关：records element 读取
- [ ] 一次性切换生产协议（不保留旧协议）
- [ ] 观测指标：run 写入成功率/延迟/错误
- [ ] 观测指标：records 查询耗时与返回规模
- [ ] 抽样比对：新旧链路回放一致性
- [ ] 全量切换后删除旧 DTO/旧事件/旧读路径代码

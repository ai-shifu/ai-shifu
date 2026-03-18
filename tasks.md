# Tasks (backend-only, updated 2026-03-18)

Design reference: `docs/learn-generated-elements-design.md`

## 0. 现状核对（已完成）

- [x] 确认当前 `element_type` 仅为 `interaction/sandbox/picture/video`
- [x] 确认 `LearnGeneratedElement` 尚无 `is_renderable/is_new/is_marker/sequence_number/is_speakable/audio_url/audio_segments`
- [x] 确认 `audio_segment/audio_complete` 当前作为非 element 事件落库
- [x] 确认 `records` 已支持 `include_non_navigable`，默认返回 `elements`

## A. 协议冻结（P0）

- [x] 冻结 `element_type`：`html|svg|diff|img|interaction|tables|code|latex|md_img|mermaid|title|text`
- [x] 冻结 element 新字段语义：`is_renderable/is_new/is_marker/sequence_number/is_speakable/audio_url/audio_segments`
- [x] 冻结 `is_new=false` 约束：必须携带 `target_element_bid`
- [x] 冻结 `is_marker=true` 约束：`is_renderable=false` 且 `is_speakable=false`
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

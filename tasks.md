# LLM & TTS Usage Metering

目标：
- 统一记录每次 LLM 调用的 token 消耗与每次 TTS 调用的字数/时长，用于计费管理。

## Checklist

- [x] 查看现有项目结构与 LLM/TTS 调用路径
- [x] 输出统一的设计方案文档（docs/llm-tts-usage-metering.md）
- [x] 新增 usage 统一表模型 + Alembic 迁移
- [x] 新增 metering 服务（UsageContext + record helpers）
- [x] 在 LLM `invoke_llm` / `chat_llm` 中落库使用量
- [x] 在 TTS 流程中落库使用量（segment + request 总量）
- [x] 增加计费侧的聚合查询/报表接口
- [x] 增加测试覆盖（LLM/TTS usage 记录）
- [ ] 评估并补充历史数据回填策略（如需要）

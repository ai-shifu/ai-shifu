# Volcengine Standard TTS (HTTP) Integration Plan

## Context
- 目标：按照 `docs/bytedance-tts-api.md` 接入火山引擎普通语音合成，复用现有火山引擎 TTS 配置，新增一个 provider。

## Checklist
- [x] 阅读 `docs/bytedance-tts-api.md` 并梳理现有 TTS provider/配置/调用链
- [x] 确认新增 provider 的标识名（如 `volcengine_http`）及 appid/token/cluster 与现有配置的映射；如需新增 env，补到 `src/api/flaskr/common/config.py`
- [x] 新增 HTTP provider 实现（如 `src/api/flaskr/api/tts/volcengine_http_provider.py`）：按 v1/tts 组装请求、`Authorization: Bearer;{token}`、`operation=query`、解析 base64 音频与 duration、统一错误处理
- [x] 注册 provider（`src/api/flaskr/api/tts/__init__.py`）、更新 `TTSProvider` enum（`src/api/flaskr/api/tts/base.py`）与校验白名单（`src/api/flaskr/service/tts/validation.py`），必要时更新 shifu 模型/文档注释中的 provider 列表
- [x] 维护前端配置：新增 provider 的 `models`(cluster)、`voices`(voice_type)、`emotions`、speed/pitch 范围与默认值，确保 UI 可选/默认值可落盘
- [x] 处理文本长度限制：在 `src/api/flaskr/service/tts/pipeline.py` 对新 provider 追加 UTF-8 1024 bytes 限制（必要时评估 streaming 分段）
- [x] 更新配置示例与文档：运行 `python scripts/generate_env_examples.py`，检查 `docker/.env.example.full`，补充使用说明
- [ ] 测试：mock HTTP 接口、provider 配置返回、校验/分段逻辑；并跑相关 `pytest` 与 `pre-commit`

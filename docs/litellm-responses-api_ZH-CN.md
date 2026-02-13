# LiteLLM Responses API 迁移说明

本仓库所有服务端 LLM 流量统一经由 LiteLLM 路由。后端 LLM 调用链已从 Chat Completions
(`litellm.completion`) 迁移到 LiteLLM Responses API (`litellm.responses`)，以便在保持多
provider 支持的同时，统一到更长期可持续的接口形态。

说明：本文档是 `docs/litellm-responses-api.md` 的中文版本；若两者存在差异，以英文版为准。

## 术语

- 原生 `/responses`：上游 provider 实现了 OpenAI 兼容的 `POST /responses` 端点（例如
  OpenAI `.../v1/responses`）。
- 适配 `/responses`：上游 provider **没有**实现 `/responses`，但实现了 OpenAI 兼容的
  Chat Completions。在这种情况下我们仍然调用 `litellm.responses(...)`，但会传入
  `custom_llm_provider="custom_openai"`，让 LiteLLM 将请求转换为上游的
  `/chat/completions`。

## 本仓库的实现细节

- 后端封装：`src/api/flaskr/api/llm/__init__.py`
- LiteLLM `responses()` 使用 `input`（而不是 Chat Completions 的 `messages`），并使用
  `max_output_tokens`（而不是 `max_tokens`）。
- `stream_options`（Chat Completions）在 Responses API 中不支持；token usage 从流式事件
  中汇总获取。
- 流式请求通过 `litellm.responses(stream=True, input=[...])` 发起。
- JSON 模式使用 Responses 风格的 schema：
  - `text={"format": {"type": "json_object"}}`
- 流式解析器支持 LiteLLM Responses 的 stream events（例如 `response.output_text.delta`、
  `response.completed`、`response.failed`）。

## Provider 支持矩阵（截至 2026-02-09）

该表描述**上游**支持情况（基于官方文档）以及本仓库的默认策略。

| Provider Key | 官方原生 `/responses` | 仓库默认 | 备注 |
|---|---:|---|---|
| `openai` | 是 | 原生 | OpenAI `.../v1/responses`。 |
| `ark`（火山方舟） | 是 | 原生 | Ark 文档包含 `.../api/v3/responses`，并给出 OpenAI SDK `client.responses.create` 的示例。 |
| `qwen`（阿里云 Model Studio） | 部分支持 | 默认适配；特定 base URL 走原生 | Model Studio 在 **apps compatible-mode** base URL 上提供 Responses API（见下文）。常见的 `.../compatible-mode/v1` 多用于 chat-completions 兼容；为避免 `/responses` 404，本仓库默认走适配模式。 |
| `ernie_v2`（百度千帆） | 文档未明确写 `/responses` | 原生 | 百度文档声明 OpenAI SDK 兼容 `https://qianfan.baidubce.com/v2`。在 `ai-shifu-api-dev` 环境中，`/responses` 对部分模型可用，因此本仓库按原生 `/responses` 处理。 |
| `deepseek` | 未找到 | 适配 | 官方文档展示的是 `/chat/completions`；未找到 `/responses` 文档。 |
| `silicon`（SiliconFlow） | 未找到 | 适配 | 文档展示 OpenAI SDK + `chat.completions`；未找到 `/responses` 文档。 |
| `glm`（智谱 BigModel） | 未确认 | 适配 | 本次调查未能确认官方 `/responses` 文档。 |
| `gemini` | 不适用（provider 专用协议） | LiteLLM Gemini provider | 使用 LiteLLM `custom_llm_provider="gemini"`，而不是 OpenAI 兼容 HTTP `/responses`。 |

### Qwen 原生 `/responses`（Model Studio）

阿里云 Model Studio 文档给出的 OpenAI 兼容 Responses API base URL 为：

```text
https://dashscope-intl.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1
```

文档同时说明仅部分模型可用（例如 `qwen3-max`、`qwen3-max-2026-01-23`），且该能力位于
新加坡区域。实际落地时通常意味着你需要能在 `dashscope-intl` 端点认证的 API key；
中国大陆区域的 key 很可能无法在该端点通过认证。

仓库行为：

- 当 `QWEN_API_URL` 包含 `/api/v2/apps/protocols/compatible-mode/v1` 时，后端会自动将
  Qwen 切换为原生 `/responses`（设置 `custom_llm_provider="openai"`）。
- 否则 Qwen 保持适配模式（`custom_openai`），保证 `litellm.responses` 仍可在仅支持
  chat-completions 的兼容端点上工作。

## Smoke Test：通过 `litellm.responses` 全量测试

脚本：

- `src/api/scripts/test_litellm_responses_providers.py`

示例（在 `ai-shifu-api-dev` 容器内执行）：

```bash
docker exec -e PYTHONUNBUFFERED=1 -w /app ai-shifu-api-dev \
  python scripts/test_litellm_responses_providers.py \
  --per-provider 1 \
  --timeout 60 \
  --max-output-tokens 32
```

期望输出：

- 每个 (provider, model) 输出一行 `[PASS]` / `[FAIL]`
- 任一 provider 失败则以非 0 退出码结束

### `ai-shifu-api-dev` 原生 `/responses` 实测（2026-02-09）

使用容器内当前的密钥和 base URL 配置，原生 `/responses` 可用的 provider：

- `openai`
- `ark`
- `ernie_v2`（至少在该环境下，对 `deepseek-v3` 可用）

以下 provider 在当前配置下原生 `/responses` 不可用（对 `/responses` 返回 404）：

- `qwen`：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- `deepseek`：`https://api.deepseek.com`
- `silicon`：`https://api.siliconflow.cn/v1`

## 参考链接

- LiteLLM Responses API：https://docs.litellm.com.cn/docs/response_api
- 火山方舟 Responses API 文档：
  - https://www.volcengine.com/docs/82379/1585128
  - https://www.volcengine.com/docs/82379/1298459
- 阿里云 Model Studio Responses API：
  - https://www.alibabacloud.com/help/en/model-studio/developer-reference/response-api/
- DeepSeek API 文档（Chat Completions）：
  - https://api-docs.deepseek.com/
- SiliconFlow 文档（OpenAI SDK 的 Chat Completions）：
  - https://docs.siliconflow.cn/en/userguide/capabilities/text-generation
- 百度千帆社区示例（OpenAI SDK Chat Completions）：
  - https://qianfan.cloud.baidu.com/qianfandev/topic/685606
- 百度文心千帆 OpenAI SDK 兼容：
  - https://ai.baidu.com/ai-doc/WENXINWORKSHOP/2m3fihw8s

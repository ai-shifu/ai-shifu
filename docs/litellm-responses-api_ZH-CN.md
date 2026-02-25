2# LiteLLM Responses API 迁移说明

本仓库所有服务端 LLM 流量统一经由 LiteLLM 路由。后端调用链已从 Chat Completions
(`litellm.completion`) 迁移到 LiteLLM Responses API (`litellm.responses`)，以便在保持
多 provider 支持的同时，统一到更长期可持续的接口形态。

说明：本文档是 `docs/litellm-responses-api.md` 的中文版本；若两者有差异，以英文版为准。

## 更新快照（2026-02-25）

- 重新核对了 LiteLLM 最新版本与各 provider 官方文档。
- 更新了 provider `/responses` 支持矩阵。
- 对齐了当前代码实现（`src/api/flaskr/api/llm/__init__.py`）。

## LiteLLM 版本现状（截至 2026-02-25）

- PyPI 最新版本：`1.81.15`（发布日期 `2026-02-24`）。
- 仓库当前固定版本：`src/api/requirements.txt` 中 `litellm==1.80.11`。
- 本次仅更新文档，不改动依赖版本。

## 术语

- 原生 `/responses`：上游 provider 官方文档明确支持 OpenAI 风格
  `POST /responses` 端点。
- 适配 `/responses`：上游主要提供 chat-completions 风格接口，我们仍调用
  `litellm.responses(...)`，并使用 `custom_llm_provider="custom_openai"` 让
  LiteLLM 进行上游适配。

## 本仓库实现细节

- 后端封装：`src/api/flaskr/api/llm/__init__.py`
- 统一使用 `litellm.responses(...)`，关键参数为：
  - `input`（而非 Chat Completions 的 `messages`）
  - `max_output_tokens`（而非 `max_tokens`）
- 流式解析器处理 Responses 事件（`response.output_text.delta`、
  `response.completed`、`response.failed` 等）。
- JSON 模式采用 Responses 风格：
  - `text={"format": {"type": "json_object"}}`
- Qwen 特殊逻辑：
  - 当 `QWEN_API_URL` 包含 `/api/v2/apps/protocols/compatible-mode/v1` 时，
    自动切到原生模式（`custom_llm_provider="openai"`）。
  - 其他情况下维持适配模式（`custom_openai`），避免经典兼容端点 `/responses`
    返回 404。

## Provider 支持矩阵（核对日期：2026-02-25）

该表描述**官方上游文档**与本仓库默认策略。

| Provider Key | 官方原生 `/responses` | 仓库默认 | 备注 |
|---|---:|---|---|
| `openai` | 是 | 原生 | 官方提供 `POST /v1/responses`。 |
| `ark`（火山方舟） | 是 | 原生 | 官方有 Responses API 专章，并给出 `client.responses.create` 示例。 |
| `qwen`（阿里云 Model Studio） | 部分支持 | 默认适配；特定 base URL 走原生 | 官方在新加坡 `dashscope-intl` 的 apps compatible-mode base URL 文档中提供 Responses API。 |
| `ernie_v2`（百度千帆） | 文档未明确写 `/responses` | 原生 | 官方文档明确 OpenAI 兼容 base URL 为 `https://qianfan.baidubce.com/v2`，示例以 chat-completions 形态为主。 |
| `deepseek` | 未找到 | 适配 | 官方文档是 `/chat/completions`；未找到官方 `/responses` 页面。 |
| `silicon`（SiliconFlow） | 未找到 | 适配 | 官方 OpenAI 兼容示例为 `client.chat.completions.create(...)`。 |
| `glm`（智谱 BigModel） | 未找到 | 适配 | 官方 OpenAI 兼容文档为 `https://open.bigmodel.cn/api/paas/v4/` + chat-completions 示例。 |
| `gemini` | 未见 OpenAI 原生 `/responses` 文档 | LiteLLM Gemini provider | Gemini 主协议是 `generateContent`；OpenAI 兼容页当前主要覆盖 `/chat/completions`。仓库使用 LiteLLM `custom_llm_provider="gemini"`。 |

### Qwen 原生 `/responses` 说明

Model Studio 当前文档给出的形态为：

```text
base_url: https://dashscope-intl.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1
endpoint: POST .../responses
```

文档约束包括：

- 新加坡区域可用。
- 仅部分模型支持（例如 `qwen3-max`、`qwen3-max-2026-01-23`）。
- 部分 OpenAI Responses 参数不支持。

### Ark / Qianfan 备注

- Ark 文档已提供明确的 Responses API 与迁移说明。
- 本次核对中，百度千帆官方文档仍未明确发布 `/responses`，因此 `ernie_v2` 的“原生”
  策略仍属于“仓库策略 + 环境实测”，不是严格的官方文档保证。

## Smoke Test：按当前密钥配置自检

脚本：

- `src/api/scripts/test_litellm_responses_providers.py`

示例：

```bash
docker exec -e PYTHONUNBUFFERED=1 -w /app ai-shifu-api-dev \
  python scripts/test_litellm_responses_providers.py \
  --per-provider 1 \
  --timeout 60 \
  --max-output-tokens 32
```

期望输出：

- 每个 `(provider, model)` 输出一行 `[PASS]` / `[FAIL]`。
- 任一 provider 失败时退出码为非 0。

## 参考链接（官方文档）

- LiteLLM
  - https://pypi.org/project/litellm/
  - https://docs.litellm.ai/docs/response_api
- OpenAI
  - https://platform.openai.com/docs/api-reference/responses
- 火山方舟（Ark）
  - https://www.volcengine.com/docs/82379/1569618
  - https://www.volcengine.com/docs/82379/1585128
  - https://www.volcengine.com/docs/82379/1099522
- 阿里云 Model Studio（Qwen）
  - https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-responses
- 百度千帆 / 文心大模型平台
  - https://ai.baidu.com/ai-doc/WENXINWORKSHOP/2m3fihw8s
- DeepSeek
  - https://api-docs.deepseek.com/
- SiliconFlow
  - https://docs.siliconflow.cn/en/userguide/capabilities/text-generation
- 智谱 BigModel（GLM）
  - https://docs.bigmodel.cn/cn/guide/develop/openai/introduction
- Google Gemini
  - https://ai.google.dev/docs/gemini_api_overview/
  - https://ai.google.dev/gemini-api/docs/openai

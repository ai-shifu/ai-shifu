# LiteLLM Responses API Migration

This repository routes all server-side LLM traffic through LiteLLM. The backend
LLM call path has been migrated from Chat Completions (`litellm.completion`) to
the LiteLLM Responses API (`litellm.responses`) so we can use a single, future
proof interface while keeping multi-provider support.

Chinese translation: `docs/litellm-responses-api_ZH-CN.md`

## Terminology

- Native `/responses`: the upstream provider implements an OpenAI-compatible
  `POST /responses` endpoint (for example OpenAI `.../v1/responses`).
- Adapted `/responses`: the upstream provider does **not** implement
  `/responses` but does implement OpenAI-compatible Chat Completions. In this
  case we still call `litellm.responses(...)`, but pass
  `custom_llm_provider="custom_openai"` so LiteLLM transforms the request to
  `/chat/completions` upstream.

## Implementation In This Repo

- Backend wrapper: `src/api/flaskr/api/llm/__init__.py`
- LiteLLM `responses()` uses `input` (not Chat Completions `messages`) and
  `max_output_tokens` (not `max_tokens`).
- `stream_options` (Chat Completions) is not supported on Responses API. Usage
  is collected from stream events instead.
- Streaming requests call `litellm.responses(stream=True, input=[...])`.
- JSON mode uses Responses-style schema:
  - `text={"format": {"type": "json_object"}}`
- Streaming parser handles LiteLLM Responses stream events (event types like
  `response.output_text.delta`, `response.completed`, `response.failed`).

## Provider Support Matrix (As Of 2026-02-09)

This table describes **upstream** support (based on vendor docs) and what we do
in this repository.

| Provider Key | Official Native `/responses` | Repo Default | Notes |
|---|---:|---|---|
| `openai` | Yes | Native | OpenAI `.../v1/responses`. |
| `ark` (Volcengine Ark) | Yes | Native | Ark documents `.../api/v3/responses` and OpenAI SDK `client.responses.create`. |
| `qwen` (Alibaba Cloud Model Studio) | Partial | Adapted by default; native on specific base URL | Model Studio documents Responses API on the **apps compatible-mode** base URL (see below). The classic `.../compatible-mode/v1` endpoint is commonly used for chat-completions compatibility; we keep the adapted mode by default to avoid `/responses` 404s. |
| `ernie_v2` (Baidu Qianfan) | Not explicitly documented | Native | Baidu documents OpenAI SDK compatibility on `https://qianfan.baidubce.com/v2`. In `ai-shifu-api-dev`, the `/responses` endpoint works for some models; we treat this provider as native `/responses`. |
| `deepseek` | Not found | Adapted | Official docs show `/chat/completions`; no `/responses` doc found. |
| `silicon` (SiliconFlow) | Not found | Adapted | Docs show OpenAI SDK + `chat.completions`; no `/responses` doc found. |
| `glm` (Zhipu BigModel) | Unverified | Adapted | No official `/responses` doc confirmed in this investigation. |
| `gemini` | N/A (provider-specific) | LiteLLM Gemini provider | Uses LiteLLM `custom_llm_provider="gemini"` rather than OpenAI-compatible HTTP `/responses`. |

### Qwen Native `/responses` (Model Studio)

Alibaba Cloud Model Studio documents OpenAI-compatible Responses API with base
URL:

```text
https://dashscope-intl.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1
```

It also documents that only some models are supported (example: `qwen3-max`,
`qwen3-max-2026-01-23`) and that this is available in the Singapore region.
In practice this usually means you need an API key that is valid for the
`dashscope-intl` endpoint; a mainland China key may not authenticate there.

Repository behavior:

- If `QWEN_API_URL` contains `/api/v2/apps/protocols/compatible-mode/v1`, the
  backend automatically switches Qwen to native `/responses` by setting
  `custom_llm_provider="openai"`.
- Otherwise, Qwen stays in adapted mode (`custom_openai`) so `litellm.responses`
  continues to work against chat-completions-only compatible endpoints.

## Smoke Test: All Providers via `litellm.responses`

Script:

- `src/api/scripts/test_litellm_responses_providers.py`

Example (inside `ai-shifu-api-dev` container):

```bash
docker exec -e PYTHONUNBUFFERED=1 -w /app ai-shifu-api-dev \
  python scripts/test_litellm_responses_providers.py \
  --per-provider 1 \
  --timeout 60 \
  --max-output-tokens 32
```

Expected output:

- Prints one line per tested (provider, model) with `[PASS]` / `[FAIL]`
- Exits non-zero if any provider fails

### `ai-shifu-api-dev` Native `/responses` Check (2026-02-09)

Using the container's current credentials and base URLs, native `/responses`
worked for:

- `openai`
- `ark`
- `ernie_v2` (at least for `deepseek-v3` in this environment)

Native `/responses` did **not** work for the following provider endpoints as
configured:

- `qwen` on `https://dashscope.aliyuncs.com/compatible-mode/v1` (404 on `/responses`)
- `deepseek` on `https://api.deepseek.com` (404 on `/responses`)
- `silicon` on `https://api.siliconflow.cn/v1` (404 on `/responses`)

## References

- LiteLLM Responses API: https://docs.litellm.com.cn/docs/response_api
- Volcengine Ark Responses API docs:
  - https://www.volcengine.com/docs/82379/1585128
  - https://www.volcengine.com/docs/82379/1298459
- Alibaba Cloud Model Studio Responses API:
  - https://www.alibabacloud.com/help/en/model-studio/developer-reference/response-api/
- DeepSeek API docs (Chat Completions):
  - https://api-docs.deepseek.com/
- SiliconFlow docs (Chat Completions via OpenAI SDK):
  - https://docs.siliconflow.cn/en/userguide/capabilities/text-generation
- Baidu Qianfan community example (OpenAI SDK Chat Completions):
  - https://qianfan.cloud.baidu.com/qianfandev/topic/685606
- Baidu (Wenxin Workshop) OpenAI SDK compatibility:
  - https://ai.baidu.com/ai-doc/WENXINWORKSHOP/2m3fihw8s

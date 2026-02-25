# LiteLLM Responses API Migration

This repository routes all server-side LLM traffic through LiteLLM. The backend
LLM path has been migrated from Chat Completions (`litellm.completion`) to the
LiteLLM Responses API (`litellm.responses`) so we can keep one interface while
retaining multi-provider support.

Chinese translation: `docs/litellm-responses-api_ZH-CN.md`

## Update Snapshot (2026-02-25)

- Re-checked the latest LiteLLM release and provider docs.
- Refreshed provider `/responses` support status using official documentation.
- Synced this doc with current code in `src/api/flaskr/api/llm/__init__.py`.

## LiteLLM Version Status (As Of 2026-02-25)

- Latest LiteLLM on PyPI: `1.81.15` (released `2026-02-24`).
- Current repo pin: `litellm==1.80.11` in `src/api/requirements.txt`.
- This document update does **not** change dependency versions.

## Terminology

- Native `/responses`: the upstream provider documents/supports an OpenAI-style
  `POST /responses` endpoint.
- Adapted `/responses`: the upstream provider exposes chat-completions style
  endpoints, and we still call `litellm.responses(...)` by using
  `custom_llm_provider="custom_openai"` so LiteLLM adapts upstream calls.

## Implementation In This Repo

- Backend wrapper: `src/api/flaskr/api/llm/__init__.py`
- Uses `litellm.responses(...)` with:
  - `input` (instead of Chat Completions `messages`)
  - `max_output_tokens` (instead of `max_tokens`)
- Streaming parser handles Responses events (`response.output_text.delta`,
  `response.completed`, `response.failed`, etc.).
- JSON mode uses Responses schema:
  - `text={"format": {"type": "json_object"}}`
- Qwen special handling:
  - If `QWEN_API_URL` contains
    `/api/v2/apps/protocols/compatible-mode/v1`, we switch to native mode
    (`custom_llm_provider="openai"`).
  - Otherwise Qwen remains adapted mode (`custom_openai`) to avoid `/responses`
    404s on classic compatible endpoints.

## Provider Support Matrix (Checked On 2026-02-25)

This table describes **official upstream docs** and the default behavior in this
repository.

| Provider Key | Official Native `/responses` | Repo Default | Notes |
|---|---:|---|---|
| `openai` | Yes | Native | Official `POST /v1/responses`. |
| `ark` (Volcengine Ark) | Yes | Native | Ark has a dedicated Responses API section and `client.responses.create` examples. |
| `qwen` (Alibaba Cloud Model Studio) | Partial | Adapted by default; native on specific base URL | Responses API is documented for the Singapore `dashscope-intl` compatible-mode apps base URL. |
| `ernie_v2` (Baidu Qianfan) | Not explicitly documented | Native | Official docs clearly document OpenAI compatibility at `https://qianfan.baidubce.com/v2` (main examples are chat-completions style). |
| `deepseek` | Not found | Adapted | Official docs expose `/chat/completions`; no official `/responses` page found. |
| `silicon` (SiliconFlow) | Not found | Adapted | Official OpenAI-compatible docs show `client.chat.completions.create(...)`. |
| `glm` (Zhipu BigModel) | Not found | Adapted | Official OpenAI-compatible docs show base URL `https://open.bigmodel.cn/api/paas/v4/` with chat-completions examples. |
| `gemini` | No OpenAI-native `/responses` documented | LiteLLM Gemini provider | Gemini primary API is `generateContent`; OpenAI compatibility page currently documents `/chat/completions`. Repo uses LiteLLM `custom_llm_provider="gemini"`. |

### Notes For Qwen Native `/responses`

Model Studio currently documents:

```text
base_url: https://dashscope-intl.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1
endpoint: POST .../responses
```

Documented constraints include:

- Singapore region only.
- Only specific models are listed (for example `qwen3-max`,
  `qwen3-max-2026-01-23`).
- Some OpenAI Responses parameters are not supported.

### Notes For Ark / Qianfan

- Ark docs now include explicit Responses API sections and migration docs.
- Baidu Qianfan docs in this check do not explicitly publish `/responses`;
  therefore `ernie_v2` is still a "native in repo strategy + env validation"
  decision, not a strict vendor-doc guarantee.

## Smoke Test: Verify With Your Current Credentials

Script:

- `src/api/scripts/test_litellm_responses_providers.py`

Example:

```bash
docker exec -e PYTHONUNBUFFERED=1 -w /app ai-shifu-api-dev \
  python scripts/test_litellm_responses_providers.py \
  --per-provider 1 \
  --timeout 60 \
  --max-output-tokens 32
```

Expected output:

- One line per tested `(provider, model)` with `[PASS]` or `[FAIL]`.
- Exit code is non-zero if any provider fails.

## References (Official Docs)

- LiteLLM
  - https://pypi.org/project/litellm/
  - https://docs.litellm.ai/docs/response_api
- OpenAI
  - https://platform.openai.com/docs/api-reference/responses
- Volcengine Ark
  - https://www.volcengine.com/docs/82379/1569618
  - https://www.volcengine.com/docs/82379/1585128
  - https://www.volcengine.com/docs/82379/1099522
- Alibaba Cloud Model Studio (Qwen)
  - https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-responses
- Baidu Qianfan / Wenxin Workshop
  - https://ai.baidu.com/ai-doc/WENXINWORKSHOP/2m3fihw8s
- DeepSeek
  - https://api-docs.deepseek.com/
- SiliconFlow
  - https://docs.siliconflow.cn/en/userguide/capabilities/text-generation
- Zhipu BigModel (GLM)
  - https://docs.bigmodel.cn/cn/guide/develop/openai/introduction
- Google Gemini
  - https://ai.google.dev/docs/gemini_api_overview/
  - https://ai.google.dev/gemini-api/docs/openai

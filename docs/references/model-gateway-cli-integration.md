---
title: Model Gateway CLI Integration
last_reviewed: 2026-09-01
canonical: true
---

## Model Gateway CLI Integration Contract

This guide is the implementation contract for an external official CLI that
signs in with an AI-Shifu account and spends that account's existing credits
through the AI-Shifu model gateway. The application CLI belongs in its own
project. AI-Shifu contains the server routes, automated tests, and this guide,
not a production client application.

The default production origin is `https://app.ai-shifu.cn`. Replace it with
the target deployment origin in every example. Non-loopback deployments must
use HTTPS.

## End-to-end sequence

The CLI should implement these steps:

1. Start device authorization and save the returned `device_code` privately.
2. Open `verification_uri_complete` in the system browser.
3. Poll the token endpoint at the returned interval until approved, denied, or
   expired.
4. Save the approved token in the operating system credential store or an
   owner-only file outside the application package.
5. Call `/api/gateway/account` and `/api/gateway/v1/models` with a Bearer token.
6. Send Chat Completions with a new `Idempotency-Key` for every logical model
   request.
7. On HTTP 401, clear the token and restart authorization. On HTTP 402, show
   the returned billing URL instead of retrying the model call.

Never print the device code or token. The user-facing pairing code and
verification URL may be displayed.

## Start device authorization

Request:

```http
POST /api/user/device/authorize HTTP/1.1
Host: app.ai-shifu.cn
Content-Type: application/json

{
  "device_name": "Example Model CLI",
  "device_os": "macOS 15.5",
  "client_version": "0.1.0"
}
```

Response:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "device_code": "private-high-entropy-value",
    "user_code": "AC4-7HK",
    "verification_uri": "https://app.ai-shifu.cn/login/device",
    "verification_uri_complete": "https://app.ai-shifu.cn/login/device?code=AC4-7HK",
    "expires_in": 600,
    "interval": 5
  }
}
```

Store `device_code`, the issuing origin, polling interval, and calculated
expiry together. Refuse to send a stored code to a different origin.

## Poll for approval

```http
POST /api/user/device/token HTTP/1.1
Host: app.ai-shifu.cn
Content-Type: application/json

{
  "device_code": "private-high-entropy-value"
}
```

The common response envelope contains one of these states:

- `pending`: wait at least `interval` seconds and poll again;
- `approved`: save the non-empty `token` and delete pending authorization data;
- `denied`: stop and delete pending authorization data; or
- a nonzero business code: treat the request as invalid or expired and start a
  new authorization only after the user asks to retry.

Do not start another authorization while the user is approving the previous
one. A second pending request makes it easy for a CLI to wait on the wrong
device code.

## Authenticate gateway requests

All gateway endpoints use the standard Bearer header:

```http
Authorization: Bearer <AI-Shifu-session-token>
```

Do not send the token in the URL, JSON body, query string, logs, analytics, or
error reports.

## Read account and credits

```http
GET /api/gateway/account HTTP/1.1
Host: app.ai-shifu.cn
Authorization: Bearer <token>
```

Successful response:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user": {
      "user_id": "user-business-id",
      "name": "Example User",
      "language": "zh-CN"
    },
    "wallet": {
      "available_credits": 100,
      "reserved_credits": 0
    },
    "billing_url": "https://app.ai-shifu.cn/admin/billing"
  }
}
```

The CLI should show available and reserved values separately. Reserved credits
belong to model operations that have started but are not fully settled.

## List callable models

```http
GET /api/gateway/v1/models HTTP/1.1
Host: app.ai-shifu.cn
Authorization: Bearer <token>
```

```json
{
  "object": "list",
  "data": [
    {
      "id": "ai-shifu-default",
      "object": "model",
      "owned_by": "ai-shifu",
      "display_name": "AI-Shifu Default",
      "credit_multiplier": 1,
      "resolved_model": "configured-rated-model"
    },
    {
      "id": "configured-rated-model",
      "object": "model",
      "owned_by": "ai-shifu",
      "display_name": "Configured Rated Model",
      "credit_multiplier": 1
    }
  ]
}
```

The list is the source of truth for client model selection. Do not hardcode
provider names or assume that every model configured on the server is billable.

## Non-streaming Chat Completions

Generate a unique idempotency value for the logical request and retain it only
while retrying that same request.

```http
POST /api/gateway/v1/chat/completions HTTP/1.1
Host: app.ai-shifu.cn
Authorization: Bearer <token>
Idempotency-Key: 019d2b28-73ca-7f91-bc62-1850d63ca101
Content-Type: application/json

{
  "model": "ai-shifu-default",
  "messages": [
    {"role": "user", "content": "Explain recursion in one paragraph."}
  ],
  "max_tokens": 512,
  "stream": false
}
```

The response follows the OpenAI Chat Completions JSON shape. Supported optional
request fields are `temperature`, `top_p`, `stop`, `seed`, `presence_penalty`,
`frequency_penalty`, `response_format`, `tools`, `tool_choice`, and
`parallel_tool_calls`.

If `max_tokens` is omitted, the gateway uses the smaller of 4096 and the model
limit. A value above the model limit is rejected rather than silently changed.

## Streaming Chat Completions

Set `stream` to `true` and parse Server-Sent Events:

```http
POST /api/gateway/v1/chat/completions HTTP/1.1
Host: app.ai-shifu.cn
Authorization: Bearer <token>
Idempotency-Key: 019d2b28-c3d3-7c65-a905-b32f8935cb18
Content-Type: application/json

{
  "model": "configured-rated-model",
  "messages": [
    {"role": "user", "content": "Say hello."}
  ],
  "stream": true
}
```

Each event has the form `data: <JSON>`. Stop after `data: [DONE]`. Preserve
`delta.tool_calls` fragments as well as `delta.content`; tool-call arguments
can be split across multiple events.

The response includes `X-AI-Shifu-Request-ID`, which may be logged for support
and correlation. Do not log the prompt, response, token, or authorization
header by default.

## Tool calls

Tool definitions use the OpenAI Chat Completions format:

```json
{
  "model": "ai-shifu-default",
  "messages": [
    {"role": "user", "content": "What is the weather in Shanghai?"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Return current weather for one city",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {"type": "string"}
          },
          "required": ["city"]
        }
      }
    }
  ],
  "tool_choice": "auto",
  "stream": true
}
```

The CLI owns tool execution. Send the assistant tool call and resulting `tool`
message in a later Chat Completions request with a new idempotency key.

## Error handling

Gateway errors use real HTTP statuses:

```json
{
  "error": {
    "type": "invalid_request_error",
    "code": "insufficient_credits",
    "message": "Insufficient credits",
    "billing_url": "https://app.ai-shifu.cn/admin/billing"
  }
}
```

| HTTP status | CLI action |
| --- | --- |
| `400` | Show the safe message and let the user correct the model or payload. |
| `401` | Delete the stored token and start device authorization again. |
| `402` | Show available credits and open `billing_url` when requested. Do not retry automatically. |
| `409` | The idempotency key was already used. Do not generate a new key and silently repeat an uncertain request. |
| `429` | Back off according to deployment policy. |
| `502` or `503` | Report a transient model-service failure. Retry only with an explicit user action and a new logical request. |

For SSE, an error that happens after headers were sent arrives as a final JSON
error event followed by `[DONE]`.

## Idempotency rules

- Generate one unpredictable key per logical model request.
- Keep the key at 90 characters or fewer; UUID and UUIDv7 values fit.
- Reuse that key only when determining the outcome of the same uncertain
  request.
- Never reuse a key for different messages, tools, or model settings.
- HTTP 409 means the server has already seen the key; this version does not
  replay a stored completion body.

## Recommended credential behavior

- Prefer the operating system credential store.
- If a file is necessary, create it outside the application package with mode
  `0600` before writing the token, and update it atomically.
- Bind pending device authorization data to the issuing origin.
- Serialize login and refresh attempts so two UI actions cannot overwrite each
  other's pending state.
- Clear credentials on HTTP 401 or explicit logout.
- Never embed a shared application secret in a distributed CLI.

## External CLI acceptance checklist

- Browser login completes without collecting a password, SMS code, or token in
  the CLI process UI.
- Denied, expired, and already-consumed device codes stop safely.
- Account balance is shown before the first paid model call.
- The model selector is populated only from `/v1/models`.
- Non-streaming text, streaming text, and streamed tool calls are parsed.
- HTTP 402 exposes the billing action and causes no automatic retry.
- Repeated `Idempotency-Key` values never create a second paid call.
- Tokens, prompts, responses, and provider details stay out of logs and crash
  reports.

See [Official Client Model Gateway](../design-docs/official-client-model-gateway.md)
for server-side decisions and settlement behavior.

---
title: MarkdownFlow Input Budget
status: implemented
owner_surface: learner
last_reviewed: 2026-11-04
canonical: true
---

# MarkdownFlow Input Budget

Every MarkdownFlow 2.0 `GatewayModel` request is checked immediately before
`chat_llm`. The application budget is counted in bytes of compact UTF-8 JSON
containing `messages` and `tools`, with `ensure_ascii=False` and separators
`(',', ':')`. The empty tools array counts even when no tools are sent. Unicode
bytes, JSON escaping, field names and structure all count. This is not a
provider token limit or a guarantee about the provider's final HTTP
serialization, model context window or output allowance.

The budget follows the selected model's input token ceiling: one byte per
token, never below the 256 KiB default. A course selection (numbered slot) is
resolved to its routed model first. The ceiling is read from
`LLM_MODEL_MAX_INPUT_TOKENS` (routed model id -> tokens, as published by the
serving provider), then LiteLLM metadata for the serving provider. A model with
neither keeps the fixed default of **262144 bytes (256 KiB)**. Lesson text runs
about three bytes per token in Chinese and four in English, so a budget at the
ceiling leaves wide headroom, but chat-template framing and output are not
counted and the provider remains the final judge of length. Callers may still
pass an explicit budget, as the teaching-summary request (40 KiB) does.

The check includes the final mapped current system instructions, initial memory,
complete authored script and brief (or the saved prompt in an existing session),
extra documents, conversation history, tool-call arguments, answers, tool
results, retry prompts and the effective offered tool definitions. It runs for
every streaming and non-streaming request, including subsequent tool-loop
requests, teacher previews and the independent memory-admission judge.
Provider credentials, routing and usage accounting remain with `chat_llm`.

An envelope exactly at the limit is sent unchanged. A larger input raises
`InputBudgetExceededError` before opening the gateway generator, provider I/O or
billing. No part of an answer, author instruction or tool chain is shortened;
no stored history or memory is deleted or summarized. The memory-section
projection remains independently limited to 32768 JSON characters.

For teaching, the engine emits `input_budget_exceeded`, the host saves the
failed turn and full deferred-answer evidence, and the existing SSE error path
reports localized API error **4020**. It does not finish or reset the lesson,
show a success terminal event, or automatically repeat an unchanged oversized
request. Budget-refused turns do not consume the turn-limit backstop. Already
shown text is finalized and committed as history elements before reporting the
failure, without sending a successful DONE boundary. An explicitly accepted
`finish` remains terminal even if an unnecessary post-finish tool-result request
is refused; the lesson is never reopened by that follow-up failure.
A refused memory-admission request continues to deny the proposed
write without interrupting the main teaching call.

A course owner may need to reduce the lesson's inputs. Restarting a lesson is
not a universal fix: a large script can exceed the budget even without history.
New prompts do not insert memory values into authored text; existing expanded
history still counts in full. Retrieval, semantic compression and automatic
recovery are separate follow-ups. The Python constructor accepts a positive
`input_budget_bytes` for controlled tests and fixed-size auxiliary requests;
otherwise the budget follows the model as described above, configured
per deployment with `LLM_MODEL_MAX_INPUT_TOKENS`. No database migration is
introduced.

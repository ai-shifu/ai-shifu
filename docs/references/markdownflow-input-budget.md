---
title: MarkdownFlow Input Budget
status: implemented
owner_surface: learner
last_reviewed: 2026-10-07
canonical: true
---

# MarkdownFlow Input Budget

Every MarkdownFlow 2.0 `GatewayModel` request is checked immediately before
`chat_llm`. The application budget is **262144 bytes (256 KiB)** of compact
UTF-8 JSON containing `messages` and `tools`, with `ensure_ascii=False` and
separators `(',', ':')`. The empty tools array counts even when no tools are
sent. Unicode bytes, JSON escaping, field names and structure all count.
This is not a provider token limit or a guarantee about the provider's final
HTTP serialization, model context window or output allowance.

The check includes the final mapped current system instructions, initial memory,
complete rendered script and brief (including repeated exact substitutions),
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
not a universal fix: a large script or exact substituted value can exceed the
budget even without history. Retrieval, semantic compression, per-model token
budgets and automatic recovery are separate follow-ups. The Python constructor
accepts a positive `input_budget_bytes` for controlled tests; production factories
use the default. No deployment setting or database migration is introduced.

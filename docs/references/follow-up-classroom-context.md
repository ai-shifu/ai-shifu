---
title: Follow-up Classroom Context
status: implemented
owner_surface: learner
last_reviewed: 2026-10-09
canonical: true
---

# Follow-up Classroom Context

Text and Live follow-up questions remain separate conversations anchored to a
selected classroom element. LLM and external-provider prompts use the shared
`learn/follow_up_context.py` builder. Live keeps its independent voice instructions;
it does not inherit text Course Prompts. Explicit memory authorization remains
[the course-reference contract](course-memory-references.md).

For a persisted anchor, history consists of recent teaching and learner answers
before its generated block, the selected element's exact text, and recent
ASK/ANSWER sidecars belonging to that anchor. This includes the visible 2.0
conversation persisted through the existing generated-block bridge. It does not
read raw agent sessions, tool calls or generation prompts. For 2.0, the existing
versioned turn record supplies only its submitted `values` list through the rewind
codec; checkpoint memory, pending tools and other configuration never become model
messages. That input precedes its turn's teaching, including the selected anchor's
own turn. Older formats and malformed value lists yield no learner text.
The anchor's full generated block is excluded because it can contain later text.
Later blocks and sidecars belonging to other anchors are excluded as well.

Prior classroom rows must be active and undeleted and match the anchor's learning
attempt, learner, course and lesson. Only content blocks become assistant messages
and legacy interaction blocks become learner messages. 2.0 submitted values also
become learner messages in their original turn order. Empty content is omitted. A
resolved anchor from another learning attempt yields no history. If the anchor's
active generated block is absent, only the selected text and its own sidecar are
used; no latest-block fallback broadens that anchor's context.

The existing history limit is shared between prior classroom turns and sidecar
messages. Recent sidecar messages take priority, then remaining slots retain the
most recent preceding classroom rows. The selected nonempty anchor remains an
additional message, including when the limit is zero. Legacy embedded ASK history
still works; canonical sidecars take precedence. Calls without a resolved element
retain the existing generated-block fallback for legacy compatibility.

Context reads do not mutate classroom history, progress, memory or agent sessions.
Existing provider routing, SSE, billing and persistence paths remain in use.
Semantic recall, transcript compression and teaching-quality acceptance are
separate work; this bounded context does not promise the entire lesson transcript.

## Current course memory in 2.0

When the deployment selects 2.0, the existing memory facade also loads course notes
without variable definitions, alongside defined variables and registered system
fields. An explicit resolved snapshot, including an empty snapshot, prevents a
second read. Text dispatch opts into the same reader before handing off its snapshot;
Live loads its snapshot when building a new conversation with independent voice rules.

Both LLM and external-provider prompts receive a separate untrusted JSON data block,
even when an author supplied a follow-up prompt without the Course Prompt slot.
Its encoded UTF-8 payload is at most 16,384 bytes. Complete values are selected in
snapshot order; oversized values are omitted, never truncated or deleted. Omitted
keys remain unknown to that request. This bounds only the added memory block, not
the pre-existing course instructions or conversation budget. JSON string keys and
values escape angle brackets, ampersands and braces to preserve host boundaries.

Current facts must not replace historical quotations. Context loading reads memory only;
it cannot authorize new writes or restore deleted notes. Fresh requests observe
stored updates and deletions. An ongoing Live provider session retains its creation
snapshot. Legacy 1.0 behavior and cross-course custom-memory isolation are unchanged.

## Provider delivery boundary

The default LLM and Live builder consume this memory snapshot. Dify serializes the
shared provider messages into its outbound query, and Get Biji uses the contextual
LLM synthesis factory after retrieval. Coze native chat receives the host context
through `additional_messages` when the resolved URL path is `/v3/chat` (including
an absolute URL or trailing slash). Because the API accepts only user/assistant
roles, course instructions and the already encoded, untrusted memory block are
wrapped in a labelled JSON reference message with the user role. They do not
replace the bot's own system configuration. Prior user/assistant messages retain
order and exact text; assistant messages use `type=answer`. The current query is
always the final user message, removing only its existing trailing host copy.

Coze permits at most 100 additional messages. The adapter reserves one slot for
the current query and one for nonempty course context, then keeps the newest
history within the remaining slots. It does not truncate individual values or
mutate the host's message list. The existing 16 KiB memory-block budget still
applies; this message-count limit is not a new whole-request byte budget.
Malformed-response warnings contain only length metadata, never provider content.
Valid error events raise a fixed provider error without echoing the response into
the host's exception warning. Native SSE `event: error` and
`event: conversation.chat.failed` headers are recognized before JSON decoding,
including payloads without an embedded event field and failures after partial
answer chunks. Nonfailure event headers do not produce malformed-frame warnings.

An explicit `extra_body.additional_messages` continues to own the entire payload
and opts out of automatic context delivery. Other extra-body fields, including
custom variables and history settings, retain their existing precedence. Bespoke
non-v3 endpoints keep the previous query-only payload. Existing conversation and
provider-side history settings remain unchanged; saved remote conversations may
retain older facts, so fresh local snapshots do not promise deletion from Coze's
remote history. Coze provider-only answers do not write AI-Shifu memory. The
request-delivery contract is covered locally; answer quality still needs a
separately configured real bot. See the [official Coze chat contract](https://docs.coze.cn/developer_guides_chat_v3).

Volc native `/api/knowledge/collection/search_knowledge` receives valid nonempty
system/user/assistant text in `pre_processing.messages`, retaining exact content
and order, with the current query appended once after removing its existing
trailing copy. The existing host history and encoded-memory budgets still apply;
there is no adapter-side persistence. The final UTF-8 body, including context,
is serialized before signing.

For contextual native requests, an unspecified `rewrite` defaults to true so
that the provider can use the history for retrieval. An explicit rewrite value
other than boolean true opts out of automatic context delivery. Any explicitly
configured `messages` field owns the complete message payload, including empty
or malformed values, and keeps the existing blank-user normalization. Other
preprocessing options remain intact. Query-only requests with no earlier valid
context and bespoke non-native paths retain their previous request behavior.
There is no new settings field or implicit switch to an LLM provider.

The [official Volc search contract](https://docs.volcengine.com/docs/vector_database_vikingdb/search_knowledgeNew?lang=zh)
describes rewriting from up to three conversation turns and requires more than
two messages for an effective rewritten query. The adapter does not fabricate
history to satisfy that threshold. Retrieval delivery is covered; a real
configured knowledge base must separately establish rewrite/retrieval quality.
This adapter returns retrieved text, rather than generating a contextual answer.
Enabling native rewriting may add provider work; AI-Shifu billing classification
and existing provider transport limits are unchanged. Valid error responses raise
a fixed provider error even if they contain data; no-text response warnings report
only the payload type, so echoed private notes do not reach host logs.

### Coze Workflow explicit binding

Workflow start-node input names and types belong to the published workflow;
there is no universal native history parameter. Existing workflows remain
query-only unless advanced `config.context_key` names a declared **String** input.
This can be configured through the existing course API config serializer;
the minimal settings form does not add a new control in this increment. Alongside
the existing credentials and workflow ID, for example:

```json
{"context_key": "classroom_context", "query_key": "query"}
```

The workflow must declare `classroom_context` as a String and explicitly reference
it in the relevant node. Its value is a JSON string of the form
`{"messages":[{"role":"system","content":"..."},...]}`, containing the host's
scoped encoded memory and ordered valid system/user/assistant text. The current
query is appended after removing only its existing trailing copy. Text stays exact,
nontext/unsupported entries are omitted, and the host's existing history and
memory budgets remain. Treat stored facts and learner/history text as reference
data, without granting permission to modify memory or override workflow rules.

The original `query_key` still receives only the actual current question. Missing,
null or blank `context_key` disables automatic context. Nonstring names and names
colliding with the normalized query_key fail with fixed configuration errors before
network. The generated context owns its named parameter, overriding a static value
there just as the current question owns query_key; other static parameters stay
unchanged. Explicit `extra_body.parameters` continues to replace the complete
parameter payload and opts out of automatic delivery. Other extra-body options
do not disable the binding. Inputs/configuration are not mutated.

Business errors now raise a fixed provider exception without raw messages, codes,
details or log IDs that could echo newly forwarded notes. Existing safe outbound
limits, response formatting, routing, billing and host transactions remain.
Provider-only workflows do not write AI-Shifu memory. Tests prove configured
request delivery and scope/freshness; a separately configured real workflow must
establish that its nodes consume the string and produce a useful answer. See the
[official workflow run input contract](https://docs.coze.cn/developer_guides_workflow_run).
The builder supplying messages is not proof that an unbound workflow receives them.

## Memory writes in contextual LLM follow-ups

For 2.0 text follow-ups, an actual contextual LLM invocation may call `remember`.
The native-thread bridge runs a small Agent with that tool only. Ordinary no-tool
answers use their existing single model request; there is no extraction request
per question. The same LLM factory is available to retrieval synthesis and to a
configured LLM fallback. External provider-only answers and Live voice do not gain
memory writes through this increment.

Permission uses collection names from the request's retained main-script row,
bound to its course and lesson. A newer publication, fenced example, course brief,
knowledge document or historical conversation cannot grant a new declaration.
Undeclared values require the complete actual current learner input and the
existing independent semantic admission check. Deleted keys require a new current
explicit request. Registered system profiles retain their existing global scope;
all other durable notes remain course-local. Existing key/value, entry-count and
JSON scope limits apply through the shared engine remember tool.

Approved updates stay in producer memory until the response fully succeeds and is
consumed. The request host stages them with ask history in its existing final
transaction, after locking the original learning attempt and comparing deletion
generations and course-value row versions. A late proposal cannot overwrite a
newer correction. Registered global profiles compare both compatibility-row
versions and canonical account values, with the account locked before its global
rows. The canonical `sys_user_language` write alias uses account storage without
adding a duplicate settings UI label. Retired published rows keep their retained declarations across
republishing; newer publications cannot grant permission. Provider failures, disconnects, guardrail rejections and previews do
not persist proposals. Cancellation checks also run while a provider is quiet.
Tool events are not added to user SSE or visible classroom history. Model requests
retain learner/course/lesson/attempt and read/listen/classroom usage attribution.
Each answer permits at most five answer-generation model requests and three tool calls; undeclared
proposals may add at most three independent admission requests, each with a bounded
provider timeout. These limits exclude the existing optional author guardrail,
which runs before answer generation. No persistent engine session or new cross-course storage is added.

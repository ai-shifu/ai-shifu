---
title: Volc Knowledge Follow-up Context
status: active
owner_surface: learner
last_reviewed: 2026-10-09
---

# Volc Knowledge Follow-up Context

## Purpose / Big Picture

The shared follow-up builder already reads scoped course memory and selected
classroom history, but the Volc knowledge adapter discards these messages. Native
knowledge retrieval should receive that context for question rewriting while
preserving explicit teacher configuration and the existing signed transport.
The durable contract belongs in [Follow-up Classroom Context](../../references/follow-up-classroom-context.md).

## Progress

- [x] 2026-10-09 16:25 CST: Confirmed the dropped messages and checked the official native search protocol.
- [x] 2026-10-09 16:29 CST: Nine native outbound/privacy/storage cases fail on the old adapter and pass on the candidate. The first test run had a missing postponed-annotation import; the corrected tests were rerun against the original runtime before acceptance.
- [x] 2026-10-09 16:31 CST: Full learning regression passes 2,897 tests and four subtests, with one expected skip.
- [x] 2026-10-09 16:38 CST: Developer-tool and all-files gates pass; PR #3063 is open at 6aa42f898. Sim cfc519737 has the same tree, build 462 / Drone 5253 and deployments 2198-2199 succeed. Both replicas match 41 runtime hashes and pass 44 isolated outbound/privacy cases with no provider calls or database writes; a new demo learner completes start/answer HTTP with two correctly attributed nonbillable usage records.
- [x] 2026-10-09 16:38 CST: Replied to Devin's three-turn window concern in its original thread as deferred real-provider acceptance, without claiming the hosted rewriter was tested.
- [ ] 2026-10-09 16:38 CST: Finish final CI and remaining AI review audit, replying to every independent opinion.
- [ ] 2026-10-09 16:38 CST: Run a configured real knowledge base with more than three classroom turns; inspect rewrite_query and retrieved results for a current fact present in the leading course-memory context.

## Surprises & Discoveries

The [official native search API](https://docs.volcengine.com/docs/vector_database_vikingdb/search_knowledgeNew?lang=zh)
uses `pre_processing.messages` only for query rewriting, which defaults to false.
It documents system/user/assistant roles, up to three turns used for rewriting,
and a requirement for more than two messages for an effective rewritten query.
Sending context without enabling rewrite would not fix contextual retrieval.
This adapter returns retrieved text directly; it does not run answer synthesis.
Devin's [original review](https://github.com/ai-shifu/ai-shifu/pull/3063#discussion_r4228215491)
asks whether the leading memory survives a long-history rewrite window. The
[original-thread reply](https://github.com/ai-shifu/ai-shifu/pull/3063#discussion_r4228232245)
defers this to configured real-provider acceptance. Official examples allow a
leading system message, but the window's treatment of that message is unspecified;
outbound tests cannot establish hosted-service prioritization.

## Decision Log

- 2026-10-09: Limit automatic delivery to the native collection search path.
  On contextual requests, default rewrite to true only when unspecified. Preserve
  explicit rewrite values and custom message ownership; no new configuration UI.
- 2026-10-09: Preserve exact valid text and history order, append the current query
  once at the tail, and reuse the host's existing bounded history and encoded
  memory. Do not fabricate conversation turns to bypass the provider threshold.
- 2026-10-09: Sanitize error echoes and no-text response warnings before forwarding
  newly available private notes. Leave credentials, signatures, safe-client
  limits, provider routing, billing, persistence and memory write scope unchanged.

## Outcomes & Retrospective

Local request/storage/privacy acceptance and repository gates pass; PR #3063 is open and exact-runtime sim acceptance passes. Final CI and remaining AI audit are pending. Request delivery tests do not establish
real configured knowledge-base retrieval quality or answer quality. Workflow
parameter mapping remains a separate focused change; 1.0 rollback stays available.

## Context and Orientation

Runtime owner: `src/api/flaskr/service/learn/ask_provider_adapters/volc_knowledge_adapter.py`.
The shared builder is `learn/follow_up_context.py`; tests already cover actual
course-note storage, scope, updates and deletion. Signing must use the final body.
Existing explicit `pre_processing.messages` normalization is a compatibility
contract, including blank user content being replaced by the current query.

## Plan of Work

Add outbound red tests, implement native message delivery and private-error
boundaries, extend real-storage acceptance, then run the learning suite and gates.
Create one focused main PR and integrate its exact runtime into sim.

## Concrete Steps

1. Run focused tests before and after the adapter change using conda ai-shifu.
2. Run `tests/service/learn/`, developer-tool checks and all-files pre-commit gates.
3. Push to GitHub origin, create/attach the PR, then integrate into the existing sim branch.
4. Verify runtime hashes and isolated request cases on both sim replicas; use a
   new demo learner for normal classroom HTTP, without editing shared courses.
5. Read review bodies, inline comments and issue comments and reply to each independent opinion.

## Validation and Acceptance

Native outbound requests contain current scoped memory, selected history and one
final query, without mutation or cross-user/course leakage. Signing covers the
exact UTF-8 body including context. Explicit message overrides, rewrite opt-out,
non-native endpoints and query-only calls preserve prior behavior. Error echoes
must not reach exception text or warning logs. Fresh snapshots see note updates
and deletions without adapter writes. The provider may use at most three turns;
a context with fewer than its required messages does not guarantee rewriting.
Real knowledge-base quality requires separately configured acceptance, especially
whether a leading current fact influences rewrite_query and results after more
than three conversation turns. Do not mark that concern resolved from mock evidence.

## Idempotence and Recovery

No migrations, dependencies, secrets or runtime environment changes. Repeated
requests read fresh snapshots and do not persist new memory. Roll back through
the existing image flow if necessary. Sim shares production data: use only pure
isolated probes and newly created learners on internal/demo courses. Production
verification remains read-only after human merge.

## Interfaces and Dependencies

Keep the existing adapter signature and provider registry. Use the documented
`pre_processing` object and existing signing / safe outbound client; do not add
custom workflow fields or a second provider transport.

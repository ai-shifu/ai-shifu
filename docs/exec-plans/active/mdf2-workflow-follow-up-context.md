---
title: Coze Workflow Follow-up Context Binding
status: active
owner_surface: learner
last_reviewed: 2026-10-09
---

# Coze Workflow Follow-up Context Binding

## Purpose / Big Picture

Coze Workflow currently discards the shared follow-up messages. Unlike native
chat, workflow start-node inputs have author-defined names and types. Provide
an explicit optional binding that delivers the existing scoped context without
changing the current query or inventing undeclared inputs for existing workflows.
The durable contract belongs in [Follow-up Classroom Context](../../references/follow-up-classroom-context.md).

## Progress

- [x] 2026-10-09 16:42 CST: Read the adapter, configuration normalization and official workflow-run input contract.
- [x] 2026-10-09 16:47 CST: Fourteen outbound/configuration/privacy/actual-storage cases fail on the old runtime. Candidate focused tests pass; full learning regression passes 2,916 tests and four subtests with one expected skip.
- [x] 2026-10-09 16:55 CST: Initial local gates and all technical CI pass. Created #3064; initial same-tree sim 147f6257d build 464 / deployments 2208-2209, two API replicas each 42 hashes and 36 isolated cases pass. A new demo learner completes two HTTP turns with usage attributed to actual progress/block IDs.
- [x] 2026-10-09 17:03 CST: AI review exposed frontend saves dropping API-configured advanced bindings. Three regression cases fail before the fix; all 136 settings tests pass after it, including fail-open private analytics.
- [ ] 2026-10-09 17:03 CST: Push the settings-preservation fix after full gates and verify the final sim web/API image.
- [ ] 2026-10-09 16:42 CST: Audit AI feedback, reply in original discussions and record final CI.
- [ ] 2026-10-09 16:42 CST: Separately accept a configured real workflow that consumes the declared context string.

## Surprises & Discoveries

The [official workflow run API](https://docs.coze.cn/developer_guides_workflow_run)
requires `parameters` matching the workflow's start-node declarations. It does
not promise a universal messages parameter. Existing `query_key`, `parameters`
and `extra_body` are advanced configuration accepted by the existing backend
serializer; the settings form currently exposes only minimal credentials/IDs. Its submit helper
previously discarded undeclared fields even though the server explicitly permits
additional properties. An unrelated title save therefore erased the context binding;
backend-only roundtrip tests could not detect this frontend consumer bug.

## Decision Log

- 2026-10-09: Add advanced `config.context_key` as an optional string binding to
  an author-declared String input. Absent/blank means no automatic context. Keep
  query_key's exact current question and avoid silently changing existing flows.
- 2026-10-09: The bound value is a JSON string containing validated text messages
  and one final current query. Keep exact text, host ordering, encoded untrusted
  memory and existing scope/budgets. Do not grant memory writes to provider-only answers.
- 2026-10-09: Reject malformed binding types and query-key collisions with fixed
  configuration errors. Explicit `extra_body.parameters` retains complete ownership;
  other extra fields do not disable context. Generated binding owns its named
  parameter just as the current query owns query_key. Do not mutate configuration.
- 2026-10-09: Sanitize workflow business errors before adding private context;
  raw provider messages/details/log IDs must not escape to host warnings.

- 2026-10-09: Honor explicit schema `additionalProperties: true` in the settings
  submit helper, preserving only undeclared values before the normal declared-field
  validation. Absent/false permissions keep prior filtering. No new setting control
  or analytics schema; assert the existing save event stays private and fail-open.

## Outcomes & Retrospective

Initial local/runtime/sim acceptance passes; final frontend-fix gates, sim and CI
are being verified. Unconfigured workflows remain query-only by design.
This increment is usable through existing API
course configuration; it does not introduce a settings-form control. Real workflow
consumption/answer quality and the prior Volc hosted rewrite-window check remain
external acceptance. Preserve 1.0 rollback and human main merges.

## Context and Orientation

`learn/ask_provider_adapters/coze_workflow_adapter.py` owns the run request and
response formatting. `learn/follow_up_context.py` supplies scoped memory and
anchor history; existing profile storage tests cover isolation and deletion.
`shifu/shifu_draft_funcs.py` preserves arbitrary config entries during normalization
and serialization. Reuse these producer/consumer boundaries without a new transport.

## Plan of Work

Add outbound and configuration-roundtrip tests, then implement the optional binding
and sanitize new error-echo exposure. Extend actual storage/builder/outbound tests,
run learning regressions and gates, then create/attach a PR and verify the same
runtime on sim with isolated probes and a newly created demo learner.

## Concrete Steps

1. In conda ai-shifu, run focused tests against the old and candidate adapters.
2. Run the full learn suite, developer-tool checks and all-files pre-commit gates.
3. Push the feature branch to origin, create/attach the PR, integrate into sim
   with latest main and verify runtime hashes plus isolated outbound cases.
4. Smoke normal classroom HTTP on a new demo learner without shared-course edits.
5. Read reviews, inline comments and issue comments and reply to each opinion.

## Validation and Acceptance

A declared context_key receives current scoped memory, the selected host history
and one final query as valid JSON text while query_key retains the original query.
Default requests, blank binding, extra-body overrides and other parameters remain
compatible; malformed/colliding bindings fail before network. Serializer round trips and actual React title saves
preserve advanced configuration. An offline bridge uses the actual server schema,
TypeScript submit helper, backend serializer and workflow adapter to verify the
context binding survives to the intercepted outbound request. Settings tests also
cover tracking failure and exclude private configuration from event payloads. Real storage updates/deletion change fresh requests
without adapter writes or other course/user leakage. Provider errors cannot echo
notes through exception text. Mocked transport cannot prove a workflow consumes the
input or produces a good answer; run a separately configured real workflow for that.

The full frontend type-check reports two existing errors in the unrelated admin
operations user test (TS2683 and TS2790). Replacing all changed frontend files with
the main baseline produces exactly the same diagnostics; lint passes with existing
warnings and the settings suite passes 136 tests. No new type error is accepted.

## Idempotence and Recovery

No migration, dependency, environment change or frontend control. Repeated calls
construct fresh payloads without persistence. Roll back through existing image
publishing if needed. Sim shares production data: only pure isolated probes and new
demo/internal learners are allowed; production verification stays read-only.

## Interfaces and Dependencies

Keep the existing adapter signature, registry, response formatter and safe outbound
client. The optional advanced context_key maps to a documented workflow String
input. Do not invent chat messages at the top level of workflow/run.

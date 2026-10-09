# Deliver classroom context to Coze follow-ups

## Purpose / Big Picture

A Coze follow-up currently receives only the current query, although the shared
host has already prepared current-course memory and anchor-bound conversation.
Deliver that context through native chat without changing provider routing or
silently replacing custom endpoint/payload contracts. The durable contract lives
in [follow-up classroom context](../../references/follow-up-classroom-context.md).

## Progress

- [x] 2026-10-09T07:46:00Z: Confirmed the real adapter drops host memory/history;
  checked the official Coze chat API roles, final-user rule and 100-message limit.
- [x] 2026-10-09T07:48:00Z: Seven outbound regression cases fail against the existing
  adapter; implemented native role mapping and bounded recent history.
- [x] 2026-10-09T07:51:00Z: Added actual storage/builder/outbound coverage for scoped
  values, updates, deletion, history and no writes, plus malformed-echo log privacy.
- [x] 2026-10-09T07:56:00Z: Initial learning tests pass 2,865 cases, four subtests
  and one expected skip; developer-tool and full repository gates pass.
- [x] 2026-10-09T07:54:00Z: Published PR #3062. Initial sim build 457 and both
  deployments succeed; review identified an error-echo privacy issue.
- [x] 2026-10-09T08:00:00Z: Three privacy regressions fail before the review fix.
  Final learning tests pass 2,868 cases, four subtests and one skip; full gates pass.
- [ ] 2026-10-09T08:00:00Z: Verify final sim runtime/HTTP and reply to every
  independent AI opinion in its original discussion.
- [ ] 2026-10-09T07:51:00Z: Accept answer quality with a separately configured real
  Coze bot; mocked HTTP delivery must not be reported as real-bot acceptance.

## Surprises & Discoveries

Coze has no system message role. Forwarding the host list unchanged would produce
an invalid API request. Assistant history also needs `type=answer`, since the
provider defaults to question. A labelled user reference message carries course
context without claiming system authority. Existing arbitrary extra-body overrides
and custom endpoints can intentionally own a different request contract.
Devin review identified valid error-event echoes escaping through the host's
existing exception warning. Three new regressions reproduce it; sanitize the
adapter error text as well as malformed-response warnings. Reply in original
thread 4227925568 after pushing the fix and validation.
The first real-storage test used an invalid response double; it was corrected to
model the safe client's actual context-managed response rather than changing runtime.

## Decision Log

- Use native `additional_messages` for a resolved `/v3/chat` path, including
  absolute URLs and a trailing slash. Keep the existing outbound SSRF policy.
- Preserve exact strings, supported chat roles, historical duplicate questions and
  the final actual query. Omit blank, nontext and unsupported-role messages.
- Reserve current query and optional context inside the provider's 100-message
  budget. Keep newest remaining history, without mutating the source list.
- Preserve explicit additional-message overrides and bespoke endpoints; document
  their context opt-out rather than break existing custom integrations.
- Keep provider conversation/history configuration unchanged. Fresh outbound
  snapshots do not erase remote bot history. No local memory writes or fallback
  routing changes are included. Workflow and Volc remain separate work.
- Stop logging malformed provider contents now that replies may echo course notes.

## Outcomes & Retrospective

Nine regression cases fail against the previous adapter. Final local learning
acceptance passes 2,868 cases and four subtests, with one expected skip. Full
repository gates pass. Sim, review closure and external answer quality remain
tracked separately above.

## Context and Orientation

`follow_up_context.py` owns scoped memory and anchor history. `handle_input_ask.py`
appends the current formatted query and routes provider messages to the adapter.
Only `ask_provider_adapters/coze_adapter.py` changes runtime behavior. Existing
safe-client, SSE chunks, request context, credentials and host transaction remain.

## Plan of Work

Prove the request loss, map to the documented native protocol, test provider
limits and compatibility, then run learning regressions and deploy the same tree
to sim. Preserve human control of main merges and record external acceptance limits.

## Concrete Steps

1. Run adapter, course-memory and learning tests from `src/api` in the shared conda environment.
2. Run developer-tool checks and `lefthook run pre-commit --all-files` at repository root.
3. Push the feature branch to origin and create a main PR. Integrate into sim using
   the existing local sim branch, preserving unrelated sim changes.
4. Check exact runtime hashes on both sim API replicas, execute isolated outbound
   probes without provider calls/database writes, and smoke normal HTTP with a new learner.
5. Read reviews, inline comments and issue comments; reply to each independent opinion.

## Validation and Acceptance

Actual outbound JSON must contain scoped current memory, selected context, prior
questions/answers and exactly one trailing current query. Real storage updates
and deletion affect fresh requests, while other courses/users never appear.
Overlong history stays within 100 messages, native roles/types remain valid,
custom contracts remain compatible, and malformed echoes never enter warning logs.
Existing timeouts, HTTP/SSRF errors and streaming behavior must remain green.
A mocked transport proves delivery, not model answer quality or remote deletion.

## Idempotence and Recovery

No migration, dependency or environment change. Repeated requests build fresh
local snapshots without adapter persistence. Roll back the image/commit through
the existing deployment flow if necessary; retain 1.0 rollback code. Sim shares
production data: only isolated offline probes and newly created demo learners
are allowed for validation, with no existing-user resets or shared-course edits.

## Interfaces and Dependencies

The existing adapter signature and runtime DTO are unchanged. Use Python's JSON
and URL parsing plus the existing safe outbound client. The documented Coze v3
chat API is the only new delivery contract; custom overrides remain explicit.

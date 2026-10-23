---
title: Profile onboarding startup
status: implemented
owner_surface: frontend
last_reviewed: 2026-10-23
canonical: true
---

# Profile onboarding startup

## Questionnaire execution

Profile onboarding and operator questionnaire previews use the shared
MarkdownFlow 2.0 agent engine through the public `learn.agent.api` boundary.
The course-only `FLOW_ENGINE_V2_ENABLED` flag does not select the profile
runtime: both profile entrypoints always use 2.0.

The entire frozen questionnaire is the script of one native engine Session.
The engine owns script progression, deferred interactions, accepted answers,
typed message history and completion. The Profile host never executes individual
authored blocks or advances an authored cursor. Published 1.0 notation remains
supported by the engine and the publication validator; source parsing is not
runtime orchestration.

One engine turn may raise several interactions. The Session preserves all of
those pending tool calls and the host displays only the first. Native answer
handling collects each deferred result and resumes the model when all calls
have answers. Named questions read only the matching submitted variable field;
unnamed questions combine the submitted values. Choice-plus-text controls retain
both selected values and free text. Invalid answers leave their native question
pending. Cached controls must remain renderable before redisplay or submission.
Responses rejected by native tool validation contribute no public text or
accepted learner evidence. Public content is adapted through the existing
pager, element SSE shape and frontend renderer.

The private learner profile is a separate transformation of native accepted
interaction answers, including unnamed answers, plus validated supplemental
assistant evidence. Instructions, questions, model-generated memory notes,
confirm clicks and the separately collected nickname are not personal profile
evidence. Both manual completion and assistant import use the same private
transformation function, existing profile prompts and nonbillable provider.
The private summary is never appended to the public questionnaire script and
never enters a `content` event. A `phase` event with `{phase: "summary"}` lets
clients show the existing summary state. The result appears only as
`profile_draft` in the terminal `done` event.

The session API exposes `turn_index`, a host request revision, and submissions
use `expected_turn_index` with `request_id`. This revision prevents stale writes
and supports exact retries; it neither indexes script blocks nor equals native
Engine.turn (answering one of several pending calls may not invoke the model).
Terminal events include `next_turn_index`, `input_accepted` and the native
`pending_interaction_ids`. Clients continue only when the native turn has no
pending interaction and has not finished. They never count authored blocks.
An interaction event carries its native `interaction_id`; an answer must submit
that value as `expected_interaction_id`. Exact retries preserve the complete
request identity, including this question token. Only an accepted answer marks
its corresponding frontend control as answered. Content and question display
identities are separate, and a retry replaces uncommitted controls.

Owner locks, exact-request replay, thirty-minute expiration, frozen
configuration, nonbillable metering and existing product analytics remain in
the Profile host. Schema 3 stores the full native Session. Schema 1 and 2 cached
per-block sessions expire as incompatible: callers receive the existing
session-not-found response and can start a fresh questionnaire. Roll out the API
workers and web clients together; old block-based clients cannot call the new
turn-revision API. Rollback requires expiring schema-3 active sessions or waiting
for their thirty-minute lifetime before restoring the old runtime.

## Course entry

Profile collection starts after account initialization and any WeChat OpenID
preparation that could navigate away from the course. Both automatic onboarding
and the personalization menu wait for preparation. The existing guided flow,
save, skip, and learner-profile API remain unchanged.

The parent course layout owns authorization readiness and navigation for the
whole route. Its missing-code OAuth and the page's OpenID recovery share this
state. Readiness is closed before child effects run, including when an account
already has an OpenID. A retained store code does not replace a missing URL
code; an incoming URL code must first hydrate the store before binding begins.
Runtime configuration must also finish loading before Profile can start.

Inside WeChat, outside mini programs, with the WeChat code flow enabled:

- Wait for the authenticated account profile before deciding whether an OpenID
  needs recovery. Exchange a fresh OAuth code once, including for a bound account
  whose current WeChat account may have changed.
- Finish any required account refresh before allowing Profile. Refresh failure
  after successful exchange does not start another OAuth redirect.
- An unbound account with no usable code may recover through one browser-session
  OAuth redirect. Profile stays closed while that navigation starts.
- Missing recovery configuration, inaccessible session storage, or an exhausted
  recovery marker allows startup to continue without another redirect.
- Account-profile waiting, code exchange, and account refresh share a ten-second
  preparation deadline. After the deadline, late results cannot start OAuth or
  refresh an account on behalf of the retired attempt.
- Once either path issues OAuth navigation, Profile remains closed until the
  document is replaced. A timer, menu click, or child-page remount cannot cancel
  navigation or release this gate. A synchronous navigation exception can
  safely release startup because navigation did not begin.
  When the layout's missing-code navigation throws, clear any retained store
  code and wait for that cleared value before releasing binding preparation.
- A persisted `pageshow` after an issued navigation proves the browser restored
  this document from its back-forward cache. Retire that navigation and abandon
  automatic authorization preparation for the restored layout: do not redirect
  again or exchange its old code. Learning and Profile with a known account may
  resume; a fresh document follows normal authorization preparation.
- If the account profile is still unavailable at the deadline, learning may
  continue. Profile itself waits for a known account identity, avoiding a
  collection that would be replaced when that identity arrives.

Other browsers, mini programs, and disabled WeChat code flows keep their existing
behavior. Teacher preview runtime keeps its immediate readiness bypass because
preview does not automatically collect Profile. Old account, token, or code work
cannot affect a new identity. React
effect replay reuses a pending exchange rather than spending a single-use code
again.

## Existing Profile analytics timing

This extends the timing contract under
[frontend product analytics](../references/frontend-product-analytics.md).

- Business question: how often do eligible learners start Profile collection,
  then complete, defer, or encounter a collection failure?
- Metric: existing aggregate starts and failures per release or reporting window;
  these best-effort event totals do not form an exact joined funnel.
- Events: `profile_onboarding_shown` and `profile_onboarding_runtime_failed` keep
  their existing names and payloads. `shown` means collection started, not that
  every personalization dialog opened.
- Triggers: the dialog controller's `beginCollection` owns `shown`; a real
  collection error owns `runtime_failed`. Parent OAuth waiting, OpenID waiting, recovery navigation,
  and abandonment of binding emit neither event.
- Population and count unit: existing eligible collection journeys, with the
  current guest, preview, settings, and per-journey producer guards preserved.
  Preparation does not create an extra journey or event.
- Consumers: existing Profile start/failure reports and operational queries.
  Release comparisons should account for removal of starts interrupted by
  recovery navigation. No dual writing, renaming, or backfill is needed.
- Privacy and correlation: no new fields or identifiers; never collect OpenIDs,
  OAuth codes, credentials, account information, or URLs.

| Event | Existing fields | Allowed values |
| --- | --- | --- |
| `profile_onboarding_shown` | `source`, `presentation`, `has_profile` | `guided` or `settings`; `blocking` or `hidden`; boolean |
| `profile_onboarding_runtime_failed` | `stage`, `presentation` | `guided`; `blocking` or `hidden` |

Route regressions prove that preparation precedes eligibility and collection
entry. Existing dialog/controller regressions prove the actual event triggers,
allowlisted payloads, and analytics failure isolation. Binding failure or a
deadline must never require successful analytics delivery to release startup.

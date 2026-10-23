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

Published MarkdownFlow questionnaires keep their existing authored block
boundaries and validation rules. The parser supplies authoring metadata and
progress; it does not execute model calls. Each authored block has its own
agent session. Content blocks output text and visuals. Only static
`BlockType.INTERACTION` blocks expose formal controls, with exactly one question
per block. Instructions to introduce or ask a question in preceding content
produce its narrative; the static interaction block supplies its controls.
After accepting the answer, the block completes without asking another
question. Invalid answers keep the current question available. Deferred tool
state, accepted answers and typed conversation history survive Redis round trips.
Before redispatching a saved question or accepting its answer, the runtime
checks that it is the single renderable interaction for the current authored
block. An incompatible saved question fails the request without accepting its
input or changing stored progress and evidence.
Answers to named questions use only the submitted field matching that variable;
a missing matching field keeps the question available. Questions without a
variable continue to combine values from the submitted fields.
Prior questions, instructions and model responses are context rather than
learner facts. Named values and accepted raw answers supply evidence for the
final profile, including answers to questions without a named variable.

The same engine executes the frozen final profile step for manual collection
and imported assistant answers. Its text is returned only in the terminal
`profile_draft` field. Existing SSE event names, cumulative element content,
request replay, thirty-minute expiration, ownership locks, nonbillable usage
and Profile analytics contracts are preserved. Existing version-1 cache records
remain readable; the first resumed answer reconstructs its deferred question
without asking the learner to resubmit it.

Interaction events also carry `interaction_id`. Learner and operator clients
bind that identifier to the displayed question and submit it as
`expected_interaction_id`; exact retries retain the same question identifier
and request ID. Stale submissions must match the current authored question;
reusing a request ID with another question identifier is rejected. Older clients
can answer their original question without the new field. Content, authored
questions and answer feedback have separate stable element IDs so one item
cannot overwrite another in the transcript. A question's display ID belongs
to its authored block; retrying an interrupted render replaces those controls
with the new native question token rather than leaving an obsolete input active.

Roll out the runtime as one worker revision. Older workers cannot read the
new engine-state cache schema. A rollback must expire active profile sessions
or wait for their thirty-minute lifetime to end before restoring older workers.

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

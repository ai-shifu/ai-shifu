---
title: Profile onboarding startup
status: implemented
owner_surface: frontend
last_reviewed: 2026-10-13
canonical: true
---

# Profile onboarding startup

## Course entry

Profile collection starts after account initialization and any WeChat OpenID
preparation that could navigate away from the course. Both automatic onboarding
and the personalization menu wait for preparation. The existing guided flow,
save, skip, and learner-profile API remain unchanged.

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
- Account-profile waiting, code exchange, account refresh, and navigation share
  a ten-second preparation deadline. After the deadline, late results cannot
  start OAuth or refresh an account on behalf of the retired attempt.
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
  collection error owns `runtime_failed`. OpenID waiting, recovery navigation,
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

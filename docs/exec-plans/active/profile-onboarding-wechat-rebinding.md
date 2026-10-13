# Keep WeChat OpenID preparation ahead of Profile onboarding

## Purpose / Big Picture

After SMS sign-in inside WeChat, the course page can start Profile collection
while its OpenID recovery effect starts a full-page OAuth redirect. The redirect
closes the collection stream, and the returning page can race the previous
session's lock. Finish or safely abandon OpenID preparation before opening
Profile, including its menu entry, so collection starts on a stable page.

## Progress

- [x] 2026-10-13 CST: Correlated two live failures with SMS sign-in, OpenID
      exchange, page reload, duplicate collection sessions, and a client disconnect.
- [x] 2026-10-13 CST: Inspected the current main, course gate, rebinding effect,
      and adjacent tests; selected bounded preparation before collection.
- [x] 2026-10-13 CST: Implement preparation and preserve existing binding behavior.
- [x] 2026-10-13 CST: Verified ordering, failure isolation, identity changes,
      and StrictMode with 201 focused tests, type checking, lint, architecture,
      and the full Lefthook repository gate.
- [ ] 2026-10-13 CST: Publish a ready pull request and verify its checks.

## Surprises & Discoveries

The first live failure explicitly logged a client disconnect. The other started
a replacement session while the old generation was still running. Sensitive
response omission prevents reading its exact business error, so lock contention
is a supported explanation rather than a directly captured error code.

The existing OpenID request and account refresh have no general request timeout.
A new startup dependency must have a deadline and suppress late navigation.
Refreshing a successfully bound account must not trigger another OAuth recovery
when only the refresh fails.

Independent review found that account-info failure can retain an authenticated
token with no user profile. Include that wait in the same deadline, and preserve
its terminal state when the profile later arrives for the same token.
Keep Profile itself closed until the account identity is available: on this
exceptional timeout only learning is released, so a later account response
cannot replace a collection started under an unknown identity.

## Decision Log

- Prepare OpenID before Profile instead of redirecting after collection; keep
  existing binding of fresh codes, including an account already bound elsewhere.
- Keep preparation local to the course route. Reuse the shared API, OAuth helper,
  user store, Profile gate, and current events.
- Share a pending code exchange across StrictMode effect replay. Scope it to
  user, token, and code, never to the mutable OpenID returned by refresh.
- Release preparation after ten seconds or when recovery cannot proceed. Once
  released, late callbacks cannot navigate or change the active account's gate.

## Outcomes & Retrospective

Implementation passes 201 focused tests, type checking, and frontend lint.
Independent review added account-info failure and late-identity regressions.
The full repository gate also passes. Publication verification is in progress.
No backend schema, provider, Profile prompt, or production configuration change
is required.

## Context and Orientation

The course entry is `src/web/src/app/c/[[...id]]/page.tsx`.
`hooks/useCourseProfileOnboardingGate.ts` owns eligibility and runtime release.
The existing OAuth helper is in `src/web/src/constants/uiConstants.ts`.
Profile collection and its events belong to the shared dialog controller.

## Plan of Work

Extract the existing OpenID orchestration into a route hook that exposes startup
readiness. Gate both automatic Profile eligibility and the menu entry until
preparation settles; never start a collection that the same preparation can
later interrupt. Preserve non-WeChat and mini-program behavior. Add hook and
route integration regressions before publishing.

## Concrete Steps

1. Add a bounded, identity-scoped OpenID preparation hook.
2. Connect its readiness to the course Profile gate and remove the parallel effect.
3. Cover pending exchange, OAuth fallback, refresh failure, unavailable storage,
   timeout, late responses, identity changes, and StrictMode.
4. Run focused Jest, type checking, lint, harness, and full Lefthook checks.

## Validation and Acceptance

Before OpenID preparation settles, no Profile eligibility request or collection
starts, the menu cannot open it, and learning runtime stays paused. Successful
exchange and account refresh release the gate. Failed or empty exchange can
redirect once; exhausted or unavailable recovery releases the gate. A timeout
releases it and prevents late OAuth. Old account/code/token work cannot navigate,
refresh, or release the current account. Binding success followed by refresh
failure releases without another OAuth. Existing completion and skip behavior
remains unchanged.

## Idempotence and Recovery

Keep the existing browser-session recovery marker. Unmounting detaches callback
subscriptions without replaying a single-use code exchange. Account or token
changes invalidate old work. Rolling back this frontend change needs no migration.

## Interfaces and Dependencies

Add a route-local OpenID readiness hook and a startup readiness input to the
existing Profile gate. No public API, package, or event payload changes.

### Existing Profile analytics timing contract

The durable startup behavior, existing event timing, payload schema, and
consumer compatibility contract live in
[Profile onboarding startup](../../product-specs/profile-onboarding-startup.md).
No new event or field is added; preparation is excluded from collection starts
and failures.

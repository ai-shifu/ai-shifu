# Gate Profile on every course WeChat authorization

## Purpose / Big Picture

PR #3126 serialized page-local OpenID recovery with Profile collection, but
the parent course layout still starts OAuth whenever the URL has no code.
An already initialized learner can therefore start Profile while that separate
navigation is pending. Share authorization readiness and navigation ownership
between the layout and page, and verify the complete parent-child route.

The authorized delivery ends at a new reviewable PR. Do not merge into main
or publish any environment as part of this work.

## Progress

- [x] 2026-10-13 CST: Confirmed the missing parent-layout gate and inspected
      account initialization, code hydration, and existing Profile tests.
- [x] 2026-10-13 CST: Created a fresh task branch from the fetched main.
- [x] 2026-10-13 CST: Shared course OAuth navigation and synchronous readiness.
- [x] 2026-10-13 CST: Verified 17 real layout-page-Profile regressions and 20
      authorization unit cases; all 262 focused tests pass.
- [x] 2026-10-13 CST: TypeScript, frontend lint, harness and architecture
      checks passed. Independent implementation review found no blockers.
- [x] 2026-10-13 CST: Passed the full Lefthook repository gate and prepared
      a separate review-only PR handoff.
- [x] Human acceptance of the new PR; merge and deployment are not authorized. Closed at archival on 2026-10-29: #3127 is merged into main and deployed with it, so this review, merge or rollout step no longer applies.
- [x] 2026-10-13 CST: Addressed PR #3127 review about restored BFCache navigation
      with six unit cases and three integration cases that first failed.
- [x] 2026-10-13 CST: Verified the separate stale-code synchronous-failure review
      fix; its integration regression fails before the change and passes after it.

## Surprises & Discoveries

The existing checkWxcode flag only delays initUser; it never blocks rendering
an already initialized child's Profile flow. URL code and the global store code
are also distinct: a retained store code cannot settle missing URL authorization.

The previous OpenID deadline releases even an issued navigation. A location
assignment cannot be cancelled by this timer, so pending navigation must stay
closed until document replacement. Its ownership must survive a child remount.

The new core integration regression fails against a static c68a64f snapshot:
one OAuth navigation coincides with one Profile display, session and stream.
The same regression passes after the change with all three Profile counts zero.

PR #3127 review found a browser Back edge case: BFCache restoration preserves
the layout and its navigation lock. A persisted pageshow is evidence that the
document returned, so retire navigation and abandon automatic preparation for
that restored layout. This must also skip binding to avoid reusing a spent code
or immediately redirecting an unbound account again.

A second review identified retained store-code exchange after a missing-code
navigation throws. The new integration regression reproduced that exchange.
Clear the stale code in the failure path and wait for its cleared render before
releasing readiness; leave actual incoming URL code handling unchanged.

## Decision Log

- 2026-10-13 CST: Keep course authorization state in the parent layout and
  expose a route-local context to the page. Both layout and recovery redirects
  use one stable authorization callback and one pending-navigation lock.
- 2026-10-13 CST: Compute readiness before effects. Wait for runtime config
  and for an incoming URL code to hydrate the store; ignore stale store code.
- 2026-10-13 CST: Retain bounded account/exchange/refresh preparation, but do
  not release an already issued navigation on deadline. A synchronous navigation
  exception is a safe terminal failure and may release startup.
- 2026-10-13 CST: Extend the existing Profile analytics timing contract with
  parent OAuth waiting. Event names, payloads, eligible population, deduplication,
  and consumers remain unchanged; waiting creates no Profile journey or event.
- 2026-10-13 CST: Use only persisted pageshow to retire a navigation on browser
  restoration. Ordinary pageshow, focus, deadlines and child remounts do not prove
  navigation completed. Restored layouts skip automatic binding/retry until a
  fresh document starts. See the
  [browser lifecycle definition](https://html.spec.whatwg.org/multipage/nav-history-apis.html#the-pagetransitionevent-interface).

## Outcomes & Retrospective

Implementation, local verification and the full repository gate are complete.
The plan remains active for human review rather than
assuming permission to merge or deploy. The canonical behavior and analytics
contract belongs in
[Profile onboarding startup](../../product-specs/profile-onboarding-startup.md).

## Context and Orientation

The optional catch-all course route lives in src/web/src/app/c/[[...id]].
Its layout owns initial OAuth and user initialization; its page owns OpenID
recovery and the Profile gate. UserProvider also hydrates incoming codes but
does not block children. Existing page tests omit the parent layout.

## Plan of Work

Extract parent OAuth state into a route-local hook/context, route page fallback
navigation through it, and combine its readiness with OpenID readiness. Keep
preview runtime bypass, missing configuration, other browsers, and mini programs
compatible. Add integrated regressions with real route and Profile controllers,
mocking only external navigation/network and unrelated lesson presentation.

## Concrete Steps

1. Add the authorization context/controller and wire layout and page.
2. Preserve pending navigation beyond preparation deadlines and child remounts.
3. Prove the review case is red before the change and green afterward.
4. Run focused Jest, TypeScript, lint, architecture and repository gates.
5. Commit, push the task branch, open and attach a ready PR; stop before merge.

## Validation and Acceptance

In WeChat, with an initialized bound account and no URL code, OAuth starts
once while Profile display, session creation, and streaming remain zero, even
past ten seconds or on menu clicks. Stale store codes do not exchange. A fresh
document returning with a code waits for hydration, exchange and account refresh
before collection. A recovery redirect survives child remounts without opening
Profile. StrictMode does not duplicate navigation; excluded browsers and preview
retain their contracts. Tracking failure never affects authorization readiness.

## Idempotence and Recovery

Navigation deduplication belongs to the parent layout lifetime. Repeated effects
reuse that decision, and child remounts cannot reset it. Account/exchange timeouts
retire late results. Do not modify production, merge, or automatically revert
anything. Keep any follow-up review fixes as independent commits.

## Interfaces and Dependencies

The route-local context exposes ready, preparationAbandoned and authorize. The binding hook gains an
optional authorize callback, preserving standalone consumers. Existing user,
OpenID, Profile, tracking, and transport APIs remain unchanged. No dependency,
schema, locale, or infrastructure change is needed.

# Post-Auth Trial Bootstrap

## Summary

This change introduces a dedicated post-auth extension point for backend login
and creator-upgrade flows. The goal is to stop wiring new creator trial credit
bootstrap directly inside `route/user.py`, while still reusing the existing
plugin registration mechanism.

## Decisions

- `user` owns a stable `run_post_auth_extensions(app, context)` orchestration
  helper for post-auth follow-up work.
- `billing` registers its default new-creator trial bootstrap through the
  existing plugin extension registry instead of being called directly by user
  routes.
- Post-auth handlers are best-effort only. Login success must not be blocked by
  billing-side failures.
- `billing overview` becomes read-only for trial offers. It reports eligibility
  and existing grants, but no longer mutates wallet state.

## Status Rules

- Existing grant ledger: `granted`
- Trial config disabled: `disabled`
- User is not a creator: `ineligible`
- Config enabled, creator, no grant yet: `eligible`

## Non-Goals

- No general-purpose domain event bus
- No async queue or durable event persistence for post-auth work
- No historical backfill job for existing eligible creators

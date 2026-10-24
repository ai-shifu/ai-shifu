# Separate course permission contact validation

## Purpose / Big Picture

The course permission dialog mixes contact parsing and business validation with
React state and translated messages. Extract pure rules so they are easy to
understand and verify independently of dialog rendering.

## Progress

- [x] 2026-09-20 01:15 UTC: Audited parsing, validation order, and UI handoff.
- [x] 2026-09-20 01:15 UTC: Extracted typed validation and sample-format helpers;
  added 22 regression tests covering the current contracts.
- [x] 2026-09-20 01:18 UTC: Independent branch validation passed: 38 focused tests,
  TypeScript, lint, architecture, repository harness, and all-file hooks.

## Surprises & Discoveries

Phone parsing extracts eleven-digit segments from surrounding text. The first
string-valued owner phone alias wins even when it is empty. These existing
behaviors are retained rather than mixed with a parsing-policy change.

## Decision Log

- Keep error order: invalid input, missing contacts, owner contact, duplicate,
  then capacity. Keep the ten-person limit and five-contact error samples.
- Keep translated messages, authorization guards, requests, confirmation state,
  and permission level in the dialog. This is a behavior-preserving refactor.
- Use a local module and discriminated result instead of a new shared framework.

## Outcomes & Retrospective

Contact rules now have a typed, React-independent boundary and 22 direct
regression tests. Those tests and 16 existing admin-page tests pass on the
standalone branch, along with TypeScript, lint, architecture, repository
harness, and all-file hooks using locked dependencies and Node 22.16.0.

## Context and Orientation

`src/web/src/components/shifu-setting/ShifuPermissionDialog.tsx` owns the UI.
The adjacent `permission-contacts.ts` owns parsing, validation and sample
formatting; `permission-contacts.test.ts` describes compatibility behavior.

## Plan of Work

Extract existing pure rules, return explicit validation outcomes, and let the
component select the same translations or open its existing confirmation.

## Concrete Steps

Run contact helper and admin-page consumer tests, TypeScript, lint, architecture
and repository checks, and all-file pre-commit hooks.

## Validation and Acceptance

Test both contact modes, punctuation, case folding, deduplication, malformed
input, owner aliases, existing grants, capacity, error priority, and sample
truncation. Valid inputs produce the same pending contact list and permission.

## Idempotence and Recovery

No persisted data, API, dependency, or analytics change. Revert the standalone
PR to inline the same rules back into the component.

## Interfaces and Dependencies

The pure helper accepts input text, contact mode, existing identifiers, and the
same owner object previously read by the callback. UI and request APIs stay
unchanged; the helper has no React or store dependency.

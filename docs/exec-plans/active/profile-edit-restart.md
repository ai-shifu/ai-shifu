---
title: Restart Profile collection after rejected edits
status: active
owner_surface: frontend
last_reviewed: 2026-11-07
---

# Restart Profile collection after rejected edits

## Purpose / Big Picture

Avoid trapping learners after a failed Profile answer edit. A validation error
on an edit shows a localized toast and starts a fresh collection session. A
fresh session must accept its own draft even after an earlier session finished.
Existing transport, busy, model, summary and uncertain-write retries remain
unchanged, as do explicit review and save.

## Progress

- [x] 2026-11-07 13:16 CST: Verify PR #3357, its head and the approved scope.
- [x] 2026-11-07 13:21 CST: Reset completed collection state for a new session;
  full-dialog recovery, late-result and duplicate-result regressions pass.
- [ ] 2026-11-07 13:16 CST: Restart rejected edits with toast and analytics.
- [ ] 2026-11-07 13:16 CST: Verify regressions and update the PR and review.

## Surprises & Discoveries

The conversation hook already rebuilds expired sessions, but the dialog's
completion guard is not reset when that happens after a completed draft. The
edit validation error also uses the ordinary fatal-error handler. A new session
can reuse the existing creation path; no backend readback endpoint is needed.

## Decision Log

Restart only when an active rewind receives `transient_markdownflow_invalid`.
Retire the old stream, queued operations and uncommitted collection state. Keep
ordinary invalid input and assistant-import handling unchanged. Preserve exact
request retry when the operation outcome is uncertain. Never change the saved
account Profile until the learner explicitly reviews and saves a new result.

## Outcomes & Retrospective

Implementation and verification are in progress.

## Context and Orientation

`use-profile-onboarding-session.ts` owns request identity and session creation.
`ProfileOnboardingConversation.tsx` owns the shared learner/preview presentation
and localized notification. `use-learner-profile-dialog-controller.ts` owns the
accepted draft and completion guard. Learning-mode code is outside this change.

## Plan of Work

First fix fresh-session completion independently. Then connect the existing
session creation path to edit validation failure, notify once and retire old
callbacks. Update localization, the product specification and analytics.

## Concrete Steps

1. Reset completion and obsolete draft state when a different session starts.
2. Add full-dialog coverage for a completed, expired and restarted collection.
3. Restart invalid edits and show the translated notification in shared UI.
4. Cover active-attempt deduplication, late callbacks and unchanged retries.
5. Publish independent commits to the existing PR and resolve verified review.

## Validation and Acceptance

The new session begins without the previous answer or rewind flag and can
produce a reviewable, saveable draft. Old callbacks cannot restore old content.
An edit validation failure restarts once even when notification or tracking
throws. Disabled conversations delay the next run as before. Network, busy,
generic runtime, import and ordinary validation behavior retains its contract.

## Idempotence and Recovery

The attempt token invalidates callbacks from the retired session. Session IDs
scope draft acceptance. Same-session duplicate completion remains deduplicated.
If creation itself fails, reuse existing creation retry without an automatic
restart loop. Retired server sessions expire through their existing TTL.

## Interfaces and Dependencies

Use the existing toast, translations and shared tracking paths. Add an optional
`onRewindRestart` notification callback to the shared conversation and hook.

### Edit restart analytics contract

- Decision: determine whether edit validation failures often force learners to
  restart collection and merit further compatibility investigation.
- Metric: daily raw `learner_profile_answer_edit_restarted` counts divided by
  existing `learner_profile_answer_edit` attempt counts, grouped by source and
  presentation. This is an aggregate ratio, not a matched-request funnel.
- Trigger: once when an active edit validation failure initiates fresh-session
  creation, after reporting the existing edit's failed terminal outcome.
- Population: learner onboarding/settings collection; operator preview,
  ordinary answers, imports, network/busy errors and explicit retries excluded.
- Count unit and deduplication: one automatic restart per active edit attempt;
  advancing the attempt token rejects duplicate and late stream callbacks.
- Schema: exactly `source=guided|settings` and
  `presentation=blocking|hidden`; no content, question/session IDs or errors.
- Consumer: Profile product owner reviewing Umami daily counts alongside the
  existing answer-edit reliability metric; no repository dashboard/query exists.
- Compatibility: additive event. Existing attempt/terminal events and their
  outcomes keep their meanings, with no rename, dual write or backfill.
- Failure isolation: toast and analytics failures cannot prevent fresh-session
  creation. Tests assert exact payload, privacy, exclusions and deduplication.

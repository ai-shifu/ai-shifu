---
title: Learner follow-up input shortcuts
status: implemented
owner_surface: learner-web
last_reviewed: 2026-09-04
canonical: true
---

# Learner follow-up input shortcuts

Desktop learners submit a follow-up with Enter and add a line with
Shift+Enter. Mobile learners keep Enter for a line break and use the visible
send button. IME composition never submits a follow-up.

## Product analytics contract

### Learner follow-up submission

- Business question: which supported learner surface and submission method
  learners use to start a valid follow-up request.
- Metric definition: count accepted submissions by `surface` and
  `submission_method` over a reporting window. This is an accepted-use metric,
  not a request-success metric.
- Event name: `learner_follow_up_submit`.
- Actor and surface: learners and eligible course owners in learner preview;
  guests are included when the follow-up input is available. Empty inputs,
  credit-ineligible users, and submissions rejected because a follow-up is
  already streaming are excluded.
- Trigger: immediately after local eligibility and non-empty validation accept
  a submission, before starting the follow-up request.
- Count unit and deduplication: one accepted deliberate submission; no
  cross-session deduplication. The streaming guard prevents concurrent
  re-entry from adding events.
- Consumers: product analytics uses the grouped counts to compare keyboard
  adoption on desktop with the mobile send-button path.
- Compatibility: new event family; no backfill.
- Verification: focused component tests assert keyboard and button payloads,
  prohibit question/course fields, and prove tracking failure does not block
  the request.

| Field               | Type   | Allowed values                      | Cardinality | Privacy class     | Why required                        |
| ------------------- | ------ | ----------------------------------- | ----------- | ----------------- | ----------------------------------- |
| `surface`           | string | `learner_desktop`, `learner_mobile` | low         | non-personal enum | Compare supported learner surfaces. |
| `submission_method` | string | `keyboard`, `button`                | low         | non-personal enum | Measure shortcut adoption.          |

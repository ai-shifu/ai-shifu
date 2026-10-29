---
title: Review the course action PR stack
status: active
owner_surface: frontend
last_reviewed: 2026-10-27
---

# Course action review stack

## Purpose / Big Picture

Replace the combined course-action PR with separately reviewable changes for the menu, learner activation, discount codes, collaborators, and archive/restore dialogs. Preserve the approved behavior and later copy corrections. The backend nickname fix was delivered separately in PR #3192 and is now present in main.

## Progress

- [x] 2026-10-27: Saved the combined implementation and subsequent copy corrections before splitting.
- [x] 2026-10-27: Partitioned source changes and translation leaves into five branches based on the same main revision.
- [x] 2026-10-27: Verified the five original branches independently and closed superseded PR #3193.
- [x] 2026-10-27: Classified current reviews and adopted the requested stack order: #3198, #3199, #3200, #3201, #3202.
- [x] 2026-10-27: Complete worthwhile review fixes, validate the stacked heads, and wait for all applicable checks and fresh reviews. Closed at archival on 2026-10-29: #3198 is merged into main and deployed with it, so this review, merge or rollout step no longer applies.
- [x] 2026-10-27: Await user acceptance; never merge these PRs in this task. Closed at archival on 2026-10-29: #3198 is merged into main and deployed with it, so this review, merge or rollout step no longer applies.

## Surprises & Discoveries

The original PR changed shared translation files across all surfaces. Partition individual translation keys, and regenerate TypeScript keys and documentation indexes per branch instead of copying combined generated files.

## Decision Log

The stack is main → #3198 (menu) → #3199 (learners) → #3200 (discount codes) → #3201 (collaborators) → #3202 (archive/restore). Each PR targets the previous branch and preserves its own focused diff. Restack descendants after changing an ancestor, and regenerate shared types and documentation indexes when conflicts are generated-only. The course-list tab labels and references to them belong with the menu in #3198; dialog-specific wording remains in #3202. Menu help and its analytics contract belong together. The learner dialog keeps its mixed-account workflow, analytics contract and tests together. Discount-code creation/editing belong together because they use one component. Archive and restore share one confirmation dialog. Shared integration-test mock changes accompany the menu Tooltip.

## Outcomes & Retrospective

This branch contains only the menu labels, Tooltip explanations, analytics contract and relevant test adaptations. The remaining dialog changes are delivered by successive branches in the stack. No merge or deployment is part of this task.

## Context and Orientation

The menu is in `src/web/src/app/admin/components/ShifuCard.tsx`. Shared strings live in `src/i18n/`. The canonical Tooltip analytics contract is in `docs/product-specs/course-action-help.md`.

## Plan of Work

Preserve the five scoped changes while restacking them on current main. Fix each verified review issue in a separate commit, validate the affected behavior, and reply or resolve only after verification. Track checks and reviews against the final head of every PR.

## Concrete Steps

1. Save the complete implementation and local copy corrections.
2. Rebase the menu on main, then replay each subsequent PR on its parent branch.
3. Generate keys and indexes, run focused tests, TypeScript, translations and repository gates.
4. Push with explicit expected-head leases, retarget each PR to its parent, and synchronize the stack links.
5. Wait at least five minutes after each push before refreshing review feedback; continue until all applicable checks are terminal and no unhandled review remains.

## Validation and Acceptance

Each PR has a focused diff against its parent and passes checks on its own stacked head. The union of their source and translation changes matches the approved combined implementation. Existing-account nickname behavior remains confined to PR #3192. User acceptance of the screenshots remains pending.

## Idempotence and Recovery

Keep the original branch and local screenshot artifacts until acceptance. Do not reset user files, rewrite main, or merge any PR. Branches use the `sunner/` prefix and contain normal commits.

## Interfaces and Dependencies

Preserve existing API and permission contracts. Tooltip events and mixed learner activation have separate specifications and privacy-safe tests. There are no package or lockfile changes.

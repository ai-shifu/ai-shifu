---
title: Review course action changes independently
status: active
owner_surface: frontend
last_reviewed: 2026-10-27
---

# Course action review split

## Purpose / Big Picture

Replace the combined course-action PR with separately reviewable changes for the menu, learner activation, discount codes, collaborators, and archive/restore dialogs. Preserve the approved behavior and later copy corrections. The backend nickname fix remains separate in PR #3192.

## Progress

- [x] 2026-10-27: Saved the combined implementation and subsequent copy corrections before splitting.
- [x] 2026-10-27: Partitioned source changes and translation leaves into five branches based on the same main revision.
- [ ] Verify each branch on its own and await user acceptance.

## Surprises & Discoveries

The original PR changed shared translation files across all surfaces. Partition individual translation keys, and regenerate TypeScript keys and documentation indexes per branch instead of copying combined generated files.

## Decision Log

Each branch targets main directly. Menu help and its analytics contract belong together. The learner dialog keeps its mixed-account workflow, analytics contract and tests together. Discount-code creation/editing belong together because they use one component. Archive and restore share one confirmation dialog. Shared integration-test mock changes accompany the menu Tooltip.

## Outcomes & Retrospective

This branch contains only the menu labels, Tooltip explanations, analytics contract and relevant test adaptations. The remaining dialog changes are delivered by sibling branches. No merge or deployment is part of this task.

## Context and Orientation

The menu is in `src/web/src/app/admin/components/ShifuCard.tsx`. Shared strings live in `src/i18n/`. The canonical Tooltip analytics contract is in `docs/product-specs/course-action-help.md`.

## Plan of Work

Partition the original patch without dropping changes. Validate and commit each branch independently. Open ready PRs for all five branches, then close the superseded combined PR #3193 with links to its replacements.

## Concrete Steps

1. Save the complete implementation and local copy corrections.
2. Apply each surface's components, tests and translation leaves on a clean main-based branch.
3. Generate keys and indexes, run focused tests, TypeScript, translations and repository gates.
4. Push each branch and create its ready PR; close the original only after replacements exist.

## Validation and Acceptance

Each PR passes its checks without requiring another split PR. The union of their source and translation changes matches the approved combined implementation. Existing-account nickname behavior remains confined to PR #3192. User acceptance of the screenshots remains pending.

## Idempotence and Recovery

Keep the original branch and local screenshot artifacts until acceptance. Do not reset user files, rewrite main, or merge any PR. Branches use the `sunner/` prefix and contain normal commits.

## Interfaces and Dependencies

Preserve existing API and permission contracts. Tooltip events and mixed learner activation have separate specifications and privacy-safe tests. There are no package or lockfile changes.

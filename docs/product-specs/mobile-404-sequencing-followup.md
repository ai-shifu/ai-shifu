---
title: "Mobile 404 Follow-up: Sequencing Improvement Plan"
status: proposed
owner_surface: frontend
last_reviewed: 2026-11-09
canonical: true
---

# Mobile 404 Follow-up: Sequencing Improvement Plan

## Background

The course layout retries transient course-info failures with capped exponential
backoff. An explicit course-not-found error redirects to `/404`. A definitive
access denial stops retries. The course API and preview-layout tests cover these
branches.

The layout gates course fetches on environment initialization. It still has a
separate TODO for sequencing WeChat OAuth, user initialization, and course-info
requests on weak networks.

## Goal
- Reduce transient course-load failures caused by client-side initialization order.

## Proposed Sequencing Refactor
1. Gate course-info fetch on OAuth readiness in WeChat.
2. Gate course-info fetch on user initialization completion.
3. Preserve the existing backoff and terminal-error handling while adding
   the readiness gates.

## Candidate Files
- `src/web/src/app/c/[[...id]]/layout.tsx`
- `src/web/src/store/UserProvider.tsx`
- `src/web/src/api/course.ts`

## Acceptance Criteria
- New users opening `/c/:id` on mobile do not hit false `/404` under weak network.
- WeChat in-app browser path is stable with and without `code` query.
- Genuine not-found courses still redirect to `/404`.

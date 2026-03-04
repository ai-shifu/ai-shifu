# Mobile 404 Follow-up: Sequencing Improvement Plan

## Background
- Current hotfix only narrows `/404` redirect conditions.
- We still have potential race windows on mobile/WeChat where OAuth, user init, and course loading run in parallel.

## Goal
- Reduce transient course-load failures caused by client-side initialization order.

## Proposed Sequencing Refactor
1. Gate course-info fetch on OAuth readiness in WeChat.
2. Gate course-info fetch on user initialization completion.
3. Add lightweight retry with backoff for non-not-found course-info errors.
4. Keep `/404` redirect only for explicit not-found signals.

## Candidate Files
- `src/cook-web/src/app/c/[[...id]]/layout.tsx`
- `src/cook-web/src/store/userProvider.tsx`
- `src/cook-web/src/c-api/course.ts`

## Acceptance Criteria
- New users opening `/c/:id` on mobile do not hit false `/404` under weak network.
- WeChat in-app browser path is stable with and without `code` query.
- Genuine not-found courses still redirect to `/404`.

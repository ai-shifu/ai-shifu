# Operator Course/User Request Optimization

## Context

The operator course list and user list currently do too much work inside the paginated list endpoints:

- both list APIs recompute overview cards on every paging/search request
- the user list returns full created/learning course arrays for every row even though the dialog is opened on demand
- the course list computes course prompt flags before pagination, which scales with the whole candidate set

This makes the course list especially slow and also adds avoidable load to the user list.

## Goals

- keep existing operator page behavior unchanged for operators
- reduce repeated backend work for paging and search
- reuse existing user detail endpoint for course dialog details instead of creating a parallel API
- keep DTO and route changes small and compatible with current admin patterns

## Plan

1. Split course overview and user overview into dedicated backend endpoints.
2. Remove overview computation from the paginated list endpoints.
3. Slim user list rows to counts for created/learning courses, then fetch full course arrays only when the dialog opens.
4. Defer course prompt flag calculation to paginated course rows only.
5. Update frontend pages to request overview data separately and load user course dialog data on demand.

## Non-goals

- no deep SQL-side rewrite of the course list filtering/sorting path in this change
- no dashboard or unrelated operator page refactors
- no new generic data-fetch abstraction

## Verification

- targeted backend pytest for operator course/user admin flows
- targeted frontend page tests for course and user operator pages
- frontend type-check and lint after request contract changes

## Follow-up Opportunities

- move course list filtering, sorting, and pagination further down to SQL to avoid Python-side full-set work
- consider caching or pre-aggregating 30-day course activity metrics if overview traffic grows
- consider denormalizing latest course activity fields if the outline activity scan becomes the next bottleneck

---
title: Operator Course/User Request Optimization
status: implemented
owner_surface: frontend
last_reviewed: 2026-11-09
canonical: true
---

# Operator Course/User Request Optimization

## Context

The operator course and user lists previously rebuilt their overview on paging
and search. The user list also returned course arrays eagerly, and the course
list calculated prompt flags before pagination.

## Goals

- keep existing operator page behavior unchanged for operators
- reduce repeated backend work for paging and search
- reuse existing user detail endpoint for course dialog details instead of creating a parallel API
- keep DTO and route changes small and compatible with current admin patterns

## Plan

The paginated lists and their overview endpoints are separate. The course and
user overview requests run after the initial list settles. The user list returns
created/learning course counts and loads course arrays from user detail on
demand. The course list calculates prompt flags for the selected page.

The backend paths are `admin_operations/courses_listing.py` and
`admin_operations/users.py` under the shifu service. The corresponding Cook
Web operations course and user page tests cover deferred overview loading.

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

---
title: Agent-First Harness Migration
status: implemented
owner_surface: repo
last_reviewed: 2026-04-17
canonical: true
---

# Agent-First Harness Migration

## Summary

Rework the repository around an agent-first harness so repository knowledge,
execution plans, and validation loops are explicit, versioned, and mechanically
checked.

## Goals

- Introduce a repository knowledge layout that acts as the system of record.
- Replace the legacy `tasks.md` workflow with `PLANS.md` plus ExecPlans.
- Shrink root/backend/frontend AI entry points into navigation-first docs.
- Add a minimum browser-plus-log harness that agents can use to validate fixes.

## Constraints

- Keep HTTP APIs, DB schema, and shared i18n contracts unchanged.
- Keep `docs/engineering-baseline.md` at its current path.
- Migrate flat docs instead of keeping duplicate copies.

## Deliverables

- Root knowledge docs and generated indexes
- Updated AI-doc generation and validation scripts
- Playwright smoke coverage with diagnostics artifacts
- Backend request-id diagnostics script

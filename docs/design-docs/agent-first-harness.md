---
title: Agent-First Harness Migration
status: implemented
owner_surface: repo
last_reviewed: 2026-11-09
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

- Root knowledge docs and committed generated indexes. See the
  [knowledge workflow](../README.md#workflow) for validation and derived reports.
- Updated AI-doc generation and validation scripts
- Playwright smoke coverage and diagnostics artifacts in the Runtime Harness workflow
- Backend request-ID diagnostics in `src/api/scripts/harness_diagnostics.py`
- Static Checks validate committed knowledge artifacts. The scheduled Harness
  Gardening job separately checks document freshness, retired terms, and stale
  architecture baseline entries.

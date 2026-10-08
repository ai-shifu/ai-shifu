---
title: Retired shared course answers
status: superseded
owner_surface: learner
last_reviewed: 2026-10-08
canonical: false
---

# Retired shared course answers

The user cancelled cross-course custom-variable sharing on 2026-10-08.
[System and course variable isolation](course-variable-scopes.md) is the current
contract. Registered system fields remain global; custom variables stay within
the current course. Author declarations cannot grant an exception.

The former `course:` and `share:` syntax no longer resolves source values or
writes back answers. Both namespaces remain reserved so old settings, model
calls and pending answers cannot recreate aliases. Existing classroom evidence
and source data are preserved; no historical data migration is performed.

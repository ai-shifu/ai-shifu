---
title: AI Doc Hard Rules Restoration
status: implemented
owner_surface: repo
last_reviewed: 2026-04-17
canonical: true
---

# AI Doc Hard Rules Restoration

## Summary

Restore the non-optional engineering guardrails that used to be visible in the
main instruction surfaces without discarding the new layered AI-doc structure.

The repository will keep:

- layered `AGENTS.md` and `CLAUDE.md` inheritance
- `docs/<topic>.md` plus an active root `tasks.md` workflow
- `docs/engineering-baseline.md` as the complete engineering handbook

The repository will change:

- root, backend, and frontend `AGENTS.md` become explicit hard-rule entry
  points again instead of thin baseline links
- generated Cursor and Copilot mirrors restate the same guardrails
- validation fails when those guardrails disappear from the primary manual
  docs
- Claude-only manual rules stop being baseline-only redirects

## Problems

- The current root, backend, and frontend `AGENTS.md` files describe process
  structure well, but several hard engineering rules are now only discoverable
  after opening `docs/engineering-baseline.md`.
- Cursor and Copilot mirrors currently inherit the same thin guidance, so the
  compatibility surfaces drift toward process reminders and away from actual
  engineering guardrails.
- `scripts/check_ai_collab_docs.py` only validates headings and baseline links
  for the manual docs, so a future edit can silently delete key constraints
  while the validator still passes.

## Decisions

### Manual AGENTS ownership

- Keep `AGENTS.md`, `src/api/AGENTS.md`, and `src/cook-web/AGENTS.md`
  hand-maintained.
- Keep the standard `Scope`, `Do`, `Avoid`, `Commands`, `Tests`, and
  `Related Skills` headings.
- Reintroduce hard constraints directly in those docs:
  - root: English-only code-facing text, inspect-before-edit, reuse-first,
    no hardcoded user strings or secrets, minimum verification, design/tasks
    workflow, shared-contract doc sync
  - backend: new migration instead of editing applied revisions, no hard DB
    foreign keys for business-key relationships, shared response envelope and
    error-code path, shared i18n under `src/i18n/`, config updates coupled to
    env example regeneration, shared LiteLLM/provider wrappers
  - frontend: unified request stack through `lib/request.ts` and `lib/api.ts`,
    no ad-hoc component fetch logic, shared i18n only, `c-*` compatibility
    surfaces remain live, Next.js naming and route-entry conventions

### Handbook boundary

- Keep `docs/engineering-baseline.md` as the complete handbook and example
  source.
- Do not remove detail from the baseline unless it duplicates the primary
  manual docs so closely that future drift becomes likely.
- Treat the baseline as the place for expanded rationale, examples, and
  troubleshooting, not as the only place where mandatory rules appear.

### Mirror and validation model

- Update generated `.cursor` and `.github` mirrors so they restate the same
  key guardrails rather than only pointing to the baseline.
- Update manual `.claude/rules/**` files so their routing guidance includes
  the same high-signal constraints for the surface they narrow to.
- Extend `scripts/check_ai_collab_docs.py` with explicit marker checks for the
  manual root/backend/frontend docs and the key manual Claude rules.

## Compatibility

- No runtime product behavior changes
- No API, database, or i18n contract changes
- No change to the AI doc file names or layered inheritance model

## Verification

- `python scripts/generate_ai_collab_docs.py`
- `python scripts/check_ai_collab_docs.py`
- `pre-commit run --files AGENTS.md src/api/AGENTS.md src/cook-web/AGENTS.md docs/design-docs/ai-doc-hard-rules-restoration.md docs/engineering-baseline.md scripts/generate_ai_collab_docs.py scripts/check_ai_collab_docs.py .claude/rules/global/testing-and-commit.md .claude/rules/backend/python-api.md .claude/rules/frontend/cook-web.md .cursor/rules/repository-ai-collab.mdc src/api/.cursor/rules/backend-api.mdc src/cook-web/.cursor/rules/cook-web.mdc .github/copilot-instructions.md .github/instructions/ai-instructions.instructions.md .github/instructions/backend.instructions.md .github/instructions/frontend.instructions.md`

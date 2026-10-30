---
title: Present course memory with contextual question and answer wording
status: completed
owner_surface: shared
last_reviewed: 2026-10-30
canonical: false
---

# Present course memory with contextual question and answer wording

## Purpose / Big Picture

The overall feature is Memory, and questions and answers form its entry structure.
Teachers use those entries to understand course authoring and simulation. Personal
information keeps its specific labels, and the learner's course-scoped collection
remains Course memory. Change presentation only, preserving all existing
keys, identifiers, storage, memory admission, sharing, replacement and deletion
behavior. Do not add a question identity model or answer history.

## Progress

- [x] 2026-10-30 08:23 UTC: Confirmed the approved contextual wording and the
  requirement to preserve existing key identity and memory behavior.
- [x] 2026-10-30 08:23 UTC: Fetched main and created
  `sunner/course-question-answer-copy` at `f7a1eae7b` in the existing worktree.
- [x] 2026-10-30 08:29 UTC: Updated all eight locales, contextual simulation
  placeholders, help and examples; preserved all existing keys and arguments.
- [x] 2026-10-30 08:29 UTC: Passed 183 tests in nine focused frontend suites,
  type checking, translation parity/usage checks and the repository harness
  using Node 22.23.4 and the existing Python environment.
- [x] 2026-10-30 08:32 UTC: Passed every all-file pre-commit gate after JSON key
  ordering was normalized; the final diff has no unrelated changes.
- [x] 2026-10-30 08:34 UTC: Committed the verified implementation as `6cf3aa038`
  and published ready [PR #3249](https://github.com/ai-shifu/ai-shifu/pull/3249)
  against main without merging it.
- [x] 2026-10-30 08:45 UTC: Applied the clarified Memory feature hierarchy in
  all eight locales and the owning documents. Revalidated 183 focused tests,
  exact translation keys and arguments, translation usage and the repository
  harness without changing code or data behavior.

## Surprises & Discoveries

- The pinned `markdown-flow-ui@0.3.6` has no exposed variable configuration
  wording requiring a library change. Its existing editor and renderer protocols
  remain unchanged.
- The preview contains both custom answer keys and system information. Its
  placeholders must distinguish simulated answers from personal information.
- Stored course memory does not have provenance sufficient to label every entry
  as an original learner answer. Keep its neutral management wording.
- The worktree initially lacked frontend dependencies. The existing source
  checkout's Python environment has the repository's pinned Markdown parser.
- Independent review caught a misleading personal-settings suggestion in system
  definition errors. Those definitions cannot be edited there; the final copy
  describes the restriction without offering an unavailable action.

## Decision Log

- Follow existing variable behavior throughout: exact keys still determine
  identity, same-course reuse and the current value. Changing a key does not
  transfer its saved answer to the new key.
- Name the overall feature and teacher panel Memory. Questions and answers are
  its entry structure; Course memory is the scoped learner-facing name. Preserve
  specific profile labels and neutral wording for visibility actions.
- Keep existing translation keys and interpolation arguments. Add one localized
  personal-information placeholder with a `label` argument.
- Preserve API fields, database schema, local-storage keys, MarkdownFlow syntax,
  runtime prompts, component versions and analytics contracts. This copy-only
  change creates no new interaction path and needs no new analytics event.

## Outcomes & Retrospective

All eight locales use Memory as the overall feature name and describe its
questions and answers as the content structure. Contextual simulation placeholders
are implemented and
published in ready [PR #3249](https://github.com/ai-shifu/ai-shifu/pull/3249).
The 183 focused frontend tests, type checking, translation checks, documentation
harness and all-file pre-commit gates pass with unchanged data and protocol
contracts. Hosted PR checks remain separate from these local results. The
implementation and local acceptance scope is complete; no main merge or
deployment is included.

## Context and Orientation

The shared locale JSON files own frontend and backend user-facing text.
`VariableList` renders the existing simulation key/value map and system labels;
its change callback and persistence consumers must keep receiving exact keys.
The learner's course-memory dialog already uses neutral entry presentation.
The profile routes expose legacy field names that remain compatibility contracts.

## Plan of Work

Update the simulation, related profile errors and course-memory help in all eight
supported locales. Select a personal-information placeholder for existing system
rows and a simulated-answer placeholder for custom rows. Document contextual
terminology, complete-question keys, exact identity and unchanged admission.
Reuse existing simulation, memory and localization tests and repository checks.

## Concrete Steps

1. Update locale values without renaming keys or altering existing placeholders.
2. Adjust only placeholder selection in the existing simulation component.
3. Align terminology and examples in the owning product and reference documents.
4. Regenerate translation types and repository knowledge indexes as needed.
5. Run focused tests, translation checks, the repository harness, developer-tool
   checks and all-file pre-commit hooks.
6. Commit with the required English Conventional Commits title and
   `Changed:` / `Benefit:` body, push the feature branch and create a ready PR.

## Validation and Acceptance

All eight locales must describe the same actions and retain ICU parameter parity.
Ordinary legacy keys, complete-question keys and system keys must display and
submit unchanged. Editing simulated values, hiding/restoring entries, refreshing
cached answers and same-course key reuse retain existing behavior. System
placeholders use their localized labels. Course-memory deletion language must
retain its existing scope. Environment and notification-template variables are
outside this terminology change.

## Idempotence and Recovery

There is no data migration, schema change, cache reset or live-course mutation.
Existing scripts and saved values remain readable without conversion. Reverting
the presentation commit restores the old copy without affecting stored records.
Never merge the branch into main automatically.

## Interfaces and Dependencies

No public API, DTO, tool, event or persistence interface changes. The new
`module.shifu.previewArea.personalInfoPlaceholder` translation takes `label`;
all pre-existing translation arguments remain unchanged. Use the currently
pinned component libraries and generate no dependency or lockfile changes.

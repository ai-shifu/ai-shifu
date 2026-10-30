# Retire Legacy Default Profiles

## Purpose / Big Picture

Retire the built-in meanings of `sex`, `birth`, `avatar`, `language` and
`sys_user_style`. These exact names remain usable as ordinary course variables.
Only `sys_user_nickname`, `sys_user_language` and `sys_user_background` retain
global profile semantics. Account settings and canonical learner-profile
collection remain available. The durable contract is
[System and course variable isolation](../../references/course-variable-scopes.md).
Existing formal and editor-preview sessions continue through the ordinary
session lifecycle. Default-profile retirement does not rewrite their saved
prompts or snapshots.

## Progress

- [x] 2026-10-30 11:28 UTC: Confirmed the approved field list, ordinary-course
  semantics and database-preservation boundary; created a feature branch from
  current `origin/main` (`bcf2d118c`).
- [x] 2026-10-30 11:42 UTC: Coordinate profile definitions, canonical mappings,
  account recovery and language selection.
- [x] 2026-10-30 11:42 UTC: Remove frontend style prefill and retired presentation
  rules; update shared translations, fixtures and contracts.
- [x] 2026-10-30 11:42 UTC: Complete isolated backend/frontend regression,
  independent scope review and repository gates; prepare the feature branch for
  review without merging main.
- [x] 2026-10-30 11:48 UTC: Rebase onto `b618c8c4c` after main advanced during
  validation. Preserve its question-and-answer copy, resolve locale conflicts,
  and rerun 139 profile/golden/Swagger checks, all 193 affected frontend tests,
  type-check and the full repository pre-commit gate.
- [x] 2026-10-30 22:55 UTC: Record the final session boundary: remove the dedicated
  retirement cleanup and marker for both formal and debug sessions. Keep existing
  saved sessions as-is; new formal sessions read current course memory, while
  editor previews use their supplied variables.
- [x] 2026-10-30 23:10 UTC: Clarify review feedback on initialization sources:
  formal sessions use `load_memory`, while editor previews use supplied
  `preview_variables` without reading learner memory from the database.

## Surprises & Discoveries

- The current main branch has already removed the old `context_v2` runtime and
  manual variable-definition APIs. This change uses the remaining shared engine
  host and automatic definition creation rather than restoring removed paths.
- Historical global definitions survive a code cleanup. Definition reads and
  automatic collision handling must filter them without changing stored rows.
- The old `language` name also participates in output-language selection and
  preview restart handling. Removing only its profile label leaves that behavior.
- Saved initial prompts can retain injected values after the current profile
  registry changes. The accepted scope leaves those historical snapshots as-is;
  the current profile reader does not imply that old prompts have been cleaned.
- A preview can remember a course note without persisting it or returning it to
  the editor's variable map. Continuing that preview uses its existing cached
  state. Restarting selects a fresh session; unused cached sessions expire
  naturally.
- Existing courses may have only a retired global definition. The first normal
  scoped assignment creates the missing course definition and uses its ID; no
  historical row is migrated and arbitrary undeclared notes gain no definition.
- Pre-existing untracked `logs/` contain example identifiers unrelated to source
  validation. Repository checks use a temporary Git excludes file for those logs;
  the logs remain untracked and are not edited or committed.

## Decision Log

- Keep database models, columns, migrations and historical values unchanged.
  Tests use temporary SQLite storage and mocked providers, never business data.
- Remove the entire default-profile session compatibility layer, including its
  cleanup, version marker and serialization hooks. Formal and debug sessions
  retain their ordinary loading, continuation and persistence behavior.
- Keep debug cache keys and the thirty-minute expiry unchanged. A preview restart
  creates a new session ID; existing cached state remains available for its run
  until it expires. No namespace or cache version is introduced.
- Keep the three active system keys in a shared exact-name allowlist. A `sys_`
  prefix alone never grants global scope; existing undeclared-memory restrictions
  still apply to `sys_user_style`.
- Ordinary variables require a course identifier before any writes are staged.
  Fresh scoped reads do not use old global defaults for a missing course value
  or account field. Existing session prompts may still contain earlier values.
- Preserve generic profile endpoint paths and response envelopes. Their built-in
  labels contain only the active fields, including canonical language.
- Keep the newer authoring rule that rejects all `sys_` question bindings.
  Retained published courses still persist exact retired `sys_user_style`
  answers through a narrow runtime-only definition option; that option cannot
  create any other reserved course definition and is never enabled by authoring.
- Preserve current request/canonical language precedence, supported-language
  normalization and disabled-multilingual behavior. Course `language` values do
  not select teaching language and are never automatically overwritten.
- Reuse existing generic variable interactions and analytics contracts. No new
  action, event family or payload field is introduced by this retirement.

## Outcomes & Retrospective

The three canonical fields now own global profile behavior. Retired names use
course scope, including old courses whose next answer creates a missing local
definition. Old definitions, values, account columns and applied migrations are
unchanged. Formal and debug sessions keep their ordinary lifecycle with no
default-profile cleanup, retirement marker or new cache namespace. New formal
sessions initialize from the current scoped `load_memory` result; editor previews
initialize from supplied `preview_variables` without reading database memory.
Continued sessions retain their saved state under the existing generic session
logic; old injected prompts are not guaranteed to be free of retired defaults.

The final session simplification passed all 1,701 agent and route regressions,
including ordinary continuation of saved inputs and accepted answers and preview
notes surviving requests without an editor variable echo.

Earlier integrated backend validation passed 4,311 tests with 90 conditional skips.
The eight affected frontend suites passed all 193 tests. Type-check, lint,
translation usage/parity, architecture boundaries, repository harness and the
full pre-commit gate passed. Independent review found and verified fixes for
legacy-definition assignment and preview user-scope note persistence. No live
provider calls, business-database changes, deployment or main merge were needed.

## Context and Orientation

The profile service owns field registration, scoped variable definitions and
canonical mapping. User repository recovery and phone/email merges consume those
helpers. The learning agent host owns output-language policy and resumed-session
memory. Shared frontend profile and lesson-preview components consume the same
wire contracts; locale JSON and generated key types live in the shared i18n tree.

## Plan of Work

Unify active system keys, remove retired field metadata and account mappings, and
filter global definition reads and automatic creation without changing course
definitions. Remove legacy style prefill and account recovery. Coordinate the
canonical language policy with frontend preview controls. Keep existing session
snapshots under the ordinary lifecycle and remove the dedicated default-profile
compatibility module, marker and storage hooks. Update fixtures and source-backed
documentation with focused regression.

## Concrete Steps

1. Implement the profile/user contract and isolated storage regressions.
2. Implement canonical-only language selection and verify ordinary session
   continuation, formal-session memory loading, supplied preview variables and
   preview restart isolation.
3. Remove frontend compatibility branches, unused translations and helper code;
   regenerate i18n types and run component/hook regressions.
4. Run type/lint and repository checks, review the integrated diff, record exact
   outcomes, and deliver a dedicated branch and reviewable pull request.

## Validation and Acceptance

- All five names can hold independent current-course values without reading old
  global rows or modifying account fields. Exact-case identity is preserved.
- Old global definitions remain stored but are neither advertised nor reused for
  automatic course-variable creation. Reads never mutate or delete old values.
- Active nickname/language/background mappings, moderation, clear behavior and
  sign-in merge remain covered. Mixed invalid writes fail before partial changes.
- Empty canonical learner profiles never prefill old style. Explicit authored
  style variables remain visible through generic preview controls.
- Output-language selection uses canonical `sys_user_language` and leaves ordinary
  course `language` values untouched.
- Existing formal and debug sessions use the original generic lifecycle without
  default-profile snapshot cleanup or retirement metadata. Saved prompts may
  retain earlier values.
- New formal sessions initialize from `load_memory`; editor previews initialize
  from supplied `preview_variables` and do not read learner memory from the
  database.
- Preview restart uses a fresh debug session ID. Cache key construction and the
  thirty-minute expiry remain unchanged, and continuation retains cached notes.
- Focused backend and frontend suites, type-check, lint, repo harness,
  architecture boundaries, translation checks and pre-commit gates pass.

## Idempotence and Recovery

The change needs no schema migration, data rewrite, dependency update or feature
flag. Re-running tests creates isolated temporary storage. Rollback restores code;
historical global rows remain available to the old implementation. Do not merge
or enable auto-merge to main.

## Interfaces and Dependencies

The profile-label list replaces the old `language` field with
`sys_user_language` and omits other retired defaults. `legacy_profile_values`
retains only nickname compatibility. Generic variable APIs keep their existing
DTO shape; non-system writes require course scope. SSE and questionnaire
protocols, engine-library interfaces and account-setting endpoints are unchanged.

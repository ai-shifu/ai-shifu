# Retire Legacy Default Profiles

## Purpose / Big Picture

Retire the built-in meanings of `sex`, `birth`, `avatar`, `language`,
`sys_user_style` and `sys_user_input`. Ordinary course variables retain their
existing definition, read and write rules, including the generic `sys_` authoring
restriction.
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
- [x] 2026-10-31 00:35 UTC: Remove the remaining retired-name compatibility scope:
  no retired-key registry, missing-definition repair, ID rebinding or reserved
  prefix exception. Keep the three active system keys and ordinary course rules.
- [x] 2026-10-31 00:40 UTC: Validate the registry-removal scope with 5,565 integrated
  backend regressions and 93 conditional skips, three additional supplied-ID
  cases, and the full repository pre-commit gate.
- [x] 2026-10-31 01:25 UTC: Extend the cleanup to `sys_user_input`: remove automatic
  variable injection and overwrites, fixed hiding and the dedicated system label.
  Keep ordinary defined/explicit preview values, request messages and the
  formatter's empty-template fallback under their existing rules.
- [x] 2026-10-31 01:31 UTC: Validate the input-variable cleanup with 5,584 backend
  regressions and 93 conditional skips, 120 frontend tests, type checking, lint
  and the full repository pre-commit gate.

## Surprises & Discoveries

- The current main branch has already removed the old `context_v2` runtime and
  manual variable-definition APIs. This change uses the remaining shared engine
  host and ordinary authoring-time definition creation rather than restoring
  removed paths.
- Historical global definitions survive a code cleanup. Definition reads expose
  only registered system fields and existing course definitions, without changing
  stored rows.
- The old `language` name also participates in output-language selection and
  preview restart handling. Removing only its profile label leaves that behavior.
- Saved initial prompts can retain injected values after the current profile
  registry changes. The accepted scope leaves those historical snapshots as-is;
  the current profile reader does not imply that old prompts have been cleaned.
- A preview can remember a course note without persisting it or returning it to
  the editor's variable map. Continuing that preview uses its existing cached
  state. Restarting selects a fresh session; unused cached sessions expire
  naturally.
- Existing courses may have only a historical global definition. A later value
  write does not repair that missing course definition. Undefined `sys_` keys
  remain excluded from supplementary reads under the existing generic rule.
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
  prefix alone never grants global scope. Keep no retired-key registry or
  reserved-prefix exception for former defaults.
- Ordinary variables require a course identifier before any writes are staged.
  Fresh scoped reads do not use old global defaults for a missing course value
  or account field. Existing session prompts may still contain earlier values.
- Preserve generic profile endpoint paths and response envelopes. Their built-in
  labels contain only the active fields, including canonical language.
- Keep the authoring rule that rejects all `sys_` question bindings. Existing
  stored course definitions use ordinary key/scope reads and writes. Value writes
  do not create missing definitions, and undefined `sys_` keys remain excluded
  from supplementary course-memory reads.
- Keep each writer's existing definition-BID resolution. Former names receive no
  forced ID rebinding; runtime value selection remains by key and scope.
- Remove the built-in `sys_user_input` injection, overwrite and UI rules. Existing
  course-defined values and explicitly supplied preview values follow ordinary
  variable handling, with no exception to reserved-prefix authoring rules.
- Keep normal learner input in request messages. Preserve the optional
  `get_fmt_prompt` `user_input` empty-template fallback; production callers do not
  pass that argument.
- Preserve current request/canonical language precedence, supported-language
  normalization and disabled-multilingual behavior. Course `language` values do
  not select teaching language and are never automatically overwritten.
- Reuse existing generic variable interactions and analytics contracts. No new
  action, event family or payload field is introduced by this retirement.

## Outcomes & Retrospective

The three canonical fields own global profile behavior. Other variables use
ordinary course paths, without a retired-name registry, definition repair, ID
rebinding or reserved-prefix exception. Old definitions, values, account columns
and applied migrations are unchanged. Formal and debug sessions keep their
ordinary lifecycle with no default-profile cleanup, retirement marker or new
cache namespace. New formal sessions initialize from the current scoped
`load_memory` result; editor previews initialize from supplied `preview_variables`
without reading database memory.
Continued sessions retain their saved state under the existing generic session
logic; old injected prompts are not guaranteed to be free of retired defaults.
`sys_user_input` receives no automatic value or dedicated UI treatment; ordinary
request messages and explicit variable values retain their existing behavior.

The input-variable follow-up passed 5,584 profile, user, learning, authoring,
golden and formatter regressions with 93 conditional skips in isolated SQLite
storage. Four affected frontend suites passed all 120 tests. Type checking,
lint, translation parity/usage, generated i18n types and the full pre-commit gate
passed. The historical migration is unchanged.

Earlier registry-removal validation passed 5,565 profile, user, learning, authoring
and golden regressions with 93 conditional skips in isolated SQLite storage.
Three supplied-definition-ID cases added after that suite's collection also
passed separately. The full repository pre-commit gate passed, including the
harness, architecture boundaries, translations, lint and formatting.
The prior `f2b3c9b45` implementation also passed its complete CI. Those results
precede the `sys_user_input` follow-up and do not validate that added scope.

Earlier session simplification passed all 1,701 agent and route regressions,
including ordinary continuation of saved inputs and accepted answers and preview
notes surviving requests without an editor variable echo.

Earlier integrated backend validation passed 4,311 tests with 90 conditional skips.
The eight affected frontend suites passed all 193 tests. Type-check, lint,
translation usage/parity, architecture boundaries, repository harness and the
full pre-commit gate passed. These results precede the final removal of the
retired-name compatibility paths and do not validate that final scope. No live
provider calls, business-database changes, deployment or main merge were needed.

## Context and Orientation

The profile service owns field registration, scoped variable definitions and
canonical mapping. User repository recovery and phone/email merges consume those
helpers. The learning agent host owns output-language policy and resumed-session
memory. Shared frontend profile and lesson-debug components consume the same
wire contracts; locale JSON and generated key types live in the shared i18n tree.

## Plan of Work

Unify active system keys, remove retired field metadata and account mappings, and
restrict global definition reads to active fields without changing ordinary
course-definition paths. Remove the retired-key registry, definition repair,
ID rebinding and reserved-prefix exception. Remove legacy style prefill and
account recovery. Coordinate canonical language policy with frontend preview
controls. Keep existing session snapshots under the ordinary lifecycle and remove
the dedicated default-profile compatibility module, marker and storage hooks.
Update fixtures and source-backed
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

- Existing course definitions use ordinary exact-key and course-scope values
  without reading old global defaults or modifying account fields.
- The system definition list includes only the three active fields. Ordinary
  value writes do not repair definitions or apply retired-name-specific ID
  rebinding. Existing authoring and supplemental-reader prefix rules apply
  without exceptions.
- Historical definitions and values remain stored. Reads never mutate or delete
  old values; an undefined `sys_user_style` value is not loaded by the supplement.
- Active nickname/language/background mappings, moderation, clear behavior and
  sign-in merge remain covered. Mixed invalid writes fail before partial changes.
- Empty canonical learner profiles never prefill old style. Existing course
  variables remain visible through generic preview controls.
- `sys_user_input` is not automatically injected or overwritten and has no fixed
  hiding rule or dedicated system label. Defined course values and explicit
  preview values retain ordinary behavior; generic `sys_` authoring restrictions
  remain unchanged.
- Normal learner input still travels through request messages. The formatter's
  optional empty-template input fallback remains available without adding
  production callers of that argument.
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

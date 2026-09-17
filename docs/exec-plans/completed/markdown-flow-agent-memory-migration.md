# Expose Learner Memory through a Typed Host Facade

## Purpose / Big Picture

Provide a small host memory interface that current learning code and a future
MarkdownFlow engine adapter can use while AI-Shifu keeps its existing storage
and business rules. Memory is the API-level concept; variables are its first
supported category, including changes made through existing settings paths.
`MemorySnapshot` and `MemoryUpdate` keep variable payloads in a dedicated
`variables` field so future non-variable categories can have their own typed
payloads and storage without changing the top-level read/write operations.

The user explicitly chose to omit interaction-source associations. Consequently,
this stage does not distinguish an interaction answer from a settings edit,
retain a separate last-interaction value, or introduce provenance metadata.
Accepted named course interactions continue to save their variables through the
existing path. There is no new extraction producer or second persistence step.

AI-Shifu already saves these values. The implementation deliverable is a stable
access boundary, consistent reads across learning paths, and proof
that the established behavior is preserved. It is not a new memory database or
a claim that variable persistence was previously missing.

The user authorized execution of this plan on 2026-09-17. Implementation and a
focused pull request are now in scope; engine activation, deployment, and PR
merge remain outside this task. Existing syntax, prompts, SSE, profile mappings, progress,
preview, follow-ups, listening/TTS, and billing remain compatibility gates.

## Progress

- [x] 2026-09-17 04:29 UTC: Investigated the original engine memory contract
      and created the initial migration plan.
- [x] 2026-09-17 05:16 UTC: Synchronized to `759ac2cbf`, including the
      vendored MarkdownFlow 2.0 engine from PR #2830.
- [x] 2026-09-17 05:48 UTC: Validated the previous provenance-reference
      proposal; that design is superseded by the user's latest decision.
- [x] 2026-09-17 06:24 UTC: Fetched main and fast-forwarded this task branch
      to `82c0979c538dc4aedb11844cee3cde94dba61ea0`, preserving local docs.
- [x] 2026-09-17 06:24 UTC: Rechecked current memory readers, profile-variable
      writes, assignment commit timing, and the new engine gateway adapter.
- [x] 2026-09-17 06:25 UTC: Redesigned the plan around existing current-value
      storage, explicit course scope, and a thin memory facade without provenance.
- [x] 2026-09-17 06:28 UTC: Regenerated indexes; repository harness,
      required-section, timestamp/path, removed-design, and whitespace checks passed.
- [x] 2026-09-17 06:36 UTC: Added the thin facade and integrated the two
      existing runtime calls; preserved settings/profile and transaction ownership.
- [x] 2026-09-17 06:39 UTC: Focused memory/value-resolution tests passed
      (21 tests), including real settings updates, canonical clearing, and rollback.
- [x] 2026-09-17 06:40 UTC: Extended the existing profile public API with
      the staged writer export; architecture and UOW checks passed without waivers.
- [x] 2026-09-17 06:45 UTC: Installed current pinned requirements in an
      isolated Python 3.11.16 environment; 277 relevant regressions passed and four
      historical tests skipped, including memory, golden, preview, listen, and profile suites.
- [x] 2026-09-17 06:44 UTC: Full `lefthook run pre-commit --all-files`
      passed, including architecture, UOW, translations, Python, and frontend checks.
- [x] 2026-09-17 06:52 UTC: Full backend verification passed in the current
      pinned environment with process-local proxy settings removed: 4,452 passed,
      107 skipped, and 46 subtests passed.
- [x] 2026-09-17 06:52 UTC: Completed implementation and verification;
      archived this plan and prepared the focused change for PR publication.

- [x] 2026-09-17 07:34 UTC: Reopened the plan after the user requested a
      memory-oriented contract that can later carry non-variable memories.
- [x] 2026-09-17 07:40 UTC: Replaced variable-named operations and exposed
      profile DTOs with typed memory envelopes. Focused verification passed:
      149 tests, four legacy skips, including real persistence and mapped SSE.
- [x] 2026-09-17 07:43 UTC: Full backend verification passed: 4,455 tests,
      107 skips, and 46 subtests. Full lefthook, architecture, UOW, and repository
      Ruff checks passed; completed the memory-envelope revision for PR #2834.

- [x] 2026-09-17 08:16 UTC: Verified the remote rebase preserves all three
      feature commits and aligned this branch to `792f4625b` on main `58a81c1ae`.
- [x] 2026-09-17 08:20 UTC: Routed preview, Ask, follow-up fallback, and
      prompt formatting fallback reads through memory. Focused verification:
      187 passed and four legacy skips; no direct learning-side profile-value
      reads remain outside the memory adapter.
- [x] 2026-09-17 08:26 UTC: Full backend verification passed: 4,478 tests,
      107 skips, and 46 subtests. Full lefthook, Ruff, architecture, and UOW checks
      passed. The completed read migration is ready for PR #2834; remote checks
      and review are followed against the published commit.

## Surprises & Discoveries

- `var_variable_values` already stores `user_bid`, `shifu_bid`, `key`, and
  `value`. The existing `learn/memory/reader.py` also exposes course scope.
  A new course-ID column or memory-value table is unnecessary.
- The existing memory reader and the teaching variable reader are different
  contracts. `load_learner_memory` reads broad stored values and groups other
  courses under `elsewhere`; `get_user_profiles` resolves course definitions,
  system labels, and canonical profile overrides for runtime use. Flattening
  the broad reader is not a behavior-preserving replacement for the latter.
- Settings can write course-scoped custom variables, and account changes can
  write system variables. Without provenance, memory intentionally exposes
  their current values too. This is the boundary the user accepted.
- `save_user_profiles` appends a value row only when its selected value differs.
  It can reuse a global fallback, map system labels to canonical fields, and
  mutate the supplied `ProfileToSave` objects before SSE emission. Those are
  compatibility details, not new memory policies to reimplement.
- The assignment path flushes variables before `VARIABLE_UPDATE` yields and
  commits them through `RunRecorder.update_progress_pointer`. The facade must
  preserve this ownership; it must not add a commit or wrap a generator in a
  transaction.
- Latest main adds `learn/agent/gateway_model.py` in PR #2831, connecting the
  vendored engine's model abstraction to `chat_llm`, and a Python 3.12 ping++
  compatibility fix in PR #2832. Neither is a completed learning-engine switch
  or a new memory store. These were synchronized changes, not work implemented
  by this task.
- Implementation check: importing `profile.funcs` from the new facade would
  add architecture debt. `profile/api.py` already exports the reader; extend
  that stable entry point to export the existing writer too, then import both
  through it. The profile implementation and transaction rules remain intact.
- The shared local `.venv` predates the vendored engine and lacks
  `pydantic_ai`. The plugin loader then skips the learning routes, causing
  unrelated 404s in broad tests. Use an isolated environment installed from
  current requirements instead of changing routes or the shared environment.
- Full-suite environment check: the inherited SOCKS proxy needs an optional
  `socksio` dependency absent from the pinned backend environment. Seven
  Langfuse tests failed during SDK construction for that reason; the same
  issue reproduced on an untouched `82c0979c5` archive. All seven pass with
  proxy environment variables removed for that test process. No repository
  dependency or global proxy setting was changed.

- The optional arena engine suite has four pre-existing mock-signature failures:
  mocked stream iterators reject `tool_calls_are_output`. The unchanged
  `792f4625b` archive reproduces the same four failures and 30 passes. The
  changed preview-isolation arena test passes in both trees; unrelated observer
  tests are outside this memory migration.

## Decision Log

- Follow-up scope: all four remaining learning-side profile-value reads must
  use `load_memory(...).as_variables()`. Preserve caller-supplied resolved
  values (including an empty dictionary), preview overlays, and language
  selection without another read or any write. Account-profile writes and
  the facade's private profile adapter keep their existing ownership.

- Follow-up decision: expose `load_memory` / `stage_memory` with
  `MemorySnapshot` / `MemoryUpdate`. Variables are one explicit category,
  represented by `VariableMemoryUpdate`; profile DTO conversion stays private.
  Preserve mapped update values on the caller's mutable variable payloads.
  Future categories must add their own typed fields and persistence handlers;
  do not predeclare unsupported fact/summary fields or store them as variables.

- User decision: do not add course-interaction provenance for now. Memory is
  the current course-variable view; later settings edits are reflected in it.
- Reuse existing profile/variable storage and services. No new table, column,
  migration, origin marker, source receipt, copied value, reference table,
  backfill, cache, vector store, or extraction pipeline is planned.
- Reuse the existing `learn/memory` package. Add only a small runtime facade;
  preserve the public broad reader and its course/global/elsewhere behavior.
- The runtime facade delegates reads to `get_user_profiles` and staged writes
  to `save_user_profiles`. It owns neither SQL selection rules nor transactions.
- Preserve exact values, system-label scope routing, canonical user authority,
  `ProfileToSave` behavior, and current error/return contracts. Do not move
  globally stored system labels into course rows in the name of isolation.
- The only learning producer being integrated is successful named assignment.
  Existing settings/profile producers continue normally through their existing
  services; all readers see the same authoritative data afterward.
- Remove the previous reference model, exact-row receipts, recorder changes,
  cancellation additions, collection flag, migration, and new atomic-write
  requirements. They existed to support the now-removed second data structure.
- No feature flag is needed for these behavior-preserving delegations. A later
  capability that changes retrieval, prompts, or engine selection must define
  its own default-off rollout; do not invent a flag that disables existing
  variable saving or duplicates identical code paths here.
- The new engine will require an explicit host adapter. This stage creates
  its access boundary, not a drop-in implementation of whole-user dictionary
  replacement or activation of the new tool loop.

## Outcomes & Retrospective

The earlier designs treated provenance as a prerequisite and introduced extra
storage and transaction work. With the user's latest decision, the core task
is much smaller: expose existing course-variable behavior behind a stable
memory interface and keep learning semantics intact.

The result deliberately cannot answer which interaction produced a value or
recover a previous course answer after a settings edit from the memory API.
Existing historical records may remain, but this feature makes no provenance
or historical-answer reconstruction guarantee.

The facade and runtime integration are complete. In the current pinned test
environment, 277 relevant regressions passed and four legacy tests skipped
because their old async helper methods no longer exist. The final full backend
run passed: 4,452 tests and 46 subtests, with 107 skips. Golden fixtures are
unchanged. The new cross-service dependency uses the existing profile public
API; architecture, UOW, toolchain doctor, and full lefthook checks passed.
No schema, origin metadata, engine activation, or new model call is introduced.

The memory-envelope follow-up adds `MemorySnapshot`, `MemoryUpdate`, and
`VariableMemoryUpdate`, with `load_memory` / `stage_memory` as the stable
entry points. The 149 focused tests pass, including three additional contract
regressions. Full backend verification now passes with 4,455 tests, 107 skips,
and 46 subtests. Full lefthook and repository checks pass. The 4,452-test result
above describes the initial facade implementation. Both revisions preserve
the same storage and transaction authority; non-variable storage remains future
work. That revision completed the envelope design.

The four-read follow-up is complete: preview, Ask, follow-up context fallback,
and prompt-formatting fallback all use the memory facade. Focused verification
passed 187 tests with four legacy skips; the full backend suite passed 4,478
tests and 46 subtests with 107 skips. Full lefthook and repository checks passed,
and two obsolete direct-profile architecture exemptions were removed. The
optional arena suite retains four baseline mock-signature failures, reproduced
on the unchanged branch head; its changed preview-isolation test passes.
PR publication delivers this focused change for review; engine replacement
and new memory usage remain separate work. Deployment and merge are not part
of this execution.

## Context and Orientation

Current host baseline: `58a81c1ae` on `sunner/memory-migration-plan`, with
the prior memory changes rebased to `792f4625b`. Paths below are repository-relative.

The original source investigation used `/Users/sunner/src/markdown-flow-agent`
at `c31d64fed8d1ad689f2117bcd75448538c5a23cc`, read-only. This is distinct
from the old `markdown-flow-agent-py` package. Source code is now vendored under
`src/api/flaskr/service/learn/agent/engine/` and owned by this repository;
external re-copying is unnecessary.

| Existing component              | Location                                                            | Use in this plan                                                                                |
| ------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Variable definitions and values | `src/api/flaskr/service/profile/models.py`                          | Existing data model and scope identities; no schema changes.                                    |
| Runtime read and staged write   | `src/api/flaskr/service/profile/funcs.py`                           | `get_user_profiles` and `save_user_profiles` remain authoritative.                              |
| Existing write DTO              | `src/api/flaskr/service/profile/dtos.py`                            | Use `ProfileToSave` only inside the facade adapter; memory callers use their own typed payload. |
| Broad memory reader             | `src/api/flaskr/service/learn/memory/reader.py`                     | Preserve `MemoryEntry`, `LearnerMemory`, `load_learner_memory`, and `elsewhere`.                |
| Learning integration            | `src/api/flaskr/service/learn/context_v2.py`                        | Route ordinary course preparation and accepted assignment through the facade.                   |
| Commit ownership                | `src/api/flaskr/service/learn/run/recorder.py`                      | Existing pointer step commits staged profile rows; no implementation change.                    |
| Canonical learner profile       | `src/api/flaskr/service/profile/learner_profile.py`                 | Existing update/clear authority; no duplicate profile memory.                                   |
| Future engine contract          | `src/api/flaskr/service/learn/agent/engine/memory.py`, `session.py` | Engine-local user/session memory requires a later scoped host adapter.                          |

The source engine has a `MemoryStore.load(user_id)` / `save(user_id, dict)`
protocol and session memory that overrides user memory when merged. It writes
named interaction answers into session memory, permits model-selected
`remember` calls, and includes merged memory in its initial prompt. Its
reference store replaces the entire user dictionary. None of these broad
behaviors should be enabled merely to expose existing course variables.

## Plan of Work

### 1. Define memory as current state with existing ownership

| Logical category        | Identity                              | Owner and first-stage behavior                                                                             |
| ----------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Canonical user fields   | User and field name                   | Existing profile/account services; canonical values override compatibility variable rows exactly as today. |
| Custom course variables | User, `shifu_bid`, exact variable key | Existing variable service; current selected value follows existing resolution rules.                       |
| Global/system variables | User and existing global key          | Preserve empty `shifu_bid` routing and existing fallback; no automatic new global facts.                   |
| Session state           | Existing session/attempt context      | Runtime retains messages, temporary answers, and progress; no new persistence layer.                       |

Course scope spans lessons. Course titles, outline IDs, and session IDs do not
replace `shifu_bid`. Same-named custom variables in different courses stay
independent; existing intentionally global system fields keep their shared
semantics. Read/write calls receive explicit user and course identities from
trusted learning context. A future public entry point must perform its own
authorization; the internal facade does not turn arbitrary IDs into permission.

Memory now means current state, not a separate set of interaction observations.
Existing values are available immediately without data migration or an
activation-date filter. A settings edit changes what a subsequent memory read
returns. Do not add a hidden origin field in another table, log, JSON blob,
or key prefix as a workaround for the rejected provenance design.

### 2. Define memory envelopes and two facade operations

Create `src/api/flaskr/service/learn/memory/facade.py` with explicit runtime
read and staged-write functions. Export them through the existing package.
Implemented signatures appear under Interfaces and Dependencies.

`load_memory` returns a `MemorySnapshot` whose `variables` field is
loaded from `get_user_profiles` using the supplied user/course context.
The runtime explicitly calls `as_variables()` to project prompt variables.
Preserve definition filtering, global fallback, canonical label mapping,
defaults, and error behavior. Do not populate it with
`load_learner_memory(...).as_variables()`, append `elsewhere`, or overlay stale
entity-owned rows. Keep runtime language selection in its existing caller.

`stage_memory` accepts a `MemoryUpdate` patch, converts its
`VariableMemoryUpdate` payloads to private `ProfileToSave` objects, and
delegates once to `save_user_profiles`. It preserves the boolean return
contract and copies mapped values back to the original variable payloads
for subsequent `VARIABLE_UPDATE` events. An empty patch is a no-op, and
omitted variables are never deletions. A snapshot is a read view, not a patch.
The facade does not return source receipts, read back rows, copy values into
another store, or create a second normalization path.

Keep these operations synchronous within the caller's existing Flask app/DB
context. The profile service remains unaware of the memory facade, avoiding a
reverse dependency. Use no generic provider registry, repository hierarchy,
new configuration, or abstract base class without an actual second backend.

Keep `load_learner_memory` as the explicit broad inspection API. Its stored-value
view and `elsewhere` are useful but differ from runtime-effective variables.
Update nearby descriptions to say stored/current values may include settings
edits, and clarify that identical-value saves can reuse a row. Preserve the
reader's queries, DTO fields, limit behavior, and exports.

### 3. Integrate the existing course path without extra persistence

In `context_v2.py`, replace the ordinary course preparation read in
`_prepare_step_state` with `load_memory`. Replace the single profile
save in the successful named-assignment branch of
`_phase_validate_input_and_advance` with `stage_memory`.

```text
Current course preparation:
  authenticated user/course
  -> memory.load_memory
  -> existing get_user_profiles
  -> existing runtime language resolution and prompt construction

Accepted named interaction:
  existing moderation + validation + value normalization
  -> memory.stage_memory
  -> existing save_user_profiles, including flush and canonical mappings
  -> existing VARIABLE_UPDATE events
  -> existing progress step commits the same staged rows
```

Do not call both the facade and original writer. Complete the learning-side
read boundary in `_resolve_preview_variables`, `_phase_handle_ask_input`,
`build_follow_up_conversation_context`, and `get_fmt_prompt`. Each resolves
`load_memory(...).as_variables()` only where it previously loaded profiles.
Keep already-resolved request dictionaries authoritative, even when empty,
so follow-up formatting does not reload or resurrect stored values. Preview
request overrides apply to the copied variable projection and never mutate
the memory snapshot. Preview stores retain their existing ownership. Do not add stricter parameter checks here that silently alter
legacy preview or empty-scope behavior.

Keep list joining, empty-string handling, variable definition IDs, system-label
mapping, the position of yields, and progress advancement exactly where they
are. No new moderation or model call is introduced. Rejected input, unnamed
answers, and continue buttons retain their existing paths and gain no new
variable producer. Listening inherits the same accepted-assignment path;
TTS/element protocols remain untouched.

### 4. Preserve transactions, lifecycle, and corrections

The facade is not a transaction owner. It must neither commit/rollback nor
open a UOW spanning yields or provider calls. It preserves the existing writer's
flush and the recorder's eventual commit. No new reference failure path,
post-commit capture, outbox, or queue remains in the design.

A disconnect or commit failure retains existing rollback behavior. Exceptions
must not be swallowed or converted into a successful memory save. Do not add
partial retries of recorder steps with profile riders. A value staged in the
current session is not claimed durable until the existing owner commits it.

Current settings/profile corrections become visible through the same backing
store, so there is no memory-copy synchronization problem. Canonical profile
clearing remains authoritative and must not revive a compatibility row.
Existing account cancellation, course/preview cleanup, deleted-row handling,
and sign-in migration keep their existing ownership and semantics. There is
no new data copy or cleanup hook to add. This is not a broader redesign of
existing retention/deletion behavior.

Rollback is a normal code revert of the facade integration. Existing readers
and data remain usable; no schema downgrade, value rewrite, reference purge,
or collection-flag operation is required.

### 5. Keep later engine integration explicit

The future engine should supply authenticated user/course context to this
facade, adapt accepted assignments into a typed memory update, and use the host's
learning transaction to make changes durable. Its session memory remains
session state until a permitted assignment is explicitly persisted.

Compatibility here means a reusable host access boundary. It does not mean
the current whole-user `MemoryStore.save` protocol can be wired directly to
`stage_memory`. A stale snapshot must not be interpreted as a set
of user edits, and missing keys must not become deletions. Future integration
needs explicit assignment mutations and course context, with a separate
async/runtime bridge if required. Do not encode the course into `user_id`.

The existing vendored engine and new `GatewayModel` remain unchanged in this
stage. Engine selection, new memory prompt content, general `remember`,
free-text extraction, and cross-course personalization need separately scoped
implementation and default-off rollout. If extraction is later requested,
compare tool-based and independent extraction then; neither is necessary to
persist already-validated variables.

### 6. Exact implementation inventory

The implementation follows this inventory; progress and verification are
recorded above.

| File                                                                          | Planned change                                                                                                       |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `src/api/flaskr/service/learn/memory/dtos.py` (new)                           | Memory snapshot/update envelopes and a variable-specific update payload.                                             |
| `src/api/flaskr/service/learn/memory/facade.py` (new)                         | Memory operations and private adaptation to existing profile reads/writes.                                           |
| `src/api/flaskr/service/learn/memory/__init__.py`                             | Export the facade alongside existing reader exports; document current-state semantics.                               |
| `src/api/flaskr/service/learn/memory/reader.py`                               | Clarify descriptive text about settings/current values; retain query and DTO behavior.                               |
| `src/api/flaskr/service/learn/context_v2.py`                                  | Use memory for course preparation, preview variables, Ask reads, and accepted writes; preserve SSE and commit order. |
| `src/api/flaskr/service/learn/follow_up_context.py`, `utils_v2.py`            | Route fallback reads through memory while preserving supplied resolved values and language overlays.                 |
| `src/api/flaskr/service/profile/api.py`                                       | Export the existing staged writer alongside the reader to preserve the cross-service architecture boundary.          |
| `src/api/tests/service/learn/memory/test_facade.py` (new)                     | Behavioral round-trip, scope, settings-update, canonical-field, and staged-write contract coverage.                  |
| Relevant existing tests in `src/api/tests/service/learn/` and `tests/golden/` | Adjust directly imported mocks only where the changed call sites require it; retain expected results and fixtures.   |
| This ExecPlan and generated indexes                                           | Keep decisions, scope, milestones, and validation evidence current.                                                  |

The profile implementation/DTOs/models, recorder, migrations, config/env examples,
account cancellation, engine, gateway, frontend, prompts, and billing are reused
without planned implementation edits. If inspection reveals that a behavior
change is necessary, document the concrete reason before expanding this narrow
plan; a larger memory architecture is not a prerequisite.

### 7. Milestones and acceptance boundaries

1. **Facade contract.** Add the two operations and package documentation with
   focused behavior checks using existing profile services. Acceptance: current
   values resolve identically, settings changes are reflected, canonical fields
   keep authority, and writes stage without committing.
2. **Current learning integration.** Route the teaching read/write and all
   four remaining learning-side fallback/preview/Ask reads through the facade. Acceptance: one save per accepted assignment, same mapped SSE
   values, identical prompt inputs, and unchanged progress/rollback behavior.
3. **Compatibility completion.** Run relevant learning, preview, listening,
   profile, and golden checks, plus required repository gates. Acceptance: no
   schema/config changes, no added model calls, and no new observable learning
   behavior. Finish the focused implementation PR under repository conventions.

New-engine activation and new memory usage are not acceptance requirements for
these milestones. The present implementation task does not authorize deployment or
claim the future engine integration is complete.

## Concrete Steps

Completed code refresh before this revision:

```sh
git fetch origin main
git merge --ff-only origin/main
```

The fast-forward reached `82c0979c5` and preserved all local documentation.
For the documentation updates, run from the repository root:

```sh
python3 scripts/build_repo_knowledge_index.py
python3 scripts/check_repo_harness.py
git diff --check
git status --short --branch
```

Before implementation, reconcile the latest baseline and read the nearest
`AGENTS.md`. If creating another worktree, copy existing local `.env` files as
required, without exposing or committing them. No migration generation or schema
mutation is required for this design.

Run the smallest relevant checks in a backend environment installed from the
current requirements. The implementation used an isolated Python 3.11.16 venv
at `/tmp/ai-shifu-memory-venv`; the shared local `.venv` was left unchanged.

```sh
cd src/api
SKIP_LOAD_DOTENV=1 SKIP_APP_AUTOCREATE=1 pytest -q tests/service/learn/memory tests/service/profile/test_variable_value_resolution.py
SKIP_LOAD_DOTENV=1 SKIP_APP_AUTOCREATE=1 pytest -q tests/service/learn/test_context_v2.py tests/service/learn/run
SKIP_LOAD_DOTENV=1 SKIP_APP_AUTOCREATE=1 pytest -q tests/golden/test_run_sse_golden.py tests/service/learn/test_preview_permissions.py
```

Include affected profile UOW, learner-profile clear/mapping, listening/TTS,
and stream-disconnect checks. Reuse existing meaningful coverage; do not add
only mock-delegation tests or broaden database stress tests for unchanged SQL.
Run required backend gates for any shared contract changes actually introduced.

For the full backend check on this host, run from `src/api` with process-local
proxy settings removed so the offline Langfuse SDK fixtures can initialize:

```sh
env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy \
  SKIP_LOAD_DOTENV=1 SKIP_APP_AUTOCREATE=1 \
  /tmp/ai-shifu-memory-venv/bin/python -m pytest -q --tb=short --disable-warnings
```

Before an implementation commit: `python3 scripts/check_dev_tools.py`,
`lefthook run pre-commit --all-files`, `python3 scripts/check_repo_harness.py`,
`python3 scripts/check_architecture_boundaries.py`, and
`python3 scripts/check_uow_commit_sites.py`. If a later task changes the vendored
engine, its mandatory offline suite is
`python -m pytest tests/service/learn/agent/engine/ -q` from `src/api`.

## Validation and Acceptance

| Scenario                                                 | Expected result                                                                                                       |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Accepted course assignment, commit, fresh read           | Same saved value is available through the facade without a second copy or write.                                      |
| Same key in two courses or two users                     | Existing ownership and fallback rules are preserved; no other-course value is merged into runtime variables.          |
| Settings changes an existing course value                | Subsequent memory read returns the changed current value; no provenance distinction is claimed.                       |
| Pre-existing variable rows                               | Available under existing read rules immediately, without backfill or origin filtering.                                |
| System labels, canonical nickname/language/background    | Same mapping and canonical override as the direct profile-service path.                                               |
| Canonical learner-profile clear                          | Cleared profile stays empty; no stale variable-row resurrection.                                                      |
| Same-value repeat, changed value, unrelated keys         | Same append/reuse behavior as existing writes; no whole-dictionary replacement or deletion of omitted keys.           |
| Multi-select, empty accepted value, Unicode keys         | Identical normalization, stored value, DTO mutation, and emitted variable update.                                     |
| Unnamed input, rejected validation/moderation, Ask, Live | No added variable save; original behavior remains.                                                                    |
| Preview and listening                                    | Existing preview isolation and media/interaction behavior are unchanged.                                              |
| Failure or disconnect around the existing commit         | Same staged-row rollback/durability boundary; facade does not commit, retry, or hide errors.                          |
| Current read versus broad memory reader                  | Runtime matches `get_user_profiles`; broad reader keeps `entries`, `elsewhere`, exclusions, and truncation semantics. |
| Prompt, SSE, model count, progress, billing              | Existing fixtures and observable results remain unchanged.                                                            |
| Memory snapshot projection                               | `as_variables()` returns a copy; preview and runtime overlays cannot mutate the snapshot.                             |
| Resolved values supplied to follow-up/prompt formatting  | Reuse them, including an empty dictionary; no duplicate memory read or revival of stored values.                      |
| Ask stream completion                                    | Scope the memory read to the current user/course and keep the existing commit after the stream.                       |
| Partial or empty memory patch                            | Omitted values survive and an empty patch adds no row.                                                                |
| Memory payload to profile adapter                        | Definition IDs, list/empty normalization, raw stored values, and mapped SSE values survive the boundary.              |

Use fictional learner A with courses Alpha and Beta. Set Alpha's `base_level`
to `beginner` through an accepted interaction and Beta's to `advanced`. After
commit, each course reads its own value. Edit Alpha through the existing
settings path to `intermediate`; the facade now reads `intermediate`. The API
does not promise to retain or identify the earlier interaction answer. Learner
B sees none of A's course data. Clearing canonical learner profile must remain
visible as an empty value regardless of stale compatibility rows.

Add or identify a transaction test proving that facade staging plus a failed
owning step does not leave a committed variable. Keep golden fixtures unchanged;
update mock import targets where necessary rather than weakening expectations.
No live model completion, production database, or learner data is needed for
this verification. Tests use fictional data, temporary SQLite, and fake model
responses. App startup can attempt model-list discovery using test credentials;
that is not a live inference or deployed-behavior check. The recorded backend
test results above are the runtime evidence, separate from documentation checks.

## Idempotence and Recovery

The existing writer selects/reuses or appends values under its established
rules. The facade adds no idempotency token, source ordering, merge policy,
retry loop, or uniqueness constraint. Existing largest-row-ID ordering and
concurrency limitations remain; this refactor does not claim to fix them.

Current values are always read from their existing authority, so there is no
memory projection to rebuild or reconcile. A code revert restores direct calls
without data repair. Re-running the documentation generator should produce no
additional changes after the first regeneration.

Forgetting, historical reconstruction, source tracking, and broader deletion
policies require later explicit requirements. Do not recreate provenance as
part of recovery or infer it from old learning logs.

## Interfaces and Dependencies

The public facade uses memory-owned types and explicit user/course identity:

```python
from flask import Flask
from flaskr.service.learn.memory import MemorySnapshot, MemoryUpdate


def load_memory(app: Flask, user_bid: str, shifu_bid: str) -> MemorySnapshot:
    """Load the supported memory categories for this learner/course context."""


def stage_memory(
    app: Flask, user_bid: str, shifu_bid: str, update: MemoryUpdate
) -> bool:
    """Stage an explicit memory patch; the existing caller owns the commit."""
```

`MemorySnapshot.variables` holds effective runtime values. `as_variables()`
returns a copy for prompt construction, excluding any future non-variable
categories. `MemoryUpdate.variables` is a list of `VariableMemoryUpdate`
objects carrying `key`, `value`, and optional `definition_bid`. It is a patch,
never a whole-memory replacement. Staging copies existing profile mappings
back into these mutable payloads for the established variable-update events.
The boolean return indicates the writer result, not a durable commit.

To add facts or summaries later, define a payload appropriate to that category,
add a dedicated field to both envelopes as needed, and implement its storage
handler in the facade. Existing variable callers continue using the same API.
Do not force free text into variable keys, inject it via `as_variables()`, or
claim an unsupported category is already saved. This revision adds no such
field, extraction, backend, registry, provider hierarchy, or engine activation.

`ProfileToSave` remains an internal storage-adapter detail. The existing
`MemoryEntry`, `LearnerMemory`, and `load_learner_memory` broad inspection API
retain their stored-row semantics; they are not the runtime snapshot.
SQLAlchemy, Flask context, profile services, and current UOW ownership remain
the implementation dependencies; no new package or service is required.

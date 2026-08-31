# Let learners answer onboarding questions with their AI

## Purpose / Big Picture

Keep the existing question → review → save flow while allowing a learner to
copy a public questionnaire prompt to their AI and import its answer into the
same session. Nothing reaches the saved learner profile before confirmation.
Administrators compile one public prompt when saving MarkdownFlow, never on
learner access. Existing configurations without a prompt remain usable.

## Progress

- [x] 2026-08-26 CST: Read root/subtree guidance and current runtime/config/UI.
- [x] 2026-08-26 CST: Fetched main and created
  `sunner/profile-onboarding-ai-import` at `7b60e7aee707be74945474c0a00e4ffe7d54930d`
  in an isolated feature worktree; copied local environment
  files without overwriting existing files or changing the source checkout.
- [x] 2026-08-26 CST: Compile and atomically publish public prompts on admin save.
- [x] 2026-08-26 CST: Implement same-session import, replay, and rollback safety.
- [x] 2026-08-26 CST: Adapt source copy/paste/draft UX to the current dialog.
- [x] 2026-08-26 CST: Verify five locales, regression suites and browser layouts.
  All eight Chinese/Arabic viewport flows pass; the existing narrow RTL course
  shell overflow is recorded below rather than silently treated as clean.
- [x] 2026-08-26 CST: Commit `9070a4b0e`, push ready PR #2669 targeting main.
  Initial remote CI all passed, including backend and runtime harness.
- [x] 2026-08-26 CST: Verify scoped natural-review follow-ups; publish each
  independent fix as its own commit. Latest CI and review state is maintained
  on PR #2669; no merge or deployment is part of completion.

## Surprises & Discoveries

- Current main already contains the PR2 structural refactor and five locales;
  old modal files cannot replace current files. Runtime sessions live behind
  `profile_research/api.py`; official MarkdownFlow remains pinned to 0.3.1.
- `add_config` commits before refreshing cache and returns `None` for an env
  override. Its return/exception is not proof of an uncommitted write.
- `sys_configs.key` has no unique constraint. First publication must use the
  same serialization boundary as later updates, with a fresh database read.
- Local tools initially lack pinned Ruff 0.16.3 and worktree node_modules;
  dependencies were prepared locally without modifying the source tree.
- A real browser found that the official renderer remounted interaction inputs
  on sibling re-renders even though the conversation stayed mounted. A stable
  memo boundary and unchanged hidden-question props preserve unsent input. The
  regression test now models the library behavior, and all eight viewport
  runs confirm retention, including import failure and return.
- Ordinary settings dismissal is not explicit abandonment: it preserves the
  raw draft; confirmed discard, save, skip, and logout clear it.

## Decision Log

- Publication uses a connection-scoped MySQL advisory lock, not an expiring
  Redis lease, so it covers first inserts and cannot expire mid-commit. A fresh
  app-scoped DB session compares the full previously read JSON before writing.
  Reject nested units of work before compilation so isolated sessions cannot
  accidentally skip the commit boundary.
- Effective reads for this one config go directly to the DB (except explicit
  overrides), preventing the generic cache-miss reader from restoring stale
  data after a publication. Generic configuration helpers remain unchanged.
- If delegate session serialization succeeds but active-pointer refresh fails,
  read back and return the committed replay result. If its outcome cannot be
  read, use the existing busy error to require the same request retry; never
  imply that the learner can safely advance another operation.
- The local source Python environment had MarkdownFlow 0.3.0. Install 0.3.1
  without dependencies in `/tmp/pr3-python` and prepend that directory for all
  authoritative tests; do not alter the source checkout or its virtualenv.
- i18n type regeneration also restores six already-present Arabic email plural
  keys omitted by main's generated file; no unrelated locale text was changed.

- Reuse sources `876eba7b8aec5d9a5add903cc7006b9a40091e72` (old #2238) and
  `331a54f5312ad8d65be1769e04bec1bb084ee30f` (split source) only for extraction,
  never as branch bases. PR2 #2308 merged at `7b3dfdde6faabd80d05cd281c7ce4fd0a74efe9b`.
- Source provenance: split-source `ProfileOnboardingModal.tsx` lines 76–132
  contain account-scoped sessionStorage read/write/clear helpers, lines 338–349
  clipboard feedback/fallback, and approximately 830–892 copy/paste JSX.
  `ProfileOnboardingModal.test.tsx` lines 960–1065 characterize restore and
  account-switch/closed-dialog/legacy cleanup. Adapt these hunks; do not restore
  selection screens, static prompts, old limits, or the old saving protocol.
- New work is public prompt compilation/publication, freezing that prompt in
  sessions, parsing imported evidence, and bridging it into the existing
  official final-summary block. Keep all ordinary manual editing/optimization,
  moderation, profile replacement, and guided/settings source contracts.
- Only this worktree may change. Separate agents own runtime, learner UI, and
  admin/i18n; the primary owns configuration publication and integration.

## Outcomes & Retrospective

Implementation, local/browser verification, and ready PR publication are
complete. Initial remote CI passed. Natural-review follow-ups were verified
locally and committed separately; the PR records the latest post-push CI state.
Current evidence: full frontend Jest **175 suites / 1,438 tests**,
TypeScript and ESLint pass (existing global warnings remain); backend focused
config/profile suite **112 tests**, runtime/routes/request-validation suite
**195 tests**, using official MarkdownFlow **0.3.1** installed in `/tmp/pr3-python`.
Final combined focused run: **309 passed**. Full backend run: **3,354 passed,
17 skipped** in 196 seconds; publication tests: **9 passed**, including a real
two-thread first-save race against the SQLite persistence fixture. Full staged
lefthook checks pass. A subsequent frontend review caught delegate validation
errors being treated as fatal; delegate-only correction/back/retry now passes
the 27-test conversation suite with the actual invalid error code. Architecture
has **0 new violations** (133 pre-existing baseline). No deployment or merge
has been performed. LLM behavior is tested with deterministic providers; this
is not a claim of live-model semantic accuracy. SQLite persistence tests replace
MySQL GET_LOCK with a test lock, while separate tests exercise advisory-lock
acquisition/cleanup failures with mocked connections.

## Review Follow-up

PR: https://github.com/ai-shifu/ai-shifu/pull/2669 (ready, base main).
Initial commit `9070a4b0e` passed all remote checks, including backend tests
(6m32s), frontend tests, runtime harness (7m58s), static checks, lint, formatting,
CodeQL, and GitGuardian. Ready is not a merge-readiness claim: GitHub reported
BEHIND main, although conflict-free. No merge or deployment was performed.

Natural CodeRabbit review
https://github.com/ai-shifu/ai-shifu/pull/2669#pullrequestreview-5027665065
has six nonblocking suggestions. Fixed orphaned account drafts at logout (`414e00248`) and
focus restoration on subview switches (`bfb50c25d`) in separate verified commits. Draft
cleanup passed 17 focused tests including missing/stale pointer and storage
failures; view focus passed 40 focused tests, full TypeScript, and ESLint.
Entering focuses the instructions so the copy step stays first, and returning
restores the entry without stealing initial focus or scrolling. Skip
moving existing storage tests and consolidating already-tested limit literals
as low-value layout/style changes. Keep the uncertain-request synchronous ref:
every mutation is paired with reducer dispatch, and retry-control tests cover
its rendering; adding duplicated state fixes no current failure. Do not add
redundant locale plumbing: the shared SSE transport already resolves current
(and pending) UI language through `getCurrentLanguageHeaders` when no explicit
language is provided; the frozen public prompt is never localized.

Devin observation
https://github.com/ai-shifu/ai-shifu/pull/2669#discussion_r3860413947
asks whether nickname-only confirmation may replace an existing introduction
with an empty one. This is the approved replacement contract: show the exact
result in the confirmation editor and only write after explicit confirmation;
do not merge old saved information automatically. Explain without changing
behavior and left the thread open (not a verified fix); explanation:
https://github.com/ai-shifu/ai-shifu/pull/2669#discussion_r3860462617. Copilot could not
review because of quota exhaustion; do not report it as approval. No reviewer
was manually triggered.

Second natural review
https://github.com/ai-shifu/ai-shifu/pull/2669#pullrequestreview-5027762459
identified a component boundary that allowed assistant support without its
controlled draft or setter. Current production callers supply both; nevertheless,
the entry/view now requires them together, with regressions for each omission
and restoration without recreating the session. This is a separate review fix,
validated with 68 conversation/dialog tests and full TypeScript. Remote CI for
`efe2371ad` passed all checks before publishing this final boundary correction.

A later natural Codex review
https://github.com/ai-shifu/ai-shifu/pull/2669#discussion_r3860605044
found that resetting the raw assistant draft only in a passive effect could
render the previous account's draft once under a new scope. The follow-up binds
the state to its account scope and masks mismatched content synchronously;
stale callbacks from the old account must not write drafts. Verification must
capture the first render, not merely the DOM after effects have flushed. The
39-test dialog suite verifies first-render masking, account B restoration,
stale callback rejection, same-account reopening, and closed account switches.

The earlier nickname-only observation was subsequently resolved by its reviewer,
not by this task, as conforming to the approved contract:
https://github.com/ai-shifu/ai-shifu/pull/2669#discussion_r3860549604.

## Browser Evidence

Real headed Chromium exercised the actual Next.js course shell and official
MarkdownFlow renderer at 1440×900, 360×640, 390×844, and 844×390, in both zh-CN
and ar-SA. Controlled local API/SSE fixtures were used; these are not physical
device or live backend/LLM integration tests. Every run preserved unsent input
and the same session, copied the exact saved public prompt, avoided submission
for typing plus an 800ms wait, and auto-processed a real clipboard paste into
confirmation. Editing the nickname produced exactly one complete request.
Question/AI/confirmation dialog bounds stayed equal; inner scrolling exposed
Back/Process controls while the fixed footer stayed visible. Arabic HTML/dialog
direction was RTL, and its copied prompt was identical to Chinese UI output.
An invalid-import SSE response retained paste text and pending question input.

The unchanged underlying course ChatUi header/LearningModeSwitch extends left
of the narrow Arabic viewport (about -105px at 360px); document scrollWidth is
465px. This offsets viewport screenshots even though dialog bounds remain
x=12/right=348 and pointer hit-testing is correct. Full-page captures show the
complete dialog. This existing shell/capture limitation remains outside scope;
there is no claim that all app layouts are free of horizontal overflow.

Local evidence is in `/tmp/pr3qa-report.md`, `/tmp/pr3qa-results-zh.txt`,
`/tmp/pr3qa-results-ar.txt`, `/tmp/pr3qa-failure-result.txt`, and
`/tmp/pr3qa-*.png`. Temporary browser fixtures and captures are not committed.

## Context and Orientation

Configuration is the single JSON `PROFILE_ONBOARDING_FLOW` in `sys_configs`.
`service/common/profile_onboarding.py` owns its contract; the operator route
rejects unknown fields. `service/profile_research/{session,runtime,document}.py`
own Redis snapshots, official parsing, locks, SSE and request replay. Learner
profile services own final moderation/persistence. `LearnerProfileDialog`, its
controller/model/views, and `ProfileOnboardingConversation`/session hook own the
frontend. Admin previews share the conversation but cannot import AI answers.

## Plan of Work

1. Validate raw MarkdownFlow with the official runtime, compile a public prompt
   with the existing LLM wrapper and a template in `src/api/prompts`, outside
   publication locks. Reuse an existing prompt when document content is unchanged.
2. Publish markdownflow/prompt/revision together, checking all 65,535 UTF-8 bytes,
   rejecting nonpersistable configuration and stale concurrent saves. Read the
   database at publication time. Distinguish committed cache failure in response.
3. Freeze prompt/document on session creation. Import raw text (10,000 characters),
   cursor and request_id under existing owner → session locks; parse untrusted
   data on a copy, preserve manual facts, run official final summary once, and
   save only the completed temporary state. Replay exact operation/body/cursor.
4. Keep question component mounted while copy/paste subview is open. Actual paste
   waits 600ms; typing, IME, over-limit and draft restoration do not auto-submit.
   Preserve drafts by account, clear on save/discard/logout, and retain original
   request identity for uncertain retries. Delegate completion opens review
   without an extra optimization; nickname-only results are valid.
5. Verify backend, frontend, five-language admin and learner UI, four viewports
   (1440×900, 360×640, 390×844, 844×390), including Arabic RTL.

## Concrete Steps

Run targeted pytest under the existing Python runtime with worktree imports;
run focused Jest in `src/web`. Then run Ruff, type-check, ESLint, translation
checks, architecture checker, repository harness, dev tool checker, and full
lefthook pre-commit. Generate knowledge indexes after plan changes. Use real
browser shell checks with controlled API fixtures where live credentials or
deployment are unavailable; report fixture use explicitly.

## Validation and Acceptance

Config tests cover generation/reuse/failure, same public text, readonly fields,
concurrent saves including initial creation, JSON byte limits, env overrides,
and postcommit cache faults. Runtime tests cover partial/conflicting/missing
facts, nickname-only, unbound questions, ownership/expiry, failure rollback,
request replay/operation separation, and no profile writes before confirmation.
Frontend tests cover retained questions/input, paste timing/IME, account draft
isolation, exact retries and review/save behavior. Existing guided/manual tests
remain green; all new UI text appears in zh-CN/en-US/fr-FR/ar-SA/th-TH.

## Idempotence and Recovery

Failed generation never changes config. A stale generated result cannot replace
a newer save. Cache errors after a durable write are reported as committed with
refresh pending, never as rollback. Failed import preserves cursor/context and
paste text; exact retries replay terminal events without repeating the LLM.
No schema changes, migrations, library upgrades or shared config refactor.

## Interfaces and Dependencies

Add readonly `assistant_prompt` to saved config and session response. Add only
`POST /api/user/profile-onboarding/session/{session_id}/assistant-answers` with
`raw_text`, `expected_block_index`, `request_id`, returning existing SSE done
fields plus operation `delegate`. Existing `/complete` remains authoritative;
profile/nickname limits stay 1,000/64. No assistant-prompt endpoint/checkpoint.

Deployment order: backend first; an administrator saves existing MarkdownFlow
to generate the public prompt; frontend last. Target, permissions and separate
backend/frontend deployment support are not confirmed, so this task publishes
a PR only and must not merge main, rewrite dev or operate a production database.

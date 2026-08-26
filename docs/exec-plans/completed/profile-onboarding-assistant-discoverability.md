# Make AI-assisted onboarding visible before the first question

## Purpose / Big Picture

Expose the existing assistant path prominently above the question area as soon
as the session returns its public prompt, without waiting for MarkdownFlow to
produce an interaction. Keep the same session and confirmation/save contract.
Use the learner's first-person voice in compiled prompts and update examples.

## Progress

- [x] 2026-08-26 UTC: Read repository/subtree instructions, session and view
  contracts, compiler template and adjacent regression tests. Synchronize the
  clean feature branch to remote PR #2669 at `11a9408d3` after coordinator rebase.
- [x] 2026-08-26 UTC: Implement early prominent entry and independent copy/edit
  controls while ordinary question generation is in flight; preserve locking.
- [x] 2026-08-26 UTC: Update five locale examples and first-person compilation.
- [x] 2026-08-26 UTC: Verify regression tests, static checks and browser layouts.
  Follow-up publication and live CI/review results are tracked in PR #2669.

## Surprises & Discoveries

Local Turbopack hit a file-watcher limit; the temporary QA server used Webpack
with polling instead. Existing pinned Ruff was reused from `/tmp/pr3-tools/bin`
without altering the source checkout.

The entry previously required `awaiting_input`. The assistant view also used
one disabled flag for copying, editing, returning and submitting; simply
removing the entry condition would expose a disabled copy workflow.

## Decision Log

- Keep the frozen-prompt requirement: old sessions/configs without a prompt
  still use normal questions. Do not generate prompts on learner access.
- Let copying and editing proceed during ordinary generation; only processing
  waits for a stable cursor. Return must not close or restart the normal stream.
  Delegate-in-flight and uncertain outcomes retain existing safety restrictions.
- Reuse the current view/session/runtime from PR #2669. Original hunk provenance
  remains in `completed/profile-onboarding-ai-import.md`; no old modal/chooser
  code is restored and no new assistant endpoint is introduced.
- Template updates affect future generation. Preserve existing same-document
  prompt reuse and frozen sessions; do not silently rewrite a published config
  or add compiler-version/config migration machinery in this UX change.

## Outcomes & Retrospective

Implementation and local verification complete. Focused Jest: 7 suites / 100
passing tests, including early copying, return without stream interruption,
uncertain initial-run replay and no automatic submission when readiness changes.
Backend compiler/config pytest: 19 passed using MarkdownFlow 0.3.1. TypeScript,
ESLint (existing warnings), Ruff, translation presence/usage, architecture (zero
new violations), repository harness and dev-tool verification passed. Complete
lefthook results and post-push CI are reported on PR #2669.

Browser inspection used the real conversation, assistant view, official renderer
and shared Dialog in a temporary local fixture matching the dialog dimensions,
not a live authenticated backend or full course shell. Chinese and Arabic RTL
were checked at 1440x900, 360x640, 390x844 and 844x390. The entry is visible while
an initial run remains pending, copy succeeds, and editable pasted/typed text
survives returning. Switching from a real renderer to the assistant and back
preserves unsent input. All measured document widths match their viewport;
landscape uses the existing internally scrollable question area. Screenshots
and fixture source are retained in `/tmp/pr3-discoverability-*`; the temporary
Next.js route was removed and server stopped. The fixture's prompt is controlled
test data, not proof of live-model first-person compliance.

No deployment, live configuration save, schema change, model call, or dev/main
push is part of this follow-up. Previously generated prompts retain their text;
changing the saved research document triggers new compilation. Saving unchanged
content reuses the old prompt, so this template update alone does not refresh
existing production/dev config or sessions.

## Context and Orientation

`ProfileOnboardingConversation` owns entry placement; its session hook owns
operation state. `ProfileAssistantAnswersView` owns clipboard/paste controls.
Five `src/i18n/*/modules/profile-onboarding.json` files own visible copy.
`src/api/prompts/profile_onboarding_assistant_compiler.md` is loaded by the
existing shared provider wrapper on admin saves that require compilation.

## Plan of Work

Place an accented card before the preserved question renderer. Distinguish
ordinary generation from delegate processing at the session/view boundary.
Update localized guidance and examples in the requested order: ChatGPT, Claude,
WorkBuddy, Doubao, 千问工作, OpenClaw, Hermes Agent, etc. Specify first-person
questions and the exact Chinese opening, with equivalent voice for other source
languages. Extend existing tests, including delayed question SSE and retries.

## Concrete Steps

Run focused conversation/view/dialog Jest tests and compiler/config pytest.
Run TypeScript, ESLint, Ruff, translation/type generation checks, architecture,
repository harness, dev-tool verification and lefthook. Inspect actual rendered
UI at 1440x900, 360x640, 390x844 and 844x390, including Arabic RTL, with controlled
local data if live login is unavailable. Record fixture limitations explicitly.

## Validation and Acceptance

The prominent entry is available before any question event; copying works while
question generation continues. Returning retains the original stream/session.
No assistant import runs concurrently with a normal run; a failed/uncertain run
must be resolved using the existing replay contract. Draft restore never submits.
No-prompt and admin-preview cases still lack the entry. Examples match in five
locales. The provider receives first-person instructions and unchanged document.

## Idempotence and Recovery

Do not abort the question stream to switch views. Existing replay IDs, account
isolation and import failure preservation remain covered by regression tests.
Do not modify source checkout, other worktrees, dev or main while implementing.

## Interfaces and Dependencies

No backend API, database schema, dependency or final-save contract changes.
Only additive internal session/view props distinguish processing availability.
Existing published prompts require a new compilation to adopt the template;
unchanged-document saves continue reusing the saved result. Existing sessions
always keep their original prompt until a new collection is started.

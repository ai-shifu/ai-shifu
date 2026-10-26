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
- [x] 2026-08-26 UTC: Replace the assistant prompt card's separate copy header
  with a compact in-card action, preserving a clear accessible label and
  readable prompt width across narrow and RTL layouts.
- [x] 2026-08-26 UTC: Float copying at the prompt card's bottom corner, make the
  assistant workspace fill the dialog body, clarify the return/process actions,
  and visually elevate the fixed dialog footer above the collection surface.
- [x] 2026-08-26 UTC: Extend the full-body layout to the confirm-and-save view,
  letting the personal-introduction editor consume remaining height while the
  fixed optimization and footer actions retain their hierarchy.

## Surprises & Discoveries

Local Turbopack hit a file-watcher limit; the temporary QA server used Webpack
with polling instead. Existing pinned Ruff was reused from `/tmp/pr3-tools/bin`
without altering the source checkout.

The entry previously required `awaiting_input`. The assistant view also used
one disabled flag for copying, editing, returning and submitting; simply
removing the entry condition would expose a disabled copy workflow.

Keeping the full localized copy label in a side-by-side card was also too
expensive on narrow screens: the French label left only about 88 CSS pixels for
the prompt. A short visible action needs a separate full accessible name rather
than relying on one string for both jobs.

The first responsive workspace prototype let its grid shrink on phones. At
360x640 that collapsed the grid track to zero and visually overlapped its
children with the action row. Keeping the stacked mobile workspace at intrinsic
height, and enabling flexible equal columns only from the desktop breakpoint,
preserves one scroll owner and prevents the overlap.

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
- Remove the prompt card's dedicated header and use a two-column grid so the
  prompt remains independently scrollable. Show a localized short copy action,
  while retaining the existing full copy label as `aria-label` and hover text.
  Keep `dir="auto"` on the prompt content so its language, not the surrounding
  interface locale, determines text direction.
- On desktop, place the public prompt and pasted answer in equal columns that
  consume the remaining body height. Stack them at intrinsic height on phones
  and let the assistant section scroll. Anchor copying to the prompt card's
  logical bottom-end corner so RTL mirrors it. Use a muted body surface plus an
  opaque, shadowed footer to express the footer as the higher interaction layer.
- Make the confirm-and-save form a full-height flex workspace and assign its
  remaining height to the personal-introduction editor. Keep a minimum editor
  height so short mobile viewports scroll the existing body instead of
  collapsing the editor or overlapping the fixed footer.

## Outcomes & Retrospective

Implementation and local verification complete. Focused Jest: 7 suites / 100
passing tests, including early copying, return without stream interruption,
uncertain initial-run replay and no automatic submission when readiness changes.
Backend compiler/config pytest: 19 passed using MarkdownFlow 0.3.1. TypeScript,
ESLint (existing warnings), Ruff, translation presence/usage, architecture (zero
new violations), repository harness and dev-tool verification passed. Complete
lefthook passed. Full frontend regression: 177 suites / 1,511 tests passed.
Commit `cec4de44c` passed every remote check, including backend (7m00s), frontend
(1m44s), runtime harness (6m59s), formatting, static, CodeQL and security checks.
PR #2669 remains ready but BEHIND main, with no human approval or merge.

The natural CodeRabbit review on `cec4de44c` raised one minor documentation
privacy suggestion: remove the machine-specific path in the original ExecPlan
(thread `PRRT_kwDOMZ_AH86cZ3aG`). Replace it with an isolated-worktree description
and validate the repository harness in a separate documentation commit. The
repeated suggestions to relocate storage tests and extract the tested import
limit remain deferred as previously documented; no runtime behavior is broken.
Post-documentation CI and thread resolution are recorded on PR #2669.

The compact-card follow-up passes the 56 focused view/conversation tests and
the full frontend regression suite (178 suites / 1,558 tests), TypeScript,
focused and full ESLint (existing repository warnings only), translation
parity/usage, architecture boundaries and the repository harness. Browser QA
used the real dialog and assistant view at a 360-style narrow width plus Arabic
RTL: the prompt and action no longer overlap, the action follows logical RTL
placement, and the unified card is 114 CSS pixels high. The temporary QA route
and tabs were removed after inspection.

The body/footer redesign passes 95 focused dialog/conversation/assistant tests
and the full frontend regression suite (178 suites / 1,558 tests), TypeScript,
full ESLint (existing repository warnings only), translation parity/usage,
architecture boundaries and the repository harness. Controlled browser QA used
the actual Dialog and assistant view at desktop, 360x640 and 390x844 sizes plus
RTL. Desktop content fills the body without hiding either action; mobile content
stacks and scrolls without overlap or horizontal overflow; the copy action stays
at the prompt card's logical bottom-end. The temporary route, screenshots and
browser tabs were removed.

The confirm-and-save follow-up passes all 39 dialog tests and the full frontend
regression suite (178 suites / 1,558 tests), TypeScript, focused and full ESLint
(existing repository warnings only), architecture boundaries, the repository
harness, dev-tool verification and complete lefthook. Controlled browser QA
with the actual Dialog and save view measured a 394px-tall save workspace inside
a 442px desktop body; its personal introduction editor expanded to 160px instead
of leaving the lower body empty. At 390x844 the editor expanded to 228px with no
body or document overflow. At 360x640 the body alone gained 112px of scrollable
content, so the full form and optimization card remain reachable while the
127px fixed footer keeps its height. The temporary route, screenshots and
browser tab were removed.

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

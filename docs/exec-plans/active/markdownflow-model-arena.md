# MarkdownFlow model arena

## Purpose / Big Picture

Provide a command-line pipeline that snapshots authorized published course
prompts, generates the same frozen cases with four explicitly selected models,
renders complete images/PDFs, and publishes blind pairwise comparisons to Feishu
Base. Reviewers vote using native buttons; separate raw records retain distinct votes.

## Progress

- [x] 2026-09-08 UTC: Resume now reconciles remote matchup records and attachment
  names/counts even when local renders are unchanged. Missing artwork invalidates
  its voting window before repair; intact verified PDFs retain their window.

- [x] 2026-09-08 UTC: Moved the evaluator outside application code following the
  user's clarification; retained direct reuse of the production model and
  MarkdownFlow paths with process-local observation.
- [x] 2026-09-08 UTC: Passed 215 standalone tests and 108 unchanged production
  LLM tests, independent npm installation, renderer fixtures, and all ten locale
  cases. Verified no remaining diff in `src/api`, `src/web`, or `src/i18n`.

- [x] 2026-09-08 UTC: Inspected permissions, published structures, MarkdownFlow
  execution, rendering, and Feishu buttons/workflows; approved implementation.
- [x] 2026-09-08 UTC: Created the task branch and assigned independent source,
  execution, rendering, and Feishu implementation work.
- [x] 2026-09-08 UTC: Implemented and tested the private manifest, independent
  recovery stages, first-vote scoring, and command entry point.
- [x] 2026-09-08 UTC: Implemented published-only snapshots and isolated model
  execution; verified the shared LLM wrapper regression suite.
- [x] 2026-09-08 UTC: Implemented rendering and Feishu adapter, including real
  browser smoke fixtures and fail-closed content-clipping checks.
- [x] 2026-09-08 UTC: Generated eight real smoke outputs with all four exact
  provider routes and verified identical initial messages within each case.
- [x] 2026-09-08 UTC: Provisioned the dedicated Feishu Base with ordinary
  organization editing, four enabled button workflows, and verified bindings.
- [x] 2026-09-08 UTC: Published and verified the two-case smoke stage, then
  completed all 48 first-round generation attempts: 47 complete and one truncated.
- [x] 2026-09-08 UTC: Passed repository checks and opened a ready pull request;
  the initial integration head passed all CI checks.
- [x] 2026-09-08 UTC: Passed 318 backend and shared LLM regression tests after
  review fixes for private artifact identity, malformed records, rendering locale
  propagation, and coordinated renderer timeouts.
- [x] 2026-09-08 UTC: Completed first-round rendering and attachment recovery:
  45 complete works, 105 PNG pages, 105 PDF pages, and 63 published matchups.
- [x] 2026-09-08 UTC: Passed the final repository-wide gate, ten renderer unit
  tests, all renderer smoke fixtures, and ten real-browser locale checks against
  the current pinned UI library. Final CI and review state are tracked on the PR.
- [ ] Deferred by the user, 2026-09-08 UTC: Run the two-reviewer live voting trial
  and inspect the workspace's remaining workflow quota after delivery.

## Surprises & Discoveries

- Existing course export reads drafts, and preview execution caches context
  across model selections. Neither is the correct batch comparison boundary.
- Feishu workflow ButtonTrigger exposes the actual click user and record ID.
  System created_by on the resulting vote is not necessarily the reviewer.
- The installed Feishu CLI lacks the newer button-rule binding shortcut; the
  documented raw API remains callable through the existing authenticated CLI.
- Local dependency installations are older than the committed package pins.
- Production provider discovery contains all four requested versions. The
  course-facing allowlist contains only two; exact verified route overrides
  remain local to the evaluation process.
- Existing same-phone historical accounts require the exact canonical account
  selection used by phone login, never a union of their course permissions.
- Large published snapshots exceed reliable uncompressed kubectl stdout
  transport on this host; the worker protocol needs bounded gzip support.
- Feishu's live Base API accepts the documented Asia/Shanghai display timezone
  while rejecting UTC and Etc/UTC; raw vote timestamps are normalized to UTC.
- Real backend elements use `element_type`, while the UI library consumes
  `type`. Rendering must adapt that boundary explicitly and paginate scrollable
  slide content without flattening the model's layout or changing its scale.
- Native buttons become clickable before their attachments finish uploading.
  Count only votes after the complete matchup is ready, and retain its first
  ready time across an interrupted upload. Corrected visual revisions must
  refresh the existing record and begin a new ready window.
- Real course images can finish loading in nested slide documents while
  Playwright's page-level network-idle lifecycle remains pending. Renderer
  readiness must check actual requests and each frame's images, fonts, diagrams,
  and stable geometry. A hash-checked private image cache can preserve original
  source bytes when the renderer host cannot directly fetch course images.
- Workflow step titles are required by the live API even though the current
  skill schema labels them optional. Localized titles were added and the
  rejected creation was reconciled against an empty workflow listing.
- The initial granular ACL setup was rejected with `row quota limit` for record
  operations and `field quota limit` for column permissions. Table-level no-access
  rules succeeded. The exact quota cause was not established; this is not evidence
  that a paid upgrade is required. The user then explicitly chose organization-wide
  editing instead, so granular ACLs are no longer a provisioning prerequisite.

## Decision Log

- The user clarified that this is a manually invoked standalone tool, while
  still testing the main flow. Keep its entry point, dependencies, renderer,
  translations, and tests in `scripts/markdownflow-arena/`. Restore all application
  code and package manifests to their original state. Reuse the original
  `chat_llm`, MarkdownFlow context, prompt composition, element adapter, and UI
  components. Observe terminal chunks only inside the isolated worker, and
  restore temporary observers on success, failure, or cancellation.
- The private configuration identifies the requested owner by phone and binds
  the resolved user ID. Never commit the real phone, credentials, source
  prompts, course IDs, or Feishu resource links.
- Mirror the existing phone-login account selection, because legacy duplicate
  phone records can exist: `auth/providers/phone.py:PhoneAuthProvider.verify`
  calls `phone_flow.py:verify_phone_code`, then
  `user/repository.py:load_user_aggregate_by_identifier`. After normalizing
  the phone, the oldest active canonical user row wins; only when none exists
  does the oldest active phone credential select its active user. Never union
  same-phone account permissions, skip an orphaned first credential, or add
  new phone spellings/providers. Re-resolve this single account before each
  generation and retain `phone_login_canonical` only in private audit data.
- The requested models are gemini-3.8-flash,
  doubao-seed-2-1-turbo-260628, deepseek-v4-flash-0731, and qwen3.8-flash.
  Resolve exact configured route IDs; refuse missing or ambiguous matches.
- Twelve cases, one output per model, all six model pairs per case. Two cases
  form the initial end-to-end smoke stage. Fix inputs and A/B assignments.
- Organization members with the link may edit all three Base tables and click
  voting buttons. Disable advanced permissions on the dedicated run Base and
  use `permission_mode=organization_editable`. External anonymous access remains
  disabled. Source prompts and A/B-to-model mappings remain local; the shared
  statistics table exposes model aggregates without matchup identities.
- The first valid vote per reviewer and matchup counts; retain duplicates.
  Ties count as half a win; both-bad votes are a separate quality metric.
- Publication fingerprints the actual PNG revision. Re-rendering updates the
  existing matchup and replaces its generated attachments without changing A/B.
  Invalidate readiness during replacement, then move its timestamp forward only
  after both sides verify; votes from the old revision remain raw but do not score.
- The user explicitly requested delivery before human trial voting. Automated
  attachment, workflow, and sharing verification remains required; ordinary-user
  voting verification is a disclosed follow-up rather than a delivery blocker.

- The published-row snapshot needs independent consistent reads and exact version
  freezing. It reuses production models and permission normalization without
  invoking authoring cache writes or draft exports. The script is complementary
  coverage for reused runtime components, not a replacement for full app e2e.

## Outcomes & Retrospective

The twelve-case first round completed all 48 model attempts. One result was
truncated, and two introduced unavailable external images; these three works
remain separate failures and do not enter normal comparisons. The 45 usable
works produced 105 PNG pages and 105 PDF pages, all at width 1280, and 63
matchups. Every usable work's first and last page was inspected, and every PDF
page count matches its image count. The frozen batch used markdown-flow-ui
0.2.25 throughout; separate compatibility and locale checks passed against the
repository's current 0.2.26 pin. Completed model output was never regenerated
to recover rendering or publication.

After standalone extraction, 215 tool tests and 108 unchanged production LLM
tests passed. The model observer delegates to the original production wrapper
and is verified to restore its spies on completion, failure, and generator
close. Renderer unit tests,
pixel-checked scroll pagination, original-image cache fixtures, all supported
locales in reading/slide modes, and real clipping rejection fixtures passed.
Repository-wide lefthook, harness, and architecture-boundary checks passed.

Live provider calls used all four exact requested routes with identical initial
message hashes within each case. The Base has organization editing access,
external anonymous access disabled, and four enabled workflows with verified
button bindings. A network-interrupted PDF upload was reconciled using repeated
attachment queries and complete record history before its single missing file
was uploaded. Existing matchup IDs and A/B positions survive corrected renders.

Two-person live voting acceptance is explicitly deferred by the user, and quota
telemetry remains unknown. Existing web e2e tests ran:
the independent Live takeover test passed with installed Chromium; tests that
require the local app were blocked because its port was not serving. This is
not a claim that the full existing e2e suite passed.

## Context and Orientation

Published course structure logs identify exact course and outline row IDs.
The shifu service owns permission normalization and parent prompt inheritance.
MdflowContextV2 and PreviewElementRunAdapter provide the reusable execution
boundary, while chat_llm owns provider routing. markdown-flow-ui owns the
reading and slide rendering contracts.

## Plan of Work

Build snapshot/engine modules, the private pipeline and CLI, a local browser
renderer, and the Feishu adapter with narrow owned files. Use fake providers
and CLI fixtures for tests before exercising authorized production reads,
model calls, and a restricted Feishu smoke batch. Record real acceptance
evidence here without including source content or private identifiers.

## Concrete Steps

1. Create a private run directory and validate configuration and dependencies.
2. Resolve owner permissions and snapshot exact published rows consistently.
3. Freeze sampled inputs and resolve the four requested model route IDs.
4. Generate and render two cases, provision Base and workflows, verify access.
5. Resume remaining cases, publish pairings, and summarize returned votes.
6. Run focused tests, repository gates, and update this plan and user guide.
7. Commit and push the task branch, create a ready PR, and check live CI.

## Validation and Acceptance

Regression coverage must reject unauthorized and draft-only sources, preserve
published row consistency and inherited prompts, assert frozen input identity,
isolate model runs, exclude incomplete outputs, and resume without duplication.
Renderer smoke fixtures cover prose, diagrams, generated HTML, and every slide.
Feishu tests assert the click actor, fixed button outcomes, organization editing,
no private content in shared payloads, and first-vote counting. Live acceptance
requires ordinary-reviewer attachment/button checks and distinct reviewer votes;
owner-only access does not establish that acceptance.

## Idempotence and Recovery

Atomic owner-only JSON manifests retain source hashes, explicit model IDs,
artifacts, matchup assignments, remote IDs, and per-stage status. Hold a run
lock. Revalidate owner permissions when resuming, reuse successful artifacts,
and retry upload/statistics independently of paid generation. Unknown remote
write outcomes require resource reconciliation, not blind create retries.

## Interfaces and Dependencies

The Python entry point exposes run --config, run --resume, and summarize
--run-id. Source and engine functions exchange versioned JSON-compatible
case/artifact records. The renderer accepts --input and --output and returns
absolute page/PDF paths. The Feishu adapter uses safe subprocess argv and
existing user authentication. It creates no chat messages and never exports
the full source prompt to the shared Base.

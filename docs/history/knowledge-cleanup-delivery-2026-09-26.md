# Repository knowledge cleanup delivery — 2026-09-26

The approved documentation and collaboration-guidance cleanup is delivered as
focused ready pull requests. Application behavior, visible product copy and
stable identifiers are preserved. The `.env.example` is documentation; local
environment values and deployed configuration were not changed.

## Scope and results

- Installation/configuration: credited the existing #2963 corrections, clarified
  the two configuration endpoints and process ownership, removed inactive
  frontend Stripe examples, and documented worker/beat plus persisted-task
  acceptance. Real job execution remains an environment-specific acceptance.
- Engineering contracts: corrected remaining billing UTC defaults and read-side
  references; documented implemented dashboard routes, fields and scoped query
  behavior, including the Python source-status filtering exception.
- Session metrics: UTC calendar month; successful revoking users form disjoint
  single-only, bulk-only and both cohorts. Existing anonymous identity and event
  fields are preserved. The example requires both event kinds for the both group.
- Chat Skills: one shared ask-store owner, qualified optional scope guards,
  manual reading-mode audio versus the NewChatComp listen-mode backfill queue,
  and current desktop/mobile/TTS idle timers with actual test pointers.
- Navigation/instructions: credited README/i18n fixes already merged in #2952;
  locale scope uses `src/i18n/locales.json`. All 20 dedicated skills are indexed
  from metadata; the frontend router is scenario-based and module rules inherit
  shared guidance. Crash fallback labels have a local, component-only exception.
- Lifecycle: reviewed all 46 baseline active documents, not only the original
  40. Final disposition is 33 completed, 11 retained active, one product contract
  and one historical inventory. Timeline is a separate completed record.
- Knowledge layout: moved 16 flat topic documents, separated historical journals
  and durable analytics contracts, and replaced stale debt counts with explicit
  current investigations. The direct-commit UoW baseline is empty and enforced.
  The long Live and Ruff journals now live in history; active plans retain
  effective decisions, continuation steps and remaining acceptance.
- Validation: covers every tracked Markdown/MDX source, aliases, skill metadata
  and catalogs, local links/anchors, plan sections and pending archived work.
  Active plans without pending work trigger review only. Historical runtime
  references remain historical; their document navigation is still checked.
- Reporting: local/CI health reports carry UTC generation time and checkout HEAD
  and are ignored rather than permanent canonical snapshots. Unknown review
  dates remain blank. The gardening report records 23 stale or unknown review
  dates; this review debt was not hidden by refreshing timestamps.

## Ready pull requests

The branches form a dependency stack because indexes and moved paths overlap.
Review corrections now live in the PR that owns each issue. Merge in dependency
order; the skill-content PR explicitly describes its temporary manual catalog
until the separate generator PR enables automation.

| Delivery | PR | Base branch |
| --- | --- | --- |
| Total ExecPlan | [#2964](https://github.com/ai-shifu/ai-shifu/pull/2964) | `main` |
| clarify runtime configuration ownership | [#2965](https://github.com/ai-shifu/ai-shifu/pull/2965) | `sunner/knowledge-cleanup-plan` |
| align billing timestamps with the UTC contract | [#2966](https://github.com/ai-shifu/ai-shifu/pull/2966) | `sunner/runtime-config-guidance` |
| align dashboard guidance with current reports | [#2967](https://github.com/ai-shifu/ai-shifu/pull/2967) | `sunner/billing-utc-guidance` |
| define monthly session revocation user cohorts | [#2968](https://github.com/ai-shifu/ai-shifu/pull/2968) | `sunner/dashboard-contract-guidance` |
| align chat skills with current state and playback | [#2969](https://github.com/ai-shifu/ai-shifu/pull/2969) | `sunner/session-analytics-contract` |
| preserve unknown review dates | [#2981](https://github.com/ai-shifu/ai-shifu/pull/2981) | `sunner/chat-skill-contracts` |
| reconcile plan completion and remaining acceptance | [#2970](https://github.com/ai-shifu/ai-shifu/pull/2970) | `sunner/unknown-review-date-compatibility` |
| clarify skill navigation and local rule ownership | [#2971](https://github.com/ai-shifu/ai-shifu/pull/2971) | `sunner/plan-lifecycle-reconciliation` |
| organize topic documents under their owning categories | [#2972](https://github.com/ai-shifu/ai-shifu/pull/2972) | `sunner/skill-routing-ownership` |
| validate documentation discovery and lifecycle | [#2974](https://github.com/ai-shifu/ai-shifu/pull/2974) | `sunner/knowledge-topic-layout` |
| final delivery record | [#2980](https://github.com/ai-shifu/ai-shifu/pull/2980) | `sunner/documentation-harness-checks` |

Superseded follow-up PRs #2973 and #2975–#2979 are closed after their corrections
were incorporated into the owning PRs. They remain historical review evidence.
The reporting/closure PR links this final record and the completed total plan.
All implementation PRs are ready, not drafts; merge remains a separate step.

## Verification evidence

Each commit-sized delivery passed the development-tool doctor, repository
documentation validation and full `lefthook run pre-commit --all-files` gate.
Meaningful focused evidence (runs may overlap; do not sum them as unique cases):

| Area | Executed evidence |
| --- | --- |
| Runtime configuration | 2 suites, 6 tests |
| Dashboard UI | 4 suites, 22 tests |
| Session/device authorization | 2 suites, 27 tests |
| Ask store, active projection, AskBlock and chat hook | 4 suites, 124 tests |
| Reading projection helpers, listen candidates and concurrency utility | 3 suites, 50 tests; not component queue-orchestration coverage |
| Shared analytics delivery | 1 suite, 10 tests |
| Knowledge generator/validator | 22 regression fixtures |
| Existing instruction boundary checks | 28 fixtures |
| Focused skill metadata | 20 skills accepted by the skill validator |
| Determinism | Repeated generation has identical committed output; only ignored reports carry run time |
| Backend UoW | Empty outside-DAO baseline; ratchet passed |
| Architecture | Existing 131 baseline entries; no new or stale entries |

The review follow-up also corrected dashboard history semantics and pagination
coverage claims, documented unobservable analytics losses before identity is
ready, and distinguished implemented hydration guards from a stronger freshness
guarantee. The root instruction now preserves shared contract coordination for
all producers and consumers. Missing bootstrap, queue-orchestration, hydration,
and timer-reset/cleanup coverage is stated explicitly rather than counted as
existing tests. No application behavior or event payload was changed.

The tooling snapshot also passed an explicitly dispatched
[Static Checks run](https://github.com/ai-shifu/ai-shifu/actions/runs/36208576710).
The final PR description records final-head CI separately. An absent workflow
check is not reported as a successful workflow run.

Historical plan test results remain attributed to their original deliveries;
they were not represented as rerun tests. #2778, #2942 and #1889 acceptance/merge
and CI evidence was read independently before closing their remaining notes.

## Retained work and external acceptance

| Active plan | Concrete remaining work / dependency |
| --- | --- |
| [Course sharing](../exec-plans/active/course-sharing.md) | Physical iOS/Android acceptance. |
| [Brand/domain payments](../exec-plans/active/creator-brand-domain-payments.md) | Settlement-owner order/dashboard reporting and its feature verification; separate implementation. |
| [Email notification delivery](../exec-plans/active/credit-notification-email-delivery.md) | Dev-US migration/configuration and controlled SMTP delivery with saved result. |
| [Live capacity](../exec-plans/active/gemini-live-configurable-capacity.md) | Approved US configuration rollout, every worker and Redis limit verified. |
| [Live follow-up](../exec-plans/active/gemini-live-voice-follow-up.md) | Real provider, Redis/MySQL, controlled dev enablement and physical browser/audio matrix. |
| [Lesson rewind](../exec-plans/active/mdf2-agent-lesson-rewind.md) | Browser refresh acceptance currently lacks a visible onRefresh trigger; keep the coverage gap open. |
| [Account cancellation](../exec-plans/active/operator-user-account-cancellation.md) | Combined dev02 acceptance with an approved disposable account and saved lifecycle state. |
| [Payment attempts](../exec-plans/active/payment-attempt-lifecycle.md) | Real payment-provider smoke. |
| [Referral rewards](../exec-plans/active/referral-invitation-rewards.md) | Dev02 saved-row and product-configuration acceptance. |
| [Ruff minimization](../exec-plans/active/ruff-rule-minimization.md) | Fresh census, remaining dedicated rule work and final selection acceptance. |
| [Skill attribution](../exec-plans/active/skill-platform-attribution.md) | External Skills producer release and end-to-end acquisition-report acceptance. |

Unrelated optional follow-ups have destinations in the
[debt tracker](../exec-plans/tech-debt-tracker.md). The
[dated 46-document review](knowledge-review-2026-09-26.md) preserves per-plan
evidence. Those remaining tasks require their stated environments, feature
changes or product decisions; the documentation audit did not perform them.

Delivery record prepared at 2026-09-26T01:40:02Z against application baseline `43e13cdf5`.

Code-review corrections and the consolidated PR ledger were recorded at 2026-09-26T03:03:01Z.
Current-head CI and review state are recorded in #2980; the earlier run linked
above remains evidence for its original snapshot, not a claim about a later head.

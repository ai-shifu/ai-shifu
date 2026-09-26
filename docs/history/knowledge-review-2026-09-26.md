# Repository knowledge review — 2026-09-26

Audit baseline: `43e13cdf567d6d933d5a5b30de5d10a0027171e1`. Reviewed all 46 active documents present on that
main revision, including additions since the original 40-plan audit. The new
cleanup tracker is not part of that baseline. Also checked completed plans for
pending work and missing sections. This is a dated inventory, not live status.

Merge evidence comes from commits reachable from the baseline. Test evidence
in existing plans remains attributed to its original run; the audit did not
repeat all historical product tests. PR #2778 and #2942 merge/CI states were
also read live. Only completed original scope with recorded acceptance is
archived; ambiguous or external acceptance remains active.

| Document | Disposition | Evidence, dependency or remaining work |
| --- | --- | --- |
| `account-session-analytics` | product specification | Moved in #2968; user-approved monthly cohorts and existing anonymous identity. |
| `admin-home-onboarding` | completed | [#2823](https://github.com/ai-shifu/ai-shifu/pull/2823) (`30e2fc2ec`); Original onboarding shipped; the obsolete home entry was retired. Shared-course editor permission affordances and French copy polish are optional follow-ups in the debt tracker. |
| `agent-first-harness-phase-2` | completed | Recorded implementation/acceptance in plan at `62792ad38`; source and adjacent test locations checked.; The recorded local dev-stack, browser smoke, correlation and runtime-harness acceptance is complete. Asset existence alone was not used as acceptance. |
| `backend-inventory-2026-07` | history | July 2026 point-in-time inventory. Counts are historical, not current debt. See the current debt tracker and completed overhaul/UoW plans. |
| `backend-overhaul-master` | completed | [#2132](https://github.com/ai-shifu/ai-shifu/pull/2132) (`0d9ed3618`), [#2133](https://github.com/ai-shifu/ai-shifu/pull/2133) (`578fe97bd`); Phase 2 shipped with recorded full-suite and live dev smoke evidence. Later direct-commit cleanup is complete; remaining provider-transaction, legacy-query and production-consumer investigations are in the debt tracker. |
| `billing-credit-notifications` | completed | [#2738](https://github.com/ai-shifu/ai-shifu/pull/2738) (`96c00194e`), [#2741](https://github.com/ai-shifu/ai-shifu/pull/2741) (`c3c6253e2`); SMS rules, templates, operator management and focused acceptance are delivered. Real email delivery belongs to the separate active email plan. |
| `billing-timezone-cleanup` | history | Unverified historical checklist and runbook, not proof of completed UTC acceptance. Old machine-local commands are historical; current guidance is the engineering baseline. Do not continue instructions from this snapshot. |
| `ci-backend-speed-stack` | completed | [#2536](https://github.com/ai-shifu/ai-shifu/pull/2536) (`7808566b6`), [#2537](https://github.com/ai-shifu/ai-shifu/pull/2537) (`04d00c90d`), [#2538](https://github.com/ai-shifu/ai-shifu/pull/2538) (`48e88ce44`), [#2597](https://github.com/ai-shifu/ai-shifu/pull/2597) (`f645e9c49`); The later recorded cold-cache and cache-hit CI runs supersede the early local Docker limitation. |
| `course-price-market-rules-and-free-unlock` | completed | [#2794](https://github.com/ai-shifu/ai-shifu/pull/2794) (`8bfa696be`), [#2795](https://github.com/ai-shifu/ai-shifu/pull/2795) (`570af4626`); The recorded market-price and free-unlock regression checks cover the original scope. |
| `course-sharing` | active | Awaiting physical iOS/Android acceptance; keep the original device matrix open. |
| `creator-brand-domain-payments` | active | Implementation is present, but complete cross-surface verification and the intended operator reporting boundary need reconciliation. Historical TypeScript failures are not proof of a current failure. |
| `creator-dashboard-course-ownership-optimization` | completed | [#1792](https://github.com/ai-shifu/ai-shifu/pull/1792) (`bc4eedf8b`); The owned-course filtering implementation and recorded ownership regression coverage are delivered. |
| `creator-dashboard-course-ratings` | completed | [#1792](https://github.com/ai-shifu/ai-shifu/pull/1792) (`bc4eedf8b`); The ratings report and its recorded focused coverage are delivered. |
| `creator-dashboard-learners-sql-optimization` | completed | [#1792](https://github.com/ai-shifu/ai-shifu/pull/1792) (`bc4eedf8b`); The scoped, paginated learner aggregation and recorded query tests are delivered. |
| `creator-dashboard-ratings-sql-optimization` | completed | [#1792](https://github.com/ai-shifu/ai-shifu/pull/1792) (`bc4eedf8b`); The scoped ratings aggregation and recorded query tests are delivered. |
| `creator-dashboard-request-splitting` | completed | [#1792](https://github.com/ai-shifu/ai-shifu/pull/1792) (`bc4eedf8b`); The independent report requests and recorded frontend/backend checks are delivered. |
| `credit-notification-email-delivery` | active | Awaiting migration/configuration and a controlled dev-US SMTP delivery with saved notification result; local tests do not prove delivery. |
| `device-auth-skill-analytics` | completed | [#2934](https://github.com/ai-shifu/ai-shifu/pull/2934) (`9bc9c1656`); Browser device-authorization attribution and recorded producer tests are delivered. The durable contract is in product specifications. |
| `gemini-live-configurable-capacity` | active | API merge is complete; US configuration rollout and verification of every worker/Redis limit remain external acceptance. |
| `gemini-live-voice-follow-up` | active | Local implementation is merged; real Gemini, physical browser/audio, Redis/MySQL integration and controlled dev enablement remain unverified. |
| `gemini-tts` | completed | [#2751](https://github.com/ai-shifu/ai-shifu/pull/2751) (`8ce8c68a6`); The plan records both focused tests and credentialed US/China provider smoke for its original scope. |
| `generated-slide-timeline` | completed | [#2778](https://github.com/ai-shifu/ai-shifu/pull/2778) (`b061be121`); CI readback and recorded 68/102-case acceptance. |
| `idempotent-payment-sync` | completed | [#2857](https://github.com/ai-shifu/ai-shifu/pull/2857) (`56e1e884b`); The recorded 72 focused and 187 order tests cover retry-safe payment side effects; no new provider rollout is claimed. |
| `learner-listen-playback-stability` | completed | [#2775](https://github.com/ai-shifu/ai-shifu/pull/2775) (`c0ff2eb08`); Checkpoint stability has recorded multi-stream and mode-round-trip acceptance. Timeline delivery is tracked separately; durable behavior and analytics moved to a product specification. |
| `lobster-course-entry-analytics` | completed | [#2816](https://github.com/ai-shifu/ai-shifu/pull/2816) (`9ad3a71e6`), [#2819](https://github.com/ai-shifu/ai-shifu/pull/2819) (`47f4da8c7`); Entry attribution and recorded event tests are delivered. Full generation/import attribution is a separate deferred proposal in the debt tracker. |
| `markdownflow-model-arena` | completed | [#2784](https://github.com/ai-shifu/ai-shifu/pull/2784) (`489391de5`); Recorded browser acceptance and focused backend/frontend checks complete the model-comparison scope. |
| `mdf2-agent-lesson-carries-on` | completed | [#2953](https://github.com/ai-shifu/ai-shifu/pull/2953) (`d5ba0d03e`); Recorded deterministic and live continuation simulations complete the approved scope; no engine implementation is changed by this audit. |
| `mdf2-agent-lesson-rewind` | active | The backend/frontend change is merged; the planned browser refresh acceptance lacks a visible onRefresh trigger. Retain the acceptance gap explicitly. |
| `notification-channel-foundation` | completed | [#2746](https://github.com/ai-shifu/ai-shifu/pull/2746) (`c1d676a94`), [#2749](https://github.com/ai-shifu/ai-shifu/pull/2749) (`75a105e5d`); The shared channel foundation shipped. The former email placeholder has since been implemented; controlled SMTP acceptance remains in the active email-delivery plan. |
| `numbered-course-models` | completed | [#2840](https://github.com/ai-shifu/ai-shifu/pull/2840) (`c0dead163`), [#2853](https://github.com/ai-shifu/ai-shifu/pull/2853) (`260b919b6`), [#2941](https://github.com/ai-shifu/ai-shifu/pull/2941) (`02e5b34cc`); Numbered choices, compatibility and later default-setting corrections are delivered with recorded focused regression evidence. |
| `observability-artifacts-consistency-frontend-trace` | completed | Recorded implementation/acceptance in plan at `724ed0818`; source and adjacent test locations checked.; The plan records focused tests and a read-only runtime probe for artifact consistency and frontend trace linkage. Business-data repairs were outside its scope. |
| `official-client-model-gateway` | completed | [#2771](https://github.com/ai-shifu/ai-shifu/pull/2771) (`0d333a642`); The official-client gateway shipped with recorded 48 focused gateway cases and the full backend gate. |
| `onboarding-existing-creator-rollout` | completed | [#1933](https://github.com/ai-shifu/ai-shifu/pull/1933) (`ac23e4dc9`), [#2823](https://github.com/ai-shifu/ai-shifu/pull/2823) (`30e2fc2ec`); The existing-account rollout shipped; later retirement of the home entry supersedes that part of the old UI while editor behavior remains. |
| `operator-credit-grant-package` | completed | [#1764](https://github.com/ai-shifu/ai-shifu/pull/1764) (`29181a1e0`); The operator grant package and recorded regression checks complete the original scope. |
| `operator-promotion-ops-state-rules` | completed | [#1937](https://github.com/ai-shifu/ai-shifu/pull/1937) (`999fcb855`); State-rule changes and focused checks shipped. The old note about unrelated working-tree changes is historical, not current delivery scope. |
| `operator-user-account-cancellation` | active | Backend and frontend PRs are merged; combined dev02 acceptance remains unperformed and includes destructive account operations. |
| `operator-user-contact-change` | completed | [#2948](https://github.com/ai-shifu/ai-shifu/pull/2948) (`a0b1e3d0e`); Contact-change workflow and recorded focused tests are delivered. |
| `package-campaigns` | active | The V1 change merged in #1889. Reconcile original pricing/grant acceptance evidence before closure; order reuse and preorder-renewal pricing are separate business-rule follow-ups. |
| `password-login-rate-limit` | completed | [#2897](https://github.com/ai-shifu/ai-shifu/pull/2897) (`8be7b6536`); The recorded real-Redis concurrent acceptance completes the password limiter. A broader IP-policy follow-up is tracked separately. |
| `payment-attempt-lifecycle` | active | Awaiting real payment-provider smoke; mocked or local database tests do not prove external provider behavior. |
| `pydantic-required-compatibility` | completed | [#2912](https://github.com/ai-shifu/ai-shifu/pull/2912) (`38dcfafbf`), [#2913](https://github.com/ai-shifu/ai-shifu/pull/2913) (`d6141f1ca`); The removed legacy constructs, AST guard and recorded regression/CI verification complete compatibility cleanup. |
| `referral-invitation-rewards` | active | Awaiting dev02 saved-row and product-configuration acceptance; do not infer it from merged implementation. |
| `rename-cook-web-directory` | active | Implementation and verification are complete. Archival is deferred to the validation-tool batch because its exact historical-path allowlist currently names the active path. |
| `ruff-rule-minimization` | active | Merged rule units are reconciled below; a fresh census and final rule-selection acceptance still remain. No new lint policy change is part of this audit. |
| `skill-platform-attribution` | active | Backend #2916 and browser #2934 are merged. The separate Skills producer delivery and end-to-end acquisition report remain external dependencies. |
| `spanish-es-es-localization` | completed | [#2942](https://github.com/ai-shifu/ai-shifu/pull/2942) (`7791a434c`); PR checks were re-read on 2026-09-26: executed checks succeeded, security-review checks were neutral, and the PR is merged. Native Spanish uses the released library; old dev-pin blockers are historical. |
| `stripe-payment-sync-security` | completed | [#2854](https://github.com/ai-shifu/ai-shifu/pull/2854) (`a2888f662`); The recorded 49 focused and 189 order tests cover provider-evidence ownership and fail-closed synchronization. |
| `trusted-client-ip` | completed | [#2896](https://github.com/ai-shifu/ai-shifu/pull/2896) (`a1173269f`); Trusted-proxy resolution and recorded focused request-chain tests shipped. Earlier permission/publish notes are historical. |

## Review limits

The directory rename plan is ready for archival but remains active until the
checker allowlist changes in the separate tooling PR. Package campaign and
brand/domain plans remain open for evidence/scope reconciliation. No external
environment was mutated or acceptance silently marked complete by this review.
No review date was inferred from file modification time or bulk regeneration.

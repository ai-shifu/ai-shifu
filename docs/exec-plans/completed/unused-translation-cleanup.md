# Unused Translation Cleanup

## Purpose / Big Picture

Remove retired shared translations and make the usage checker detect them
without treating generated TypeScript declarations as runtime references.
Preserve current UI text, backend compatibility aliases, dynamic key families,
and product names supplied by billing data.

## Progress

- [x] 2026-09-27 UTC: Audited translation references and identified 73 retired
  frontend keys plus additional candidates requiring dynamic-reference review.
- [x] 2026-09-27 UTC: Fetched remote main and created
  `sunner/cleanup-unused-translations` from `a1af71a01`.
- [x] 2026-09-27 UTC: Repaired usage detection and added nine focused fixture
  tests, including missing-key rejection and runtime alias compatibility.
- [x] 2026-09-27 UTC: Verified and removed 369 unused keys in all seven locales,
  removed two empty frontend namespaces, and regenerated metadata and declarations.
- [x] 2026-09-27 UTC: Translation parity/usage, nine checker tests, frontend type
  checking, and focused UI tests pass with lockfile-installed dependencies.
- [x] 2026-09-27 UTC: Passed 37 frontend suites / 532 tests, nine checker tests,
  40 knowledge-index tests, frontend type checking, repository harness,
  architecture validation, strict tooling checks, and the all-files pre-commit gate.
- [x] 2026-09-27 UTC: Addressed PR #2989 review by restricting relative key
  detection to translator arguments and forwarded literal-union contracts.
  Added five regressions and removed 12 newly exposed unused keys in all locales.
- [x] 2026-09-27 UTC: Restored the registered `server.order.orderHasPaid`
  message in all locales and added error-registry coverage to the usage checker.

## Surprises & Discoveries

- Generated `i18n-keys.d.ts` contains every defined key and is scanned as an
  ordinary TypeScript file, masking unused translations.
- Dynamic templates, namespaced translator props, backend key constants, and
  legacy `module.backend` aliases need to remain recognized.
- The old `update_i18n.py --prune-unused` helper does not reliably prune the
  whole inventory; use an explicit reviewed deletion set instead.
- The default local toolchain has Ruff 0.16.9 instead of pinned 0.16.5 and lacks
  markdown-it-py 4.0.0. Prepare an isolated temporary tool environment for checks.
- Whole-string token matching can swallow key constants after apostrophes in
  comments or inside nested templates. Match key-shaped literals independently.
- The additional candidates belong to retired notification-template/type
  editors, old promotion summaries/advanced controls, superseded billing copy,
  old onboarding views, and other unused UI labels. Five backend messages have
  no remaining literal, dynamic, alias, or producer references. Current delivery
  status/error families, billing product-name families, and `server.profile.sex*`
  remain intact.
- Preserve the empty `server.outline` namespace because its backend producers
  still use compatibility aliases; removing its sole unused label must not
  remove missing-key validation coverage for that active domain.
- The borrowed source-checkout dependencies lacked intl-messageformat and used
  a stale MarkdownFlow type surface. Replaced only this worktree's symlink with
  an ignored local `npm ci --ignore-scripts` install; source-checkout dependencies
  and the committed lockfile remain unchanged.

## Decision Log

- Repair detection before pruning. A static candidate is not sufficient
  evidence for deleting a dynamic or persisted translation contract.
- Keep this change focused on unused translation inventory and its enforcement.
  Do not change runtime UI behavior, analytics, database records, or TTS metadata.
- Preserve dynamically matched key families conservatively. Do not introduce
  an unused-key allowlist to make CI pass.

## Outcomes & Retrospective

Removed 380 unique keys (2,660 localized values) and two retired frontend
namespaces. All remaining translation values are identical to the base commit.
The repaired checker and its CI regressions preserve dynamic, relative, and
aliased consumers and report no missing or unused keys without allowlists.
All local acceptance checks pass. The default static-checks workflow also runs
the checker regressions before enforcing translation usage. Delivery uses a
ready pull request; merge and deployment are outside this task's scope.

## Context and Orientation

Canonical JSON lives in `src/i18n/<locale>/`. Usage validation is
`scripts/check_translation_usage.py`; parity validation is
`scripts/check_translations.py`. `scripts/generate_languages.py` maintains
locale namespaces and `scripts/generate_i18n_keys.js` maintains
`src/web/src/types/i18n-keys.d.ts`. CI and lefthook run the usage checker with
`--fail-on-unused`. See `docs/references/i18n.md` for the shared contract.

## Plan of Work

Exclude declaration/test files from runtime reference detection. Recognize
complete key literals, namespaced relative references, dynamic templates,
backend constants, and aliases. Cover those cases with temporary-fixture unit
tests. Review the resulting unused set against production call sites and
runtime configuration producers, prune only that set across all locales, and
regenerate metadata and declarations.

## Concrete Steps

Run the checker and its focused tests after each detection change. Inspect
candidate groups with repository searches before deleting them. Run both
generators twice to confirm deterministic output, then the checks below.

## Validation and Acceptance

- Generated declarations alone never make a translation used.
- Genuine full, relative, dynamic, backend, and aliased references survive.
- The missing-key check still fails for a missing literal translation.
- All locales have identical key inventories; usage validation reports no
  missing or unused keys without allowlists.
- Frontend type checking and relevant existing UI tests pass.
- Repository harness and the required all-files pre-commit gate pass.

## Idempotence and Recovery

Generators and deletion are deterministic. Reverting the final commit restores
translations, namespaces, declarations, and the checker together. No external
runtime configuration or production state is modified.

## Interfaces and Dependencies

Keep existing CLI flags and success/failure semantics. Use the Python standard
library for checker and test code. Shared translation aliases remain compatible
with backend and frontend consumers.

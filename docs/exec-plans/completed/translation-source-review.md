# Review product translations against the Chinese source

## Purpose / Big Picture

Review the six non-Chinese product locales against `zh-CN`, correcting semantic
drift, incomplete instructions, inconsistent role terminology, and untranslated
product labels. Preserve Chinese copy, keys, ICU arguments, technical IDs,
links, and MarkdownFlow interaction syntax.

## Progress

- [x] 2026-09-27 03:20 UTC: Read repository guidance, refreshed the remote base,
  and inventoried 58 files and 4,271 messages per locale.
- [x] 2026-09-27 03:20 UTC: Baseline file/key/placeholder parity passes.
- [x] 2026-09-27 03:20 UTC: Reviewed learner, authoring, billing, operations,
  and backend messages, with production call-site checks for ambiguous copy.
- [x] 2026-09-27 03:20 UTC: Corrected 329 target values and reviewed the diff.
- [x] 2026-09-27 03:20 UTC: Translation parity/usage, metadata freshness,
  backend tests (27), frontend tests (20), ICU parsing/formatting (329 messages),
  and eight referral singular/plural runtime renders pass.
- [x] 2026-09-27 03:21 UTC: Tooling doctor and repository all-files verification
  pass; the refreshed remote main has no additional commits to audit.

## Surprises & Discoveries

- Structural parity passes even when a translation changes a metric's time
  window or retains English-only labels.
- The initial tooling doctor reports missing pinned Ruff and markdown-it-py.
  Installed the pinned tools into a temporary isolated virtual environment;
  the tooling doctor now passes without changing repository dependencies.
- The shared local frontend `node_modules` is missing `intl-messageformat`.
  Installed its locked version (10.7.18) into a temporary directory and supplied
  that directory to Jest and the runtime smoke script. The relevant tests pass.
- The French decimal example `1,5` is valid: `normalizeMultiplierInput` explicitly
  accepts commas, and its adjacent tests cover that input.

## Decision Log

- Chinese values and production call sites determine meaning. Technical brands
  and deliberately localized product names are not automatically mistranslations.
- This is a copy correction task: no new locale, analytics, runtime feature,
  dependency release, saved-content backfill, or legal translation is included.
- Review uses complete inventory screening for parity, numeric/markup drift,
  English residue, and terminology, plus contextual semantic review by surface.
  Automated screening alone is not linguistic certification.

## Outcomes & Retrospective

Corrected 329 values: English 59, French 127, Spanish 24, German 81, Arabic 11,
and Thai 27. Chinese source files, locale metadata, keys, argument names,
rich-text tags, and URLs are unchanged.

Material corrections include:

- Restored account cancellation consequences: identity/login removal, zeroed
  credits, ended sessions, and retention of historical business/course data.
- Restored billing and error recovery instructions, annual validity start dates,
  subscription auto-renewal meaning, and Stripe sync-success prerequisites.
- Corrected German debug/production labels and backend variable errors, French
  redemption-code and teacher terminology, and Thai personal-introduction terms.
- Restored the full course-prompt authoring guidance and accurate preview actions.
- Aligned consumption multiplier labels and notification units/populations with
  Chinese, and preserved the seven-day window in usage-attention reports.
- Added English/German referral month plural forms using existing arguments.

The inventory screening covers all 58 JSON files and 4,271 values per locale;
semantic review prioritizes the listed product surfaces and confirmed drift.
This is not a claim that every existing phrase has received native-speaker
certification. No authored or persisted content was rewritten.

Repository all-files checks passed, including JSON formatting, translation
contracts and usage, architecture boundaries, documentation harness, Python
checks, and frontend formatting/lint. Existing frontend lint warnings remain;
no unrelated files were changed by the gate.

## Context and Orientation

Shared JSON under `src/i18n` serves both the Flask backend and Next.js frontend.
`docs/references/i18n.md` owns the delivery checklist. Available target locales
are `en-US`, `fr-FR`, `es-ES`, `de-DE`, `ar-SA`, and `th-TH`.

## Plan of Work

Inventory and compare messages with Chinese, prioritize financial/permission
meaning and user instructions, inspect call sites where wording is ambiguous,
then edit only confirmed incorrect values. Record material examples and run
the existing translation validators and ICU regression suites.

## Concrete Steps

1. Refresh `origin/main` and create `sunner/review-translations-from-chinese`.
2. Compare locale JSON by namespace and inspect affected production usage.
3. Correct target values while preserving the source and message contracts.
4. Run translation parity/usage, metadata freshness, diff hygiene, and relevant
   formatting checks. Follow the tooling doctor and all-files gate if committing.

## Validation and Acceptance

All files and keys retain parity; arguments and rich-text/interaction syntax
remain valid. Chinese source files are unchanged. Corrected messages preserve
Chinese action, scope, units, and recovery instructions. Existing ICU plural
tests pass, and repository documentation harness passes after plan changes.

## Idempotence and Recovery

All changes are version-controlled text on an isolated task branch. Re-review
the diff without touching saved courses or live configuration. Reverting the
task's JSON hunks restores previous behavior.

## Interfaces and Dependencies

No key, API, runtime dependency, or consumer interface changes are planned.
Existing translation validators and i18next-ICU tests remain authoritative for
structural and formatting compatibility.

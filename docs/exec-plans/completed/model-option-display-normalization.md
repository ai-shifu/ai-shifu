# Centralize model option display normalization

## Purpose / Big Picture

LLM and TTS model selectors duplicate conversion of credit multipliers, badge
labels, and default flags. Give that display contract one owner in shared libs.

## Progress

- [x] 2026-09-20 01:15 UTC: Audited both normalizers and their consumers.
- [x] 2026-09-20 01:15 UTC: Moved the pure LLM normalizer from store to lib and
  reused shared metadata conversion from TTS options.
- [x] 2026-09-20 01:15 UTC: Independent branch validation passed: 59 focused
  tests, TypeScript, lint, architecture, repository harness, and all-file hooks.

## Surprises & Discoveries

LLM string entries intentionally have no metadata defaults. LLM deduplicates
values, while TTS retains duplicates. Follow-up options use different multiplier
semantics and are outside this change.

## Decision Log

- Extract only the common display metadata, after domain eligibility guards.
- Preserve nullish alias priority, numeric coercion, positive rounding, label
  trimming, default flags, and each domain's existing labels and identifiers.
- Update all imports when moving the pure helper out of the store layer.
- Preserve behavior; no new interaction or analytics event is introduced.

## Outcomes & Retrospective

One shared helper now owns model display metadata. All 59 focused tests and
repository checks pass on the independent branch using locked dependencies and
Node 22.16.0. Existing domain differences remain explicit and covered.

## Context and Orientation

`src/web/src/lib/modelOptions.ts` owns shared display normalization. The course
provider and operations page use its LLM adapter; `tts-model-options.ts` keeps
provider/model-specific adaptation while reusing the same metadata rules.

## Plan of Work

Move the normalizer and tests, extract the common fields, update both callers,
and add contract tests around alias precedence and domain differences.

## Concrete Steps

Run modelOptions, tts-model-options, ModelList, useShifu, and operations-page
Jest tests; TypeScript; lint; architecture and repository checks; all-file hooks.

## Validation and Acceptance

Legacy string options, labels, default selection, invalid multiplier handling,
LLM first-value deduplication, and TTS duplicate retention remain unchanged.

## Idempotence and Recovery

No data, dependencies, or configuration change. Revert this standalone PR to
restore the previous helper location and duplicate conversion blocks.

## Interfaces and Dependencies

The exported LLM adapter's input and output remain compatible. Its imports move
from store to lib; TTS shares only the metadata helper, not the LLM adapter.

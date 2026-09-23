---
title: Calibrated course completion credit estimate
status: active
owner_surface: shared
last_reviewed: 2026-09-23
canonical: false
---

# Calibrated course completion credit estimate

## Purpose / Big Picture

Estimate the credits for one learner to complete every visible lesson in reading mode, including normal interactions and follow-up questions. The course's authored text and structure are the inputs; a separate, validated historical calibration supplies the coefficients. Show median expected usage and an 80th-percentile preparation amount only when that calibration is trustworthy.

## Progress

- [x] 2026-09-23 08:04 CST: Inspected the existing operator estimate, billing settlement, learning contexts, and published completion benchmark.
- [x] 2026-09-23 08:32 CST: Added engine-aware feature extraction, strict historical sample screening, and gated P50/P80 calibration.
- [x] 2026-09-23 08:32 CST: Added a separate standard-1x completion estimate object to the operator detail response, with null values until calibration qualifies.
- [x] 2026-09-23 08:36 CST: Passed focused and service-wide tests, repository harness, architecture boundary, and frontend type checks. No authoritative ten-course training set is available locally, so calibration remains pending.

## Surprises & Discoveries

- The existing operator estimate counts one model call per lesson, omits follow-up questions and repeated history, and uses uncalibrated output ratios. It must not be presented as the new full-completion prediction.
- A documented reading-mode completion used 25.24 credits across 20 lessons and 51 calls, but the checked-in evidence does not contain matching authored character counts.
- A 1x model label is an output-rate reference. This estimate explicitly normalizes all three token categories to 0.000066667 credits per token.
- The active engine may be selected by deployment allowlist, so a published row's engine field alone cannot prove the historical runtime.
- The detail page favors an unpublished draft even when a published course exists. The new estimate must instead read the exact version in the runtime's published structure and prune hidden subtrees.
- The local development database has too few completed learning records to pass the ten-course, 100-completion release gate. A validated coefficient artifact cannot be produced from it.

## Decision Log

- Keep the current model-specific read/listen/classroom cost range and UI contract unchanged. Add a separate 1x, reading-only completion estimate to the operator detail response. The user-approved plan excludes a page change.
- Fit a nonnegative course-level quantile model per engine and language. Historical completions are grouped by course for training and validation; never sum lesson-level percentiles.
- Do not publish coefficients or numeric predictions until the historical sample and validation gates pass. Uncalibrated and out-of-range courses receive null values with an explicit status.
- Store only aggregate character counts, token counts, engine/language identifiers, course grouping IDs, and validation metrics in calibration artifacts. Do not export raw prompts, generated text, learner identity, or credentials.
- Fit the pinball objective with an offline linear-programming solver; the request path loads only coefficients and has no SciPy dependency. A solver failure prevents artifact installation.

## Outcomes & Retrospective

The estimation API and offline calibration workflow are implemented. No coefficients were published: local records cannot meet the sample threshold, and the previously documented 25.24-credit case lacks the matching historical authored text. The response is explicitly uncalibrated until a complete private export passes the evidence and held-out validation gates. A later data run can install the versioned artifact without changing billing or the operator page.

## Context and Orientation

- Operator detail assembler: `src/api/flaskr/service/shifu/admin_operations/courses_detail.py`.
- Existing approximation: `src/api/flaskr/service/shifu/admin_operations/courses_credit_estimate.py`.
- DTO: `src/api/flaskr/service/shifu/admin_dtos_courses.py`.
- Per-request settlement: `src/api/flaskr/service/billing/charges.py`.
- Historical completion methodology: `docs/product-specs/billing-learning-hours-estimate.md`.

## Plan of Work

Extract features from the effective authored lesson state. Validate historical completion and metering linkage against the corresponding published snapshot and actual runtime. Reprice successful production LLM requests at the standard reference rate. Fit separate P50/P80 course-level models, validate against held-out courses, and install a versioned artifact only when every release gate passes. Return a status and null values otherwise.

## Concrete Steps

1. Implement engine-aware feature extraction and exact standard-rate repricing.
2. Build a sanitized sample import/calibration command with documented exclusion rules and course-grouped validation.
3. Add a versioned artifact loader and an operator DTO field for predictions/status.
4. Exercise extraction, settlement, release gates, null fallback, and route serialization with focused tests.

## Validation and Acceptance

- Inputs count Unicode characters per visible leaf lesson, resolve inherited prompts, and differentiate generation from static display and interactions according to the runtime.
- Cached input is a subset of input. Repricing rounds each request metric half-up to 0.01 credits before summing requests.
- A calibration group has at least ten distinct courses and 100 full completions; held-out P50 WAPE <=30% and P80 coverage is 75%-85%.
- The result contains expected credits, preparation credits, calibration status, and version. Invalid, absent, insufficient, or out-of-range artifacts yield no numeric claim.
- Existing billing settlement and web page remain unchanged.

## Idempotence and Recovery

Feature extraction and prediction are read-only. Calibration writes a separate versioned JSON artifact only after validation; removing it returns the API to the explicit uncalibrated state. No migration or billing config change is required.

## Interfaces and Dependencies

The operator course-detail response gains a separate completion estimate object. Runtime inference uses the Python standard library. Offline calibration accepts only screened, aggregate records; any data-source access is read-only and never part of the request path.

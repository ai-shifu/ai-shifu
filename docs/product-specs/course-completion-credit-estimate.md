---
title: Standard-1x full-course reading credit estimate
status: implemented-pending-calibration
owner_surface: shared
last_reviewed: 2026-09-23
canonical: true
---

# Standard-1x full-course reading credit estimate

## Contract

The operator course-detail response includes `completion_credit_estimate`, a separate estimate for one learner completing every visible leaf lesson in reading mode, including normal exercise turns and follow-up questions. `estimated_credits` is the predicted course-level median (P50), and `recommended_credits` is the course-level P80. The result also includes `status` (`calibrated` or `uncalibrated`) and the calibration `version`. Unavailable predictions have null values. Existing model-specific read/listen/classroom ranges and billing settlement retain their distinct meanings.

The estimate standardizes uncached input, cached input, and output to **0.000066667 credits/token** (0.066667 credits per 1,000 tokens). This is the documented reference case, not a guarantee that every model displaying 1x has equal input and cache rates. Per request, subtract cached input from total input and round each of the three credit components half-up to 0.01 before summing requests. The preparation figure is a statistical coverage estimate, not a prepaid reservation.

The approved display copy for a future presentation is **“完整学完预计约 X 积分，建议准备 Y 积分。”** Its note should state the standard 1x rate, reading mode, normal interactions, and exclusion of speech synthesis and relearning. This change does not alter the current operator page.

## Features and calibration

The extractor counts Unicode characters from the exact rows in the latest published structure when a course is published, or from its draft structure while unpublished. It follows the learning tree's hidden-subtree and leaf rules. A 1.0 lesson is parsed with MarkdownFlow to distinguish generated, interaction, and preserved blocks, and inherits its effective author prompt from the lesson, ancestor, or course. Its system-prompt feature includes the learner-context envelope that the runtime composes before sending it. A 2.0 lesson sends its entire script to the agent and uses its own built-in system instructions; the current host does not pass the 1.0 inherited prompt into that engine. Its one initial authored generation unit per lesson is a structural feature, not a claim that the agent makes only one call. The extractor produces nine course-level features: lesson count; dynamic, static, and system text in thousands of characters; generated block and explicit interaction counts; and the sums of squared per-lesson characters, characters × system text, and (characters + system text) × block count. The engine and detected authored language select separate calibration groups. Ambiguous language, learner-specific output language, empty lessons, or missing structure produce no numeric estimate.

Verified complete reading runs supply labels. Successful billable production LLM requests, including follow-up questions, are repriced at the common reference. TTS, previews, debugging, failed requests, and relearning are excluded. Samples must use the published snapshot active throughout the completion; the current authored text cannot be paired with earlier token use. The offline screener requires complete published, progress, generated-block, and usage exports, a deployment-window proof of the actual engine, an independently audited full user/course usage window, explicit reading mode on every request, and intact progress links. The 2.0 group additionally requires instrumented per-turn links and independent request-mode proof. It excludes unverifiable records and deduplicates repeated exports and relearning. Raw learner and authored content stay outside the repository.

For each engine/language group, offline fitting solves nonnegative weighted quantile regression at the whole-course level with a linear-programming solver, weighting courses equally. Course-grouped folds and a recency-held-out course set measure P50 weighted absolute percentage error and P80 empirical coverage; every validation course is absent from its model's training set. The report also compares a constant-character baseline and the previous approximation where its value is supplied. A group qualifies only with at least **100** completions from **10** distinct courses, P50 WAPE at most **30%**, and P80 coverage within **75%–85%**. The versioned artifact stores coefficients, training interval, feature bounds, validation metrics, and a checksum. Runtime validates these fields and refuses to extrapolate more than 20% beyond any observed feature bound.

## Offline workflow and current state

Install the offline solver with `python -m pip install -r requirements-calibration.txt` from `src/api/`. Use `src/api/scripts/course_completion_credit_samples.py` to screen a private candidate export, then `python -m scripts.calibrate_course_completion_credits private-candidates.json --version <version> --dry-run` from `src/api/` to inspect aggregate exclusions and held-out validation. Omit `--dry-run` only after reviewing the report; a qualified artifact is then written beside the predictor module. The command does not connect to a database and writes no artifact when no group qualifies. Candidate exports require external read-only extraction and independent review of their completeness and engine evidence.

No qualified training set or calibration artifact is in this repository. The documented 20-lesson, 51-call completion of **25.24 credits** is a billing sanity check; the matching historical authored characters are unavailable here. Local development data currently contain too few usage and progress records for calibration. Until validated real samples are supplied, the API intentionally returns `uncalibrated` with null values.

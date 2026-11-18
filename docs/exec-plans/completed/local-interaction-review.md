---
title: Reusable Local Interaction Review
status: completed
owner_surface: backend
last_reviewed: 2026-11-18
canonical: false
---

# Reusable Local Interaction Review

## Purpose / Big Picture

Developers can open a local evaluation report, inspect each learner step and
criterion across runs, and record a human decision with supporting notes.
They can resume their work in the browser or carry an annotation file to a new
copy of the report.

## Progress

- [x] 2026-11-18 09:40 UTC: Verified the report format, fixture fingerprint, and the two recorded live runs.
- [x] 2026-11-18 09:58 UTC: Generated self-contained review pages and preserved fixture context and call evidence in new reports.
- [x] 2026-11-18 10:08 UTC: Verified replay, legacy report review, and browser annotation workflows.

## Surprises & Discoveries

Earlier reports record filtered prose, rendered controls, removed interaction
syntax, final error types, and retry counts. The loader cannot reconstruct the
original arguments or validation feedback for rejected calls from those fields.

## Decision Log

- 2026-11-18. Keep automated results and human entries independently visible.
  Scope entries to a run, case, repeat, stage, and criterion.
- 2026-11-18. Generate standalone HTML from JSON. Store drafts in the browser
  and support JSON export and import as portable copies of the annotations.

## Outcomes & Retrospective

Saving a JSON report now produces a companion review page. The two saved live
reports open together with all 17 cases and 37 aligned learner steps. In Chrome,
annotations survived refresh and export and import. A conflicting import kept
the local note, and the second model's criterion remained independently editable.
All 3,435 MarkdownFlow and evaluator tests passed.

## Context and Orientation

The [interaction evaluator](../../../src/api/scripts/README.md#evaluate_mdf_interactionspy)
produces structured reports and accepts sanitized fixtures. HTML generation
uses those reports without contacting a model provider.

## Plan of Work

Record fixture context and model-call evidence when saving a report. Attach
fixture context to older reports only when the selected catalog fingerprint
matches. Show learner inputs, outputs, controls, memory, and automated
judgments with per-criterion human annotations.

## Concrete Steps

1. Extend saved evaluation evidence and implement the HTML generator.
2. Add report navigation, evidence views, criterion filters and statistics,
   and browser and file persistence for human decisions.
3. Generate the page for the existing two-model run and exercise the workflow.

## Validation and Acceptance

Run the local evaluator and MarkdownFlow tests. Compare both recorded live
reports in the browser and verify that an annotation survives refresh and an
export and import cycle. Check that separate runs and repeats keep independent
annotations, and that a report with a different fixture fingerprint is not
aligned to the same steps.

## Idempotence and Recovery

Regenerating a page from the same report keeps its run identity. Export an
annotation file to reopen decisions after moving the review page. Import
matches individual entries to the runs present in the page and reports
conflicting edits.

## Interfaces and Dependencies

The evaluator writes JSON and a companion HTML page for saved runs. The HTML
generator also accepts one or more saved reports with matching case selections.
The review uses the pinned Markdown parser and browser APIs.

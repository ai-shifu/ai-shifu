---
title: Learner image input
---

## Purpose / Big Picture

Learners can attach up to four JPEG, PNG or WebP images (5 MiB each) to a
lesson answer or text follow-up, with or without text. Images appear in saved
history and reach the configured vision-capable LLM as native image parts.

## Progress

- [x] 2026-11-06: Implemented uploads, composition, history and vision model
      mapping for reading, listening, previews and text follow-ups.
- [x] 2026-11-07: Verified image-only answers, follow-ups with a different image,
      history reload and the mobile layout against a real vision model.
- [x] 2026-11-11: Ported the feature to current main and passed the focused
      backend regression suite.
- [x] 2026-11-11: Scoped the shared reading composer to course surfaces and
      passed all web unit tests with the new library build.
- [ ] 2026-11-11: Pin the published MarkdownFlow UI 0.3.12 package, validate a
      clean install and open the application PR.

## Surprises & Discoveries

Engine checkpoints and interaction defaults already preserve string answers.
Local storage returns relative URLs that a remote model cannot fetch. The
gateway reads the verified local file and sends its data as a model image part.

## Decision Log

- Preserve existing input and checkpoint contracts by serializing attachments as
  reserved Markdown images (`![learner-image](URL)`). Keep these markers out of
  editable text through shared attachment controls and history presentation.
- At the application model boundary, map only these reserved learner markers to
  native image parts. Do not alter authored or assistant Markdown images.
- Append interaction images after all tool results in a request, preserving the
  provider's tool-call/result ordering. Persisted string answers need no migration.
- Use existing storage providers. Verify actual raster bytes, dimensions and size
  before upload; local files are materialized as data URLs only after the text
  envelope budget check. Keep the four newest images in model requests,
  preserving text and saved attachments in earlier turns. Use a text notice
  for missing local files and old storage locations. Never fetch arbitrary
  image URLs on the API server.
- Accept only the configured course-storage base URL or the exact local storage
  path with an opaque image key. Reject forged storage locations and more than
  four attachments on both learner and Debug request routes. Expose these
  storage prefixes to the browser to verify image links when opening history.
  Cap upload attempts at 32 per learner per hour before decoding or persisting
  files.
- Preserve editable inputs while an upload is in progress and block submission
  until it settles. Text and images share the existing send control.
- Existing model selection remains authoritative. Vision requires a compatible
  configured model. Live voice and third-party workflow image transport are out
  of scope. Third-party workflows reject new image submissions and receive
  a text notice for earlier attachments, preserving earlier text.

## Outcomes & Retrospective

The local preview confirmed that the model interpreted uploaded images and
history reloaded with thumbnails. The application pins the published
MarkdownFlow UI 0.3.12 release.

## Context and Orientation

`ContentBlock` owns shared lesson controls, `AskBlock` owns text follow-ups,
`learn/routes.py` owns authenticated learner endpoints, and
`api/llm/markdownflow_model.py` maps engine messages to the shared gateway.

## Plan of Work

Add a verified upload endpoint and shared image-marker mapping. Add reusable
attachment controls to lesson and follow-up inputs, preserving text-only behavior.
Test upload refusal, native model payloads, history, retries and analytics isolation.

## Concrete Steps

Run focused pytest and Jest suites, then web type-check/lint, Ruff, translation,
architecture and repository harness checks. Inspect the final diff for scope.

## Validation and Acceptance

Image-only and image-plus-text answers reach the gateway with `image_url` parts;
multiple interaction results remain contiguous; old text inputs remain byte-stable.
Uploaded files with invalid bytes, unsupported formats or excessive size fail
before storage. Successfully uploaded attachments remain available if a later
file fails to upload. Learners can reselect the failed file to retry. History
shows thumbnails instead of marker source. Analytics failure never prevents uploads.

### Image upload analytics contract

See [Frontend Product Analytics](../../references/frontend-product-analytics.md).

- Business question: Can learners successfully attach images to answers and questions?
- Metric: daily upload success / attempts, grouped by answer versus follow-up.
  This measures uploads, not model-answer quality or sent-message conversion.
- Events: `learner_image_upload_started`, `learner_image_upload_finished`.
- Trigger: after a valid file is accepted for upload; exactly one terminal event
  on success or failure. Validation refusals emit neither event.
- Population: learner members and guests using editable lesson or text follow-up
  controls. Exclude previews, readonly/print history and live voice controls.
- Count unit/deduplication: one file upload invocation, guarded against concurrent
  batches; no render or history events. No persisted cross-tab deduplication.
- Correlation: aggregate only; no exact attempt join is claimed.
- Consumer: product owner's daily feature reliability query; no existing dashboard
  or event is renamed. Additive new family, no historical backfill.
- Schema: `surface` enum `answer|follow_up`; finished also has `outcome` enum
  `success|failed`. No filenames, image URLs, text, prompts or errors.
- Verification: exact names/payloads, eligibility, terminal outcomes, no render
  duplicates, sensitive-field absence and throwing tracker isolation.

## Idempotence and Recovery

Uploads use random object identifiers. Retrying creates another object, never
overwrites an existing upload. Unsent uploads remain subject to the configured
storage retention policy.
Reverting this feature leaves historical markers as valid Markdown strings.

## Interfaces and Dependencies

Reuse the authenticated request transport, storage providers, Pillow and
`useTracking`. MarkdownFlow UI owns the picker and previews through
`showImageInput` and `imageInput`. The application owns uploads and encodes
`OnSendContentParams.images` as persisted learner markers. The application PR
must pin the published MarkdownFlow UI release. The database schema is unchanged.

---
title: Learner Listen Playback and Timeline
status: implemented
owner_surface: frontend
last_reviewed: 2026-11-04
canonical: true
---

# Learner Listen Playback and Timeline

1. Listen mode shows a lesson-wide generated-slide timeline. Each available
   slide is a selectable marker; future slides are absent until generated.
   The first release omits persistent page-count copy; active output is
   explicitly labelled `Generating`.
2. Selecting a generated slide switches the visual immediately and stops the
   previous slide audio. Ready target audio starts from its beginning; missing
   target audio waits in place and starts when generated. Partially generated
   visuals remain selected and continue rendering.
3. Checkpoints are emitted at pause, logical-item completion, low-frequency
   progress, and unmount. They never clear merely because one segment ends.
4. A checkpoint is keyed by the logical audio item and course/lesson scope.
5. Returning to listen mode or reloading restores the matching audio item and
   attempts normal playback. A browser may still reject unmuted autoplay after
   a full reload, in which case the restored position remains ready to play.
6. Existing player-button behavior is unchanged by slide navigation.

## Reading interaction questions and shared transport

Native interaction questions travel with their controls in optional
`payload.interaction_question` metadata. Reading and Debug do not append that
question as lesson prose. Questions already present in authored narration remain
unchanged. Short confirmation labels retain their existing button behavior.

For ordinary answer-collecting interactions, the shared course/profile runtime
must first ask the complete current question in visible teaching content, then
call the real `interact` tool in the same turn and wait. A control title is
not a replacement for asking the question. Preserve authored questions,
choices, retries and input boundaries. Do not invent a new teaching question
for authored navigation or confirmation controls. Structured direction keeps
its dedicated tool-only contract: the host presents its feedback and
unanswered question before the controls.

Profile questionnaire interaction chunks contain only the rendered controls.
Question wording comes from the model's ordinary visible content under the
shared question-first instruction. The host never prepends the tool question,
including when restoring pending input, rejecting an answer or exposing a queued
interaction. It does not compare question text with prose to choose presentation.
Interaction identities, stored answers and published prose remain unchanged.
Exact request replays retain their saved event payloads; existing cached history
is not rewritten.

Interaction `content` contains only the original controls in memory, storage,
streamed events and serialized history. The question is carried exclusively in
`interaction_question` metadata. Serialization never prepends question text,
and frontend consumers parse and render the control content directly.

Use `question` for this presentation concept, distinct from model instructions
such as a system or course prompt. The existing engine `interact(prompt=...)`
tool and pending-session schema keep their compatibility contract; the host
maps that wording to `interaction_question`. This optional presentation field
is renamed before release, so no deployed-field alias or data migration is
needed.

Reading and Debug ignore the question metadata when rendering controls.
Desktop, mobile and print share this display rule. Listen/classroom title
presentation is a separate dependent change; the metadata never becomes part
of the interaction body.

This shared transport stops producing separate question CONTENT, audio and
marker elements in every mode. Authored narration and its audio are preserved.
Previously stored prose is not guessed or rewritten. No migration or library
version bump is required.

This changes existing-content placement, with no new action
or analytics meaning. Question text must never be sent to analytics.

## Listen and classroom interaction titles

Listen and classroom modes use a nonblank native `interaction_prompt` as the
active interaction panel title. Its body shows only the controls. Moving to
another interaction updates the title; changing only the metadata at the same
element ID also invalidates the rendered-element cache. Historical questions
and answered controls retain their corresponding title and answer.

Titles display the original prompt as literal text. HTML and Markdown are not
executed or rendered as rich content. Missing/blank prompts and system controls
retain the existing localized generic title. Short confirmation wording that
already labels its button keeps that behavior.

The question is not emitted again as a slide, lesson body or independent audio.
Switching back to reading continues to hide the extra prompt. This consumer
change depends on the reading/shared transport contract and introduces no new
backend, database, dependency or analytics behavior.

### `learner_listen_resume_requested`

- Business question: What share of eligible listen sessions has a saved audio
  checkpoint to resume?
- Metric definition: Count resume-request events by course over a reporting
  window; compare with existing learner listen-session reporting as the
  denominator. This measures a resumable checkpoint, not autoplay success.
- Actor and surface: Learners on `learner_listen`; guests and members are
  included, preview mode is excluded.
- Trigger: After a valid checkpoint is read for the current course and lesson
  and before it is supplied to `Slide`.
- Count unit and deduplication: One event per course/lesson renderer scope;
  repeated renders and effects for that scope do not emit another event.
- Consumers: Learner playback adoption reporting owned by the learning team.
- Compatibility: New additive event; no backfill.
- Verification: Renderer tests cover the trigger and allowlisted payload;
  tracking uses `useTracking` and failures are ignored.

| Field       | Type   | Allowed values    | Cardinality | Privacy class | Why required          |
| ----------- | ------ | ----------------- | ----------- | ------------- | --------------------- |
| `shifu_bid` | string | course machine ID | high        | pseudonymous  | course-level grouping |
| `surface`   | string | `learner_listen`  | 1           | non-personal  | fixed product surface |

### `learner_listen_slide_navigate`

- Business question: Do learners use generated-slide markers to revisit or
  advance among available lesson slides?
- Metric definition: Count successful timeline selections and compare them
  with listen sessions that expose more than one generated slide.
- Actor and surface: Learners on `learner_listen`; guests and members are
  included, preview mode is excluded.
- Trigger: After the UI library accepts a marker selection for a different
  generated slide and requests navigation to it.
- Count unit and deduplication: One event per accepted marker selection; no
  deduplication across deliberate repeated selections.
- Consumers: Learner navigation reporting owned by the learning team.
- Compatibility: New additive event; no backfill.
- Verification: Renderer tests cover the exact event name, allowlisted payload,
  preview exclusion, and fail-open analytics behavior.

| Field                  | Type   | Allowed values                   | Cardinality | Privacy class | Why required            |
| ---------------------- | ------ | -------------------------------- | ----------- | ------------- | ----------------------- |
| `generated_step_count` | number | positive integer                 | bounded     | non-personal  | available timeline size |
| `shifu_bid`            | string | course machine ID                | high        | pseudonymous  | course-level grouping   |
| `surface`              | string | `learner_listen`                 | 1           | non-personal  | fixed product surface   |
| `target_step_index`    | number | zero-based generated slide index | bounded     | non-personal  | selected location       |

### `learner_listen_slide_timeline_exposed`

- Business question: What share of eligible listen sessions uses generated
  slide navigation?
- Metric definition: Count unique timeline exposures as the eligible
  denominator and accepted `learner_listen_slide_navigate` events as usage.
- Actor and surface: All learners rendered on `learner_listen`, including
  guests and members; preview mode and timelines with fewer than two generated
  slides are excluded.
- Trigger: Once per in-page course/lesson scope when at least two generated
  slide markers become available.
- Count unit and deduplication: One exposure per course and lesson for the
  lifetime of the loaded page; further generated slides and mode round trips do
  not emit another exposure.
- Consumers: Learner navigation reporting owned by the learning team.
- Compatibility: New additive event; no backfill.
- Verification: Renderer tests cover eligibility, deduplication, exact
  allowlisted payloads, preview exclusion, and fail-open tracking.

| Field                  | Type   | Allowed values    | Cardinality | Privacy class | Why required            |
| ---------------------- | ------ | ----------------- | ----------- | ------------- | ----------------------- |
| `generated_step_count` | number | integer >= 2      | bounded     | non-personal  | available timeline size |
| `shifu_bid`            | string | course machine ID | high        | pseudonymous  | course-level grouping   |
| `surface`              | string | `learner_listen`  | 1           | non-personal  | fixed product surface   |

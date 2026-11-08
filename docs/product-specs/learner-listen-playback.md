---
title: Learner Listen Playback and Timeline
status: implemented
owner_surface: frontend
last_reviewed: 2026-11-08
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

For an ordinary answer interaction, the model asks the question in visible
Markdown prose and then calls `interact` with the same wording in `question`.
When the control has a leading `{{...}}` binding, that question is the exact
text inside the braces, even when it is a short label. The runtime
uses `question` for the interaction and memory without generating a second
presentation from the tool arguments. For structured
direction, the runtime presents the guiding question within the structured
feedback. Confirmation and authored navigation send an empty question. Custom
navigation labels use the tool options.

Interaction `content` contains only the controls. Current answer controls use
the default listen and classroom panel title, while the learner receives the
question in the model's teaching content. Reading, Debug, and Profile likewise
display that content separately from the controls.

Historical `prompt` values remain readable as `payload.interaction_question`
presentation metadata. Existing saved prose and exact request replay payloads
keep their prior presentation.
See [Learner Memory Admission](./learner-memory-admission.md) for storage rules.

This changes existing-content placement, with no new action
or analytics meaning. Question text must never be sent to analytics.

## Listen and classroom interaction titles

Listen and classroom modes use a nonblank native `interaction_question` as the
active interaction panel title. Its body shows only the controls. Moving to
another interaction updates the title; changing only the metadata at the same
element ID also invalidates the rendered-element cache. Historical questions
and answered controls retain their corresponding title and answer.

Titles display the original question as literal text. HTML and Markdown are not
executed or rendered as rich content. Missing or blank questions, system
controls, and questions whose trimmed value is `sys_user_nickname`,
`sys_user_language` or `sys_user_background` use the localized generic title.
Short confirmation wording that already labels its button keeps that behavior.

The question is not emitted again as a slide, lesson body or independent audio.
Switching back to reading continues to hide the extra question. This consumer
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

### `learner_listen_slide_keyboard_navigate`

The learning team uses this event to measure adoption of vertical keyboard
navigation. Reports count accepted turns by course and direction over a
reporting window. Timeline reporting uses the separate marker selection event.

Guests and members are eligible in learner listen mode when the course and
lesson IDs are available and at least two generated slides exist. Preview and
classroom are excluded.

The renderer emits after a committed move to the adjacent generated slide in
the direction of an unmodified, canceled arrow key event in the same dispatch
task. Arrow Up moves to the previous slide and Arrow Down to the next slide.
Keys used for scrolling, disabled navigation, and attempts that leave the
current slide in place fall outside the trigger.

Each matching dispatch is consumed once. Separate accepted turns each count,
including repeated visits to a slide. The renderer scopes the association to the
current course and lesson and sends the course ID for course-level reporting.
This additive event starts with the release.

Renderer tests verify the trigger, exclusions, single emission per matching
dispatch, exact payload, and continued navigation when `useTracking` fails.

| Field       | Type   | Allowed values     | Cardinality | Privacy class | Why required          |
| ----------- | ------ | ------------------ | ----------- | ------------- | --------------------- |
| `shifu_bid` | string | course machine ID  | high        | pseudonymous  | course-level grouping |
| `surface`   | string | `learner_listen`   | 1           | non-personal  | fixed product surface |
| `direction` | string | `previous`, `next` | 2           | non-personal  | groups turns by key   |

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

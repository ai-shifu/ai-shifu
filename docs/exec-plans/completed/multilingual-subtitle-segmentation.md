# Multilingual Subtitle Segmentation

## Purpose / Big Picture

Recognize sentence-ending punctuation across writing systems when generating
subtitles, without maintaining separate Chinese/English punctuation lists.
Keep subtitle timing derived from the existing audio/provider alignment paths.

## Progress

- [x] 2026-09-28 UTC: Inspected streaming TTS, request batching, Tencent
      alignment, frontend subtitle consumption, and their regression tests.
- [x] 2026-09-28 UTC: Selected one shared Unicode punctuation pattern.
- [x] 2026-09-28 UTC: Integrated subtitle-producing segmentation paths and
      multilingual, source-range, and timing regression tests.
- [x] 2026-09-28 UTC: Fixed and independently verified the review finding about
      punctuation-only stream continuations triggering synthesis requests.
- [x] 2026-09-28 UTC: Passed all 771 TTS tests, Ruff, repository harness,
      architecture checks, and the complete lefthook pre-commit gate. Reviewed
      scope and acceptance before moving the plan to completed.

## Surprises & Discoveries

- Frontend subtitle utilities normalize cues and remove selected trailing
  punctuation; sentence boundaries originate in backend TTS paths.
- Three copies of the same Chinese/English delimiter set serve streaming TTS,
  pipeline batching, and Tencent alignment. Updating only one would leave
  provider-dependent segmentation.
- Grouping consecutive punctuation exposed the existing length-only submission
  check: a punctuation run in a later chunk could become a TTS request. Reusing
  `has_speakable_text` for completed sentences and final tails prevents this.

## Decision Log

- Use `regex`'s Unicode `Sentence_Terminal` property, with existing semicolon
  pauses retained and corresponding Arabic/Greek forms recognized. Pin the
  already installed, verified package version as a direct dependency.
- Group adjacent terminal punctuation and trailing closing quotes/brackets.
  Retain the existing immediate punctuation-based streaming contract. This
  change does not introduce language detection or NLP abbreviation inference.
- Keep provider timestamps, source indices, audio offsets, duration weighting,
  metering, and subtitle DTOs in their existing owners. No frontend interaction
  or analytics contract changes are required.
- Leave Tencent TextToVoice request-size splitting unchanged: that provider
  supplies no subtitles and its length-limit handling is separate work.

## Outcomes & Retrospective

Subtitle-producing paths now share Unicode sentence-terminal recognition.
Provider indices and timestamp allocation remain unchanged. All 771 TTS tests
passed, including complete and chunked multilingual punctuation, finalization,
and source alignment cases. Independent review verified the punctuation-only
request fix; the full repository pre-commit gate passed. No service deployment
or persisted subtitle migration is part of this change.

## Context and Orientation

`src/api/flaskr/service/tts/patterns.py` owns shared compiled patterns.
`streaming_tts.py` uses the sentence pattern for synthesis and fallback cues.
`pipeline.py` uses boundaries when batching complete text. Tencent's provider
in `src/api/flaskr/api/tts/tencent_provider.py` additionally maps sentence
ranges onto provider timestamps. Tests live in `src/api/tests/service/tts/`.

## Plan of Work

Replace the common pattern with Unicode properties, have pipeline and Tencent
consume it, then cover Unicode terminals, punctuation groups, source offsets,
stream finalization, and fallback timing through the existing entry points.

## Concrete Steps

1. Pin `regex` and update the common pattern and pipeline consumer.
2. Consolidate Tencent text/range splitting and terminal checks on that pattern.
3. Run focused tests, then the complete TTS suite and repository gates.

## Validation and Acceptance

Arabic, Urdu, Indic, Burmese, Ethiopic, Armenian, Japanese, Chinese, and Latin
script examples should split at their supported terminal punctuation. Opening
punctuation and commas must not create boundaries. Consecutive terminal marks
and closing quotes received together must stay with the preceding sentence.
Unterminated stream fragments must survive until finalization. Source ranges
must still map exactly to original text, and fallback cue duration must end at
the supplied audio offset plus duration. Existing TTS tests must remain green.

## Idempotence and Recovery

There is no data migration or external write. Reverting the implementation and
dependency pin restores previous behavior; already persisted cues are unchanged.

## Interfaces and Dependencies

The shared `SENTENCE_ENDINGS.finditer()` match interface remains available.
`regex==2025.11.3` provides Unicode property support documented in the
[package reference](https://pypi.org/project/regex/2025.11.3/).
This is punctuation segmentation, so punctuation-free languages/text and
language-specific abbreviation disambiguation still use existing behavior.

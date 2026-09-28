# Multilingual Subtitle Segmentation

## Purpose / Big Picture

Recognize sentence-ending punctuation across writing systems when generating
subtitles, without maintaining separate Chinese/English punctuation lists.
Keep subtitle timing derived from the existing audio/provider alignment paths.
Preserve multilingual expressive punctuation and closing quotes when rendering
subtitles under the existing trailing-punctuation display policy.

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
- [x] 2026-09-28 UTC: Addressed PR #2999's shared-alignment timing review:
      partitioned cross-sentence indexed Tencent cues and passed all 777 TTS
      tests, including short-duration rounding and single-sentence anchors.
- [x] 2026-09-28 UTC: Narrowed pre-submit filtering to sentence-ending
      punctuation and closer fragments after provider-policy review. All 789
      TTS tests passed, including symbol-only completed sentences and final
      tails for Aliyun, Baidu, and Volcengine HTTP.
- [x] 2026-09-28 UTC: Covered overlapping provider anchors and standalone
      closing punctuation. Grouped Tencent cues now remain monotonic, and
      punctuation filtering requires a previously consumed sentence boundary.
      All 797 TTS tests and an independent final review passed.
- [x] 2026-09-28 UTC: Extended frontend trailing-punctuation handling
      to multilingual question/exclamation marks, Unicode closing punctuation,
      and code points outside the BMP. All 145 focused frontend and renderer
      tests, type checking, and lint passed, including persisted and streaming
      cue paths and unchanged timing metadata.
- [x] 2026-09-28 UTC: Addressed mixed closing-punctuation/speech chunks from
      the follow-up review. Detached Unicode closers no longer migrate into
      the next sentence. All 810 TTS tests passed, including raw offsets,
      final tails, opening quotations, and provider symbol handling.
- [x] 2026-09-28 UTC: Replaced quote-category assumptions with shared pairing
      context for German reversed quotes, spaced French closers, and opening
      quotes at chunk boundaries. All 881 TTS tests passed, including source
      offsets, Tencent terminal handling, provider punctuation policies, and
      word-initial apostrophes inside a quotation.

## Surprises & Discoveries

- Frontend subtitle utilities normalize cues and remove selected trailing
  punctuation; sentence boundaries originate in backend TTS paths.
- The frontend's Chinese/English preservation list removed Arabic question
  marks and French closing quotes. UTF-16 indexing also missed supplementary
  punctuation, while spaces inside quotes stopped punctuation removal early.
- Three copies of the same Chinese/English delimiter set serve streaming TTS,
  pipeline batching, and Tencent alignment. Updating only one would leave
  provider-dependent segmentation.
- Grouping consecutive punctuation exposed the existing length-only submission
  check: a punctuation run in a later chunk could become a TTS request. Reusing
  the shared sentence-terminal and closer character classes to skip punctuation
  fragments prevents this without discarding symbols supported by providers.
- PR review identified that one indexed Tencent alignment can span multiple
  source sentences. Reusing its entire interval for each sentence creates
  overlapping subtitles after recognizing additional Unicode boundaries.

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
- Partition an indexed Tencent cue across the source sentences it overlaps,
  using the existing speech-weight helper on each source intersection. Use
  cumulative rounding so adjacent intervals meet and the provider's outer
  endpoints survive. Non-overlapping cues contained in one sentence retain
  their full interval. Clamp each grouped sentence to its predecessor's end
  when provider anchors overlap, allowing zero-length cues without extending
  the overall timeline.
- Filter only sentence-ending punctuation/closer fragments before submitting
  synthesis tasks, and only after a sentence boundary was already consumed.
  Standalone closing punctuation, emoji, mathematical symbols, and other
  punctuation still reach the provider-aware `skip_non_speakable_text` decision.
- Leave Tencent TextToVoice request-size splitting unchanged: that provider
  supplies no subtitles and its length-limit handling is separate work.
- Preserve the frontend display policy: remove ordinary trailing punctuation
  while keeping question/exclamation marks, ellipses, and closing quotes or
  brackets. Use Unicode `Pe`, `Pf`, and `Quotation_Mark` for closing punctuation
  and a Unicode 17.0 name-derived set for expressive punctuation, for which
  JavaScript has no equivalent semantic property. Iterate by code point and
  retain whitespace inside closing quotes. This is a display-only correction
  with no new interaction or analytics event.
- Do not normalize source text or infer its language. Explicit U+037E Greek
  question marks are preserved; ASCII semicolons keep their existing removal
  policy. Greek text using the canonically equivalent ASCII semicolon remains
  ambiguous without a content-language contract.
- After a consumed sentence boundary, strip detached Unicode closing-mark
  tokens before submitting a mixed punctuation/speech segment or final tail.
  Quote roles use a shared pairing context carried through streamed sentence
  boundaries, so reversed closing quotes stay with their sentence while a
  following opening quote remains in the next sentence. Only quotes that close
  a pending pair are removed from a later chunk's prefix; detached non-quote
  brackets retain the existing cleanup policy. Keep raw buffers and boundary
  offsets unchanged.

## Outcomes & Retrospective

Subtitle-producing paths now share Unicode sentence-terminal recognition.
Provider indices remain unchanged; indexed Tencent cues spanning multiple
sentences are apportioned within their original interval. All 881 TTS tests
passed, including complete and chunked multilingual punctuation, finalization,
contextual quotation pairing, and source alignment cases. Independent review
verified the punctuation-only request fix; the full repository pre-commit gate
passed. No service deployment
or persisted subtitle migration is part of this change.
The frontend also preserves multilingual expressive punctuation and closing
quotes before passing cues to the existing slide library. No library release,
dependency update, or subtitle timing change is needed for this display fix.

## Context and Orientation

`src/api/flaskr/service/tts/patterns.py` owns shared compiled patterns.
`sentence_boundary.py` owns quote-aware matching and its immutable quote state.
`streaming_tts.py` uses the sentence pattern for synthesis and fallback cues.
`pipeline.py` uses boundaries when batching complete text. Tencent's provider
in `src/api/flaskr/api/tts/tencent_provider.py` additionally maps sentence
ranges onto provider timestamps. Tests live in `src/api/tests/service/tts/`.
`src/web/src/lib/subtitleUtils.ts` owns trailing-punctuation display cleanup;
`listenModeUtils.ts` applies it to persisted and streaming subtitle cues.

## Plan of Work

Replace the common pattern with Unicode properties, have pipeline and Tencent
consume it, then cover Unicode terminals, punctuation groups, source offsets,
stream finalization, and fallback timing through the existing entry points.

## Concrete Steps

1. Pin `regex` and update the common pattern and pipeline consumer.
2. Consolidate Tencent text/range splitting and terminal checks on that pattern.
3. Run focused tests, then the complete TTS suite and repository gates.
4. Update frontend punctuation display rules and cover utility behavior plus
   persisted and streaming cue integration without changing cue metadata.

## Validation and Acceptance

Arabic, Urdu, Indic, Burmese, Ethiopic, Armenian, Japanese, Chinese, and Latin
script examples should split at their supported terminal punctuation. Opening
punctuation and commas must not create boundaries. Consecutive terminal marks
and closing quotes received together must stay with the preceding sentence.
Unterminated stream fragments must survive until finalization. Source ranges
must still map exactly to original text, and fallback cue duration must end at
the supplied audio offset plus duration. Existing TTS tests must remain green.
When a Tencent alignment spans multiple sentences, its time must be divided
between those source intersections instead of duplicated. Cumulative rounding
must preserve endpoints even for zero- or one-millisecond alignments; separate
non-overlapping alignments contained in one sentence retain their original
times. Overlapping provider anchors must not move a later sentence backwards
or extend the overall provider timeline.
Symbol-only content and punctuation other than sentence-ending/closer fragments
must still reach the provider-aware non-speakable-text check. Standalone
sentence-ending/closer input also follows that policy; only continuations of
an already consumed sentence boundary are filtered before submission.
Frontend output must retain Arabic question marks, French/German closing quotes,
spacing inside quotes, and expressive punctuation variants. Ordinary trailing
punctuation, including supplementary-plane sentence endings, remains hidden.
Both persisted and streaming paths must retain cue timing, position, and segment
indices and leave the source cue objects unchanged.
German reversed closing quotes must not gain an extra Tencent terminal mark or
migrate to the next subtitle. Adjacent CJK/Latin opening quotes, including an
opening quote at a stream chunk's end, must remain attached to the next sentence.
Quote continuations split across chunks must preserve raw offsets and avoid
swallowing a new quoted phrase.

## Idempotence and Recovery

There is no data migration or external write. Reverting the implementation and
dependency pin restores previous behavior; already persisted cues are unchanged.

## Interfaces and Dependencies

The shared `SENTENCE_ENDINGS.finditer()` match interface remains available.
`regex==2025.11.3` provides Unicode property support documented in the
[package reference](https://pypi.org/project/regex/2025.11.3/).
This is punctuation segmentation, so punctuation-free languages/text and
language-specific abbreviation disambiguation still use existing behavior.

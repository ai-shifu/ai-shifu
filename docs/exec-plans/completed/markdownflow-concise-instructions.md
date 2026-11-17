# Concise MarkdownFlow instructions

## Purpose / Big Picture

Make MarkdownFlow's model-facing instructions shorter and more precise while
preserving the existing interaction, feedback, memory, rendering and completion
contracts. Repeated explanations currently appear in the base prompt, resumed
answer guidance, conditional feedback instructions and tool descriptions.

The authoring syntax, parser, tool schemas, validation, runtime feature flags and
evaluation assertions remain unchanged. This is separate from the experiment
that rewrote lesson scripts as natural language and thereby removed parsed
pause and feedback anchors.

## Progress

- [x] 2026-11-16: Updated the existing feature branch and captured all 66 runtime,
  prompt and evaluator source files. They match the previous syntax-based
  evaluation baseline.
- [x] 2026-11-16: Assigned independent reviews of core and optional prompt
  contracts and prepared an isolated evaluation directory.
- [x] 2026-11-16: Simplified all 13 prompt modules and model-facing prose in
  three Python files; independently reviewed retained contracts and conditional
  paths. Prompt modules total 5,689 words instead of 8,839 (35.6% fewer).
- [x] 2026-11-16: Verified unchanged executable Python and tool-schema structure;
  all 3,401 engine/evaluator tests pass, and the 57 offline replays match baseline.
- [x] 2026-11-16: Ran all 55 live cases on all six active production routes;
  preserved all 330 paired results and requests, and reviewed all 19 question flags.
- [x] 2026-11-16: Updated reviewed prompt fingerprints, documentation indexes and
  validation evidence; repository-wide checks pass. No merge or deployment.

## Surprises & Discoveries

The previous natural-language authoring experiment changed generated system
instructions and feedback schemas even though runtime source was unchanged.
This experiment retains the original authored syntax so those mechanisms stay
enabled. The existing tool offers `direction`/`review` to portable hosts and a
required `feedback` object only on the supported course feedback path; prose
must describe the offered schema accurately rather than rename the contract.

The focused instruction-delivery tests depended on old headings, numbered rules
and prose fragments. Update those wording assertions to the reviewed text or
complete module delivery while retaining event, state, source-evidence and
boundary assertions. Historical migration fingerprints remain unchanged; the
package test separately pins the reviewed current prompt hashes.

## Decision Log

- Reuse the current feature branch and its open PR. Do not merge into `main`.
- Compare against the previous 264/330 run with the same literacy-course
  constraints and original syntax-based teaching scripts. Do not use the
  natural-language-script result as the primary control.
- Reduce repetition and wording, not validation or authored requirements.
  Keep separately enabled instruction modules self-contained.
- Preserve exact answer-storage keys while allowing equivalent learner-facing
  questions. Preserve confirmation/navigation boundaries and the structured
  direction exception.
- Keep evaluator rules and fixtures fixed. Review disputed judgments separately
  from raw scores, and distinguish invocation failures from behavior failures.

## Outcomes & Retrospective

The simplification and evaluation are complete. No production course or runtime
was changed. The candidate is shorter, but this run does not justify deploying
it as a reliability improvement. Total passes decreased from 264 to 262 of 330;
first-attempt passes decreased from 182 to 161. There were 26 failed-to-passed
pairs and 28 passed-to-failed pairs, with no invocation or harness failures.

| Production route | Total passes before / after | First-attempt passes before / after |
| --- | ---: | ---: |
| CN Fast / DeepSeek | 43 / 41 | 21 / 6 |
| CN Balanced / GLM | 34 / 41 | 15 / 24 |
| CN Quality / Qwen | 48 / 44 | 31 / 24 |
| US Economy / DeepSeek | 39 / 36 | 18 / 13 |
| US Balanced / Gemini | 49 / 49 | 47 / 46 |
| US Quality / GPT | 51 / 51 | 50 / 48 |

All 13 prompt modules total 39,576 UTF-8 bytes instead of 57,747. Paired first
requests contain 32.1% fewer system-instruction characters and 11.3% fewer tool
description characters, a combined mean reduction of 23.8% (69,960 to 53,316).
These are character measurements, not tokenizer estimates. Every first-request
field outside system prose and descriptions matches the control, including the
course prompt, authored script, tool-schema structure and provider settings.

Automatic continuations increased from 63 to 80, and tool retries from 53 to 60.
On CN Fast, 28 recovered cases printed the final content without a tool call,
then called `finish` after automatic continuation; the control had 18 such cases.
The captured requests confirm no new teaching prose during those continuations.
This is an observed symptom, not proof of a particular sentence causing it.

Automatic missing-question flags increased from 16 to 19. Manual review of all
19 found 15 clear omissions, three borderline requests and one likely false
positive. Raw scores are unchanged. Other failures prevented question judging
in 18 candidate steps versus 12 in the control, so flag counts alone are not a
complete question-quality measure. Each model/case pair ran once; outcomes can
vary, and the shared course constraints can conflict with some original fixture
expectations in both runs.

The executable Python AST is unchanged outside docstrings, descriptions and the
explicitly reviewed answer-reference notice. All 128 offline model requests have
identical tool schemas after removing descriptions. The 57 replay results are
identical to the baseline: 43 first-attempt passes, 12 recovered passes and two
expected fault replays, with networking disabled. The experiment preserves all
621 recursively checked Pydantic field-set nodes and unchanged fixture content.

The fresh CN/US catalog contains the same six model routes as the baseline. All
330 live pairs used frozen runtime sources, the same course prompt, original
authored syntax, fixed judge and evaluation assertions. Source hashes match
before and after the run.

Repository harness validation and the complete repository-wide lefthook gate
pass. The local check environment uses the repository-pinned Ruff 0.17.3.

Local audit artifacts are retained under the thread's
`simplified-prompts-comparison` visualization directory: `report.json`,
`comparison.json`, `request-audit.json`, `runtime-contract.json`,
`schema-contract.json`, all 330 `all-case-pairs.json` records, original request
bodies, `runtime-prompts.md`, and the learner-facing `index.html`. The page
reconstructs every pair failing in either run, preserves original Markdown,
renders only visible control fields, and shows manual question-review notes
separately. Full source snapshots and archive checksums identify the evaluated
candidate independently of its base Git HEAD.

## Context and Orientation

`src/api/markdownflow/engine/prompts/` contains the base and optional instruction
modules. `engine.py` composes them and builds tools. `tools.py`, `direction.py`
and `answer_context.py` contain tool descriptions and current-answer guidance.
`src/api/tests/markdownflow/` protects the engine's portable contracts.
`src/api/scripts/evaluate_mdf_interactions.py` runs fixed replays or live cases.

See `docs/design-docs/markdownflow-engine-library.md` for the engine boundary and
`docs/product-specs/learner-listen-playback.md` for question presentation.

## Plan of Work

First inventory the original instruction responsibilities and their activation
conditions. Rewrite core and optional prompts in parallel, then shorten tool
descriptions and current-answer reference guidance. Cross-review the result
against the original clauses, with particular attention to omitted exceptions.
Update text-contract assertions only where wording intentionally changed.

Freeze the candidate before running the full live matrix. Retain the same
course constraints, teaching scripts, inputs, judge and provider settings as
the control. Preserve all request bodies without credentials. If transport
fails, retain the original attempt and supplement only invocation failures;
never rerun successful or behavioral-failure pairs to select a better result.

## Concrete Steps

1. Capture baseline runtime files, prompt hashes and the prior result report.
2. Edit model-facing wording only and record clause coverage and size changes.
3. Compare Python ASTs excluding explicitly reviewed text locations and compare
   actual tool schemas with description fields removed.
4. Run `python -m pytest tests/markdownflow/ -q` from `src/api`, relevant evaluator
   tests, and the 57-case offline replay with network access disabled.
5. Run all 55 live cases on each active route and reconstruct changed failures
   using actual learner prose and controls.
6. Regenerate repository knowledge indexes, run the repository harness and
   required commit checks, and synchronize the existing PR description.

## Validation and Acceptance

All existing executable behavior and non-description schema fields must remain
unchanged. Offline results must preserve the baseline behavior, including the
two expected fault replays. Engine tests must pass. The candidate must still
load syntax, feedback and other optional modules on the same paths as before.

Live evidence reports first-attempt passes, recovered passes, question-judgment
coverage, tool retries and automatic continuations separately. A shorter prompt
is not sufficient evidence of better teaching, and one run does not establish a
stable success rate. Unexpected functional regressions require correction or
an explicit unresolved result rather than altered assertions.

## Idempotence and Recovery

Keep original source snapshots and raw reports immutable. Resume only an
identical candidate with matching source, fixture and model-route fingerprints.
Stop a route after repeated invocation failures rather than exhausting the
remaining cases against a broken connection. Preserve every valid output and
record supplemental attempt provenance. No migration or online publication is
required; the previous prompt text remains available in Git.

## Interfaces and Dependencies

No tool fields, DTOs, parser behavior, validation rules, runtime flags or
dependencies change. Only model-facing text and the tests/documentation that
identify that text are updated. Existing model adapters and the course gateway
remain the execution path for live evaluation.

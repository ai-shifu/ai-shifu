# Interaction evaluation coverage

The bundled catalog has 28 cases, including 17 derived from distinct Langfuse
sessions and 11 synthetic cases. The 12-case smoke suite covers choice, text,
and combined submissions, including one-option navigation. The navigation
fixtures check the authored option, require an explicit click, and verify that
fixed choices preserve learner memory. Both observation paths accept any
navigation question, including an empty title. They check the button's
submitted value, the scenario-specific question after the click, and unchanged
memory across the click. Preparation prose can omit a reminder to click.
The full catalog includes 10 replay-only cases.

## Teaching paths

| Learner behavior | Case |
| --- | --- |
| Choose a visible label and store the answer under the authored question | `lf-course-01` |
| Choose a visible label whose submitted value is a stable ID | `lf-course-35` |
| Submit two selected options | `lf-course-08` |
| Submit a written answer after reloading the question | `lf-course-07` |
| Choose an option or enter a custom answer in a single-choice control | `lf-course-04`, `lf-course-03` |
| Select multiple options or enter only text in a multi-choice control | `lf-course-06`, `lf-course-16` |
| Pause for an explicit click after visible teaching | `lf-empty-pause-01` |
| Use an earlier preference and collect a fixed one-option answer without writing it to memory | `natural-language-single-answer` |
| Choose a scenario, click the navigation button after reload, then submit choices and a note on the relevant follow-up | `choose-scenario-then-navigate` |
| Use the same lesson to choose the balcony and reach its distinct follow-up after reloading the navigation button | `choose-balcony-then-navigate` |
| Ask about the required format, return to the same question, then answer it | `clarify-before-answering` |
| Receive a targeted hint, revise the answer, then complete the exercise | `lf-feedback-missing-branch` |
| See evidence-based guidance with the original input hint, then submit a correction | `lf-feedback-checking-placeholder` |

## Replay regressions

| Failure or boundary | Case |
| --- | --- |
| Retired argument, missing question stem, or invalid display question | `lf-retired-prompt-02`, `lf-missing-stem-03`, `lf-wrong-binding-05` |
| Unauthored pause before a question or at a section divider | `lf-extra-pause-06`, `continue-without-authored-pause` |
| Wrong answer ID, control-only retry after withheld prose, or missing feedback branch | `lf-feedback-wrong-answer-id`, `lf-feedback-control-only-retry`, `lf-feedback-missing-branch` |
| Wrong input hint on a checking-direction response | `lf-feedback-checking-placeholder` |
| Literal markup in a code fence versus a control written into teaching prose | `synthetic-literal-control`, `synthetic-narrated-fallback` |
| Retry budget exhausted after repeated invalid calls | `synthetic-retry-exhaustion` |
| Blank submission after reload leaves the question pending | `synthetic-blank-answer-reload` |
| Two emitted controls are answered in order across reloads | `queued-choice-reload` |
| Escaped delimiters survive rendering and submission | `escaped-choice-and-input` |

The fallback and exhaustion cases report a reproduced failure. A successful
recovery is reported separately. Replay-only cases target scripted malformed
responses or host behavior that can run without a fresh model response.

An interaction step expects one emitted question by default. Set
`question_count` when the step intentionally emits more than one. The
`pending` field checks how many questions the session still holds.

Set `prose_question` to the intended question for a live check of the
learner-facing prose. The judge accepts any wording that clearly asks for the
same choice, answer, or action. When the same titled control is shown again,
the judge can use the previously displayed question to resolve an explicit
request to answer it. A related question with a different answer target fails.
A tool argument, option label, input hint, or mention of the topic alone does
not ask the learner. The tool's question binding remains a separate check.
Use `prose_meaning` when the prose should convey an instructional point with
the authored actions, conditions, and order. Use `prose_contains` for exact
tokens such as `YYYY-MM-DD`.
Use `replay_prose_once` for phrases that should occur exactly once in the fixed
replay text. A replay expectation can also use `prose_once` inside
`replay_expected`, for example to check question wording across a scripted
retry. Live runs do not apply either replay-only assertion.

The Langfuse-derived cases come from a 30-day sample ending November 13, 2026.
Tool inputs and outcomes supplied the interaction shapes and rejection reasons.
The catalog uses rewritten lesson excerpts, teaching responses, and learner
answers. Teaching prompts follow the `ai-shifu-course-creator` authoring
guidance, with runnable lesson steps and feedback based on the learner response.
The new teaching paths and corrective responses are authored fixtures. Opaque
course groups and case tags record structural provenance. The catalog omits
source identifiers, raw prompts, generated reasoning, and private metadata.

When curating a case, identify the behavior that would fail independently of
the existing cases. A different topic, paraphrased prompt, or one extra option
on the same path can use an existing representative. Keep a separate case when
the control contract, submission, sequence, feedback, or failure mechanism
changes. Use the evaluator's comparison mode for prompt regressions when the
case selection and fixture contents, evaluator settings, and repeat count
match. Check those requirements before starting a live candidate run. Counts
describe the selected fixtures.

See the [evaluator usage guide](../README.md#evaluate_mdf_interactionspy) for
commands and instructions for adding a case.

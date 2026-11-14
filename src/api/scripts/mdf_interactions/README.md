# Interaction evaluation coverage

The catalog contains 48 cases derived from 48 distinct sessions in the
production Langfuse project, spanning 17 courses and 12 observed anomalies.
The sample uses a 30-day window ending November 13, 2026 and includes 35 learning
sessions and 13 course previews. It also contains nine synthetic gap cases.
The smoke suite selects 12 of the trace-derived cases.

| Primary interaction | Langfuse-derived cases |
| --- | ---: |
| Single choice | 17 |
| Multiple choice | 1 |
| Text | 16 |
| Single choice or text | 11 |
| Multiple choice or text | 2 |
| Confirm | 1 |

| Observed anomaly | Cases |
| --- | ---: |
| Retired question argument | 1 |
| Missing question stem | 2 |
| Display question used with the wrong binding | 2 |
| Empty continuation before teaching | 2 |
| Unauthored pause followed by continued teaching | 1 |
| Feedback with the wrong answer identifier | 1 |
| Control-only retry after feedback prose was withheld | 1 |
| Missing feedback branch | 1 |
| Checking direction with an incorrect input placeholder | 1 |

The nine synthetic cases cover markup printed as a control, literal markup
inside a code fence, retry exhaustion, repeated question prose across attempts,
blank submissions, checkpoint reloads, queued interactions, delimiter escaping,
explicit display and stored values, and authored and unauthored confirmation.
The narrated fallback and queued-interaction cases are replay only. The runner
reports reproduced fallback and exhaustion separately from successful recovery.

An interaction step expects one emitted question by default. Set
`question_count` when the step intentionally emits more than one. The
`pending` field checks how many questions the session still holds.

Set `prose_question` to the intended question for a live check of the
learner-facing prose. The judge accepts any wording that clearly asks for the
same choice, answer, or action. A paraphrase or an invitation to respond can
pass. A tool argument, option label, input hint, or mention of the topic alone
does not ask the learner. The tool's question binding remains a separate check.
Offline runs check deterministic expectations only. The synthetic duplicate
question case retains `prose_once` in `replay_expected` to verify the exact
number of occurrences across a scripted retry.

Candidate observations were grouped by course and teaching interaction, and
selected traces were checked for distinct session identities. Tool inputs and
outcomes supplied the interaction shapes and rejection reasons. The catalog
uses rewritten lesson excerpts, teacher responses, and learner answers. A
synthetic follow-up advances each case through the local engine. For observed
rejections without a verified recovery, the corrective response is authored as
part of the local test. The JSON records structural provenance through opaque
course groups and case tags. Source session identifiers, raw prompts, generated
reasoning, and private metadata are omitted. The sample is designed for
regression coverage and cannot be used to estimate production rates.

See the [evaluator usage guide](../README.md#evaluate_mdf_interactionspy) for
commands and instructions for adding a case.

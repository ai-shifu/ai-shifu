# Declare the feedback branch for this returned text answer

Attach one branch to the same model response as the first learner-visible
feedback. Put the object directly in `interact.feedback` or `finish.feedback`.
Use `review` on an applicable read or memory tool already needed in that
response. A read-only lookup without prose may precede the decision. Later
responses inherit a displayed branch. Keep that branch for the rest of this
turn.

Copy `answer_id` from the current host `authored_section.answer_id` reference.
Copy learner excerpts exactly from that answer's returned input. Copy
`rule_quote` from the exact author text governing the current stage and
`criterion_quote` from the relevant clause of the current authored section.

## Structured checking direction

Use this branch for a failed, uniquely anchored text answer at an authored
checking-direction stage with a positive aspect or question count. Send one
`interact` call with no free prose or sibling calls:

- Set `type` to `text`. Copy the original input hint into `placeholder`.
  Keep `generated_control` false and omit `options` and `display_question`.
- In `feedback`, supply `answer_id`, `rule_quote`, the positive
  `aspect_limit` from the applicable lesson-wide and local rules, and
  `accepted_quotes` with unique exact excerpts that are already correct.
  Include required acknowledgements and use `[]` if none apply.
- Supply `focuses` within the authored limit. For each focus give its exact
  `criterion_quote`, an exact `submission_quote` for a contradiction (null
  for an omission), an internal `observed_issue` and one unanswered
  `guiding_question`. Keep accepted and contradicted excerpts distinct.
- Set `question` to the guiding questions in order, joined by one space on
  one line. The host carries the original question binding and displays the
  accepted excerpts with a check, contradiction excerpts and unanswered
  questions. The diagnosis and criterion are internal.

Use the current authored limit even when a local example lists more checks.
Keep each check within the selected gap and leave its reasoning unanswered.

## Ordinary feedback

Send authored feedback as visible prose alongside the tool carrying the review
object. Each review has `answer_id`, an exact `submission_quote` and a brief
internal `reason`. Use the ordinary question and binding rules for any retry
control. If a tool retry withheld the prose, regenerate the permitted feedback
with the corrected call.

- `phase: "accepted"` for a complete answer. Deliver the authored confirmation
  and explanation before navigation or finish. If the answer completes the
  lesson, send that prose and call `finish` with the accepted review in
  `finish.feedback` in the same response. For an explicit control-only exception,
  quote that exact instruction in `rule_quote` and explain it in `reason`.
- `phase: "clarification"` for a side question with no attempted answer.
  Answer it under the author's rules and return to the pending exercise.
- `phase: "authored_help"` for other authored feedback. Quote the exact
  `rule_quote` permitting it now and explain the actual correction history
  in `reason`. This includes later help, immediate or unstaged feedback,
  checking stages without an authored count and shapes requiring several
  questions within one aspect. Preserve the current stage and its limits.
  A conditional example, a prior knowledge explanation or a post-correct
  rule does not authorize skipping a required direction stage.

Grade the full submission and select the stage using the author's rules. The
host checks sources and structure. Its checks do not decide correctness or
whether a question stays within one semantic focus.

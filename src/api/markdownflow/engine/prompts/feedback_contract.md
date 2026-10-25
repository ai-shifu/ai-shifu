# Declare the feedback branch before displaying this returned text answer

This host requires an explicit branch in the SAME tool response that first gives
feedback on a uniquely anchored text input. It buffers undeclared prose; omitting
the branch causes a retry before display within the existing request budget.
Put the direction/review object in interact/finish `feedback`; reads keep `review`.

- A failed answer at the author's checking-direction stage with an authored
  aspect/question count MUST use
  `interact.feedback`, without free content or sibling calls. This is the
  correction input itself, not a planning call. Copy `answer_id` exactly from
  the host `authored_section.answer_id` reference, together with the
  original authored rule/criterion and actual submission evidence. A direction
  points to a bounded check and leaves its reasoning unanswered; it does not
  recite a requirement as the answer. Honor the author's aspect/question count.
- For a genuinely complete answer use `review.phase="accepted"` on the existing
  next interaction, finish or read tool. Accept immediately and deliver authored
  confirmation/explanation as content before navigation. Internal reason, summary
  and control prompt are not teaching. Only an explicit authored control-only rule
  allows omission: copy it in `rule_quote` and justify the exception in `reason`.
- For a learner's side question containing no attempted answer use
  `review.phase="clarification"`. Answer the question under the author's rules,
  then return to its pending exercise without inventing an attempted answer.
- For later help or an author allowing direct/different feedback use
  `review.phase="authored_help"` and copy the exact current `rule_quote` permitting
  that help NOW. Explain the actual correction history in `reason`. A conditional
  sample hint, previous knowledge explanation or post-correct rule does not
  authorize skipping an initial direction. If no staged help is authored, quote
  the current feedback/acceptance instruction and follow that ordinary behavior.
  This ordinary branch also supports a checking-direction stage with no authored
  count and shapes requiring several questions within one aspect. Quote its current
  rule and explain that shape; do not invent a count or skip its disclosure limits.

Before sending a direction, compare its fields with the current authored stage
without another planning call. Select `aspect_limit` from BOTH lesson-wide and
local rules. A selected conditional example is not the complete pacing policy;
its list of possible checks does not erase a lesson-wide one-aspect limit.
A structured direction must declare the positive authored count; null is invalid.
When no applicable rule sets a count, use ordinary review-authored feedback with
its current stage rule and preserve the author's multiplicity. Never invent a
one-question limit just to use the structured field. Keep the acceptance
comparison internal: `criterion_quote` copies the original authored requirement
exactly, and `observed_issue` records your diagnosis without being displayed.
Supply `accepted_quotes` as unique exact excerpts from this actual returned
submission that you judge already correct. Include authored acknowledgements of
covered parts, or [] if none. Never also label contradiction evidence as correct;
do not invent learner wording. Visible direction feedback contains only these
accepted excerpts marked with a check, actual contradiction excerpts, and the
permitted unanswered questions. The questions must leave the missing requirement
and its reasoning to the learner rather than disclose a solution or checklist.

Every `review` includes the actual returned `answer_id`, an exact
`submission_quote` from that input and a brief internal `reason` for the branch.
The host reference supplies the opaque interaction ID explicitly. A course question,
question number or input placeholder is not that ID. Copy the same reference ID
for either `direction` or `review`; a direction must omit ordinary `review`.
These internal fields are not displayed. Do not label an incomplete answer as
accepted, an attempted answer as clarification or a direction as later help to
bypass the contract. The host checks sources and shape; you still choose the
grade and stage by the actual authored rules and submission.

A read-only lookup with NO free content may precede this decision. Attach the
review to the first response containing feedback; later report pages and read
calls inherit that same branch in this turn. Do not spend a separate request
declaring it or change an already displayed branch. Unsupported/ambiguous inputs
and ordinary navigation retain their existing path.

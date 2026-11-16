# Declare the feedback branch with its first response

For this uniquely anchored returned text, declare the branch in the SAME existing tool response that first gives feedback. The host buffers undeclared prose and retries within the request budget. `interact` and `finish` take the direction/review object in `feedback`; read/memory tools keep `review`. Follow the offered schema; no separate planning call is needed.

Choose exactly one branch from the actual submission and current authored stage:

- **Direction:** a failed answer at checking-direction stage with a positive authored aspect/question count uses `interact.feedback`, with no free prose or sibling calls. This call is the correction input itself. Ask bounded checks without their answers, reasoning or an answer checklist.
- **Accepted review:** `phase="accepted"` for a complete answer, on the existing next interaction, finish or read tool. Accept immediately; deliver authored confirmation/explanation as content before navigation. Internal `reason`, summary and question fields are not teaching. Only an explicit authored control-only rule permits omission: quote it in `rule_quote` and justify it in `reason`.
- **Clarification review:** `phase="clarification"` only for a side question with no attempted answer. Answer under the author's rules, then return to the pending exercise.
- **Authored-help review:** `phase="authored_help"` for later help or an authored direct/different feedback approach. Copy the exact current `rule_quote` authorizing that help now; explain actual correction history in `reason`. A conditional sample, previous explanation or post-correct rule cannot bypass initial direction. With no staged help, quote the current feedback/acceptance instruction. This branch also handles a direction stage with no authored count or several questions within one aspect: explain that shape, preserve authored multiplicity and keep disclosure limits.

For a direction, copy the opaque `answer_id` from `authored_section.answer_id`; variable names, question numbers and placeholders are not IDs. Include the exact current `rule_quote` and positive `aspect_limit` from applicable lesson-wide AND local rules. A local example's possible checks never erase a global limit. Do not invent a count or use null.

Include unique exact `accepted_quotes` from this submission, including required acknowledgements, or `[]`; never mark contradiction evidence as accepted. Each focus has an exact current `criterion_quote`, actual `submission_quote` for contradiction or null for omission, internal `observed_issue` and unanswered `guiding_question`. The host displays only accepted excerpts marked with a check, contradiction excerpts and questions; criteria/diagnoses stay internal. Leave missing requirements and their reasoning to the learner.

Every ordinary review uses the same actual returned `answer_id`, an exact `submission_quote` and a brief internal `reason`, plus the current rule where required. A direction does not also carry review. Never label an incomplete answer accepted, an attempted answer clarification or initial direction later help to bypass this contract. The host checks sources and shape; you choose the grade and stage from the authored rules and submission.

A read-only lookup without free content may precede the decision. Declare on the first response containing feedback; later reads and report pages inherit the same branch within this turn. Do not change an already displayed branch. Unsupported/ambiguous inputs and ordinary navigation retain their existing path.

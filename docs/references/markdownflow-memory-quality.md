---
title: MarkdownFlow Memory Quality Evaluation
status: active
owner_surface: learner
last_reviewed: 2026-10-12
canonical: true
---

# MarkdownFlow Memory Quality Evaluation

The opt-in evaluator at `src/api/scripts/evaluate_mdf2_memory.py` supplies a
repeatable synthetic baseline for the current course model. Its thirty-four fixed
cases cover fourteen semantic admission decisions, six actual-engine recall
turns, four long-teaching-history journeys, four exercise-statistics reports and
six authored-rubric grading checks.
This is model behavior evidence alongside existing deterministic storage
and host-isolation regressions; it does not replace human teaching-quality
acceptance, persisted cross-lesson acceptance or long-term cost observation.


## Worked example consistency

The ninth frozen original-model check on sim-086140b restores a concrete
program and two iterations after native retries but still fails factual
acceptance: LOAD initializes the accumulator to 5, SUB subtracts 1, the
zero-exit test observes 4, then ADD adds 2 before the back-edge. Subsequent
zero-exit tests observe 5, 6, and so on: cycle n tests n+3 for n >= 1 under
ordinary integer arithmetic. No test reaches zero in that arithmetic; the
example specifies no overflow semantics to support its claimed eventual stop.
Four generations settle 7.82
credits; exact outputs/tokens uniquely bind actual attempt/block, with unchanged
source/classroom and no new learner or summary. Preserve this separate failure.


Before claiming a worked result or termination, the default runtime instructions
ask the model to state each example's full initial state and trace operations, including
reinitialization and branch targets, with consistent units and non-conflicting
data/code storage. Reapply reads and resets on each loop iteration; only
retained state changes can accumulate. Trace requested iterations in one state
table and derive behavior claims from it; claim termination only when that trace
reaches a stop. Check net change over each complete cycle against its exit
condition, not only locally correct arithmetic steps. Correct model-created errors before presenting them; preserve
authored, learner and quoted evidence instead of silently repairing it. Respect
the authored hint stage and state uncertainty when the result is unverified.
This is model guidance, not a host factual grader, new tool or extra request.
The restriction covers extra verification requests, while required runtime tools
and calls inside the example remain allowed. Script instructions direct teaching;
they are not text to recite to the learner.
Existing author ownership, correction/navigation rules and request/retry limits
remain authoritative.

Native SDK regressions inspect delivery on initial and resumed clarification
requests, with and without feedback contracts and session reload. Controlled
FunctionModel outputs do not establish factual model compliance. Actual deployed
model acceptance must independently check its example against its explanation;
whole fresh-classroom acceptance remains separate. The original nineteenth
failed classroom is preserved. Its generated loop reloads unchanged memory on
each back-edge and cannot terminate as claimed; do not repair stored evidence or
count a subsequent targeted success as a pass for that journey.

The first scoped actual-model check on 14be21d51/sim-e640a53 passes native
interaction delivery but fails example acceptance: no initial memory/register
values or requested two-iteration trace. It does not claim termination; retain
this separate under-specified-example failure. One generation settles 1.92
credits, with exact output/token and actual attempt/block binding; original
source and classroom state remain unchanged. No new learner or unchanged paid
retry follows. Explicit initial-state/trace guidance requires a changed deployed
candidate and separate acceptance; controlled-output tests alone cannot supply it.

The second scoped check on 2ef1c1129/sim-0cef691 also fails: its first branch
example specifies values, but the separate loop omits its counter initialization
and the requested complete two-iteration trace. Reusing the earlier counter
would exit after one iteration; do not invent a replacement value. Protocol
delivery passes, but this is not semantic acceptance. Its one generation settles
1.96 credits with exact output/token and actual attempt/block binding; original
source and classroom state remain unchanged. No new learner is created. Retain
both targeted failures and require full initial state separately for each example
before checking a changed deployed candidate; keep original input and budgets.

The third scoped check on b5e25f8db/sim-a7ff2b9 also fails: values are stated,
but the purported real loop has no back-edge. The model correctly traces its
one-pass fall-through into HALT and acknowledges it runs once, yet still presents
it instead of the requested two-iteration demonstration. Do not insert a missing
jump into stored evidence. Its one generation settles 1.99 credits with the same
exact output/token and actual attempt/block binding; source and original classroom
state remain unchanged, with no new learner. The next refinement requires
verification against requested behavior and correction before presentation, not
merely a consistent description of an example that fails the requested task.

The fourth scoped check on 8012b33f2/sim-5d88b7a supplies no displayed program
or two-iteration trace and defers requested details until the learner answers.
This is failed acceptance, not evidence of correct examples. Three generations
within existing native retry limits settle 5.75 credits with verbatim output/token
and actual attempt/block binding. The policy and original request are present in
actual generation inputs. Original source and classroom state remain unchanged;
no new learner or summary is created. Preserve the author's brief-clarification
rule. Investigate potentially conflicting correction-only host guidance without
overriding that rule or spending on unchanged-runtime resampling.

## Clarification and correction scope

The current authored reference accompanies both attempted answers and knowledge
questions. Its correction-only guidance must be explicitly limited to
checking-direction feedback, where permitted questions remain unanswered and
later reasoning is withheld. Clarification answers the actual side question
within authored brevity and disclosure rules, then returns to the pending
exercise. Include the actual question's requested examples or walkthroughs
concisely, including after native branch/control repair; a generic definition
does not replace the requested illustration. Rejected drafts remain undisplayed
and absent from persisted teaching history. This distinction neither authorizes a full solution forbidden by the
author nor imposes a new answer requirement. Exact source, history, memory,
navigation and request limits remain unchanged. Native SDK instruction/reload
tests establish delivery only; deployed teaching quality and the complete fresh
natural-compaction journey still require independent acceptance.

The phase-scoped runtime 6a3aa06d7 deploys as sim-c91e50d. Both APIs match
67 production fingerprints and pass 422 SDK checks; source and integrated sim
pass 3830 learning/script cases, 50 subtests, three expected skips and all gates.
The fifth scoped actual-model check restores explanation and traces but still
fails factual acceptance: byte addressing with two-byte instructions conflicts
with one-byte instruction placement/PC movement, and a result write overwrites
the next HALT while claiming instructions remain unchanged. Do not repair the
output by changing address units, padding instructions or moving the result.
One trace/generation settles 2.01 credits with verbatim output/token and actual
attempt/block binding; original source and classroom state are unchanged. No
summary or new learner is created. Retain all five scoped failures separately
from the original failed fresh journey.

A separate process-local capability diagnostic enables provider thinking only
for the same original-model checkpoint. Product minimum-thinking policy remains
intentional and unchanged in the serving API, course and shared configuration.
Actual trace metadata confirms thinking enabled, but the displayed answer omits
the program/two-iteration trace and defers details. This diagnostic fails the
frozen semantic check and does not show that reasoning fixes factual errors.
One trace/generation settles 2.00 credits; the existing Langfuse content field
matches billing verbatim with unique tokens and actual attempt/block binding.
Reasoning evidence is retained separately. Source and original classroom state
remain unchanged. This is neither serving-runtime nor fresh-classroom acceptance.
Do not change global reasoning policy or repeat an unchanged paid request based
on this result. A model comparison must preserve the original source, request,
standards and per-turn limits, and remain separate from course acceptance.

The frozen two-candidate configured-model comparison preserves the original
checkpoint/question/source, product parameter policy and per-turn limits. Model
2 passes this isolated example check: initialization at a distinct data cell,
two increments, a conditional back-edge and final fall-through/HALT all match its
six displayed PC/memory rows. Three native generations settle 28.52 credits.
Model 3 fails native delivery with no displayed answer after five generations;
retained tool results reject a serialized JSON string in the object-valued review
field. Do not coerce the schema or infer factual acceptance from missing output.
Its five generations settle 77.93 credits. All eight outputs/tokens uniquely bind
to actual attempt/block usage, all fees settle, source/classroom remain unchanged
and no summary/new learner is created. A diagnostic route guard initially stops
before provider usage; explicit course scope fixes only the private runner, not
product routing. Structured-output audit recovery reads existing evidence only.

This comparison changes no serving course/model or global reasoning policy and
does not close either the original model's failure or fresh eleven-question
natural-compaction acceptance. Model 2 is a candidate for a separately scoped
classroom evaluation, not an automatic course migration or a pass for #3122.

## Cases and scoring

Admission calls the product's `make_request_check`, including its actual prompt,
structured decision and request limits. Positive cases cover explicit English,
Chinese and French requests and faithful exact-code storage. Negative cases cover
ordinary preferences, quoted examples, negation, forgetting, questions,
conditional requests, invented additional traits and policy-bypass instructions.
A provider error, absent response or invalid structured decision is an evaluation
error, never a passing negative case. Each case gets a fresh admission checker.

Recall runs the real engine with a 100-character initial memory budget to omit
long values. It checks exact recall, a current value superseding stale history,
a deleted value remaining unavailable despite a historical tool return, and an
oversized value returning `too_large` without a partial answer. Each case gets a
fresh synthetic session. Two additional changed/deleted cases include an answered
named question and a serialized session round trip. These synthetic reloads do not
replace storage-backed host tests. Passing requires a current recall tool result, exactly
one expected answer after a paired exact-key read, no conflicting relevant reads,
no stale or invented project code, finished teaching,
unchanged memory and preserved original history. An unpaused content-only turn
with visible non-whitespace content gets at most one host-style continuation to finish; all earlier output and failures
remain scored, so this is not an answer retry. A plausible answer without a
current tool read fails.

The lesson asks the project question without telling the model to call recall or
warning it about stale history; the runtime policy must supply that behavior.
The fixture deliberately uses stable machine-readable project codes. These checks
evaluate fact fidelity and tool use, not natural teaching style or a complete
language benchmark. The synthetic snapshots are already authorized inputs; they
do not independently prove the host's database authorization or course isolation.
Those remain covered by the real storage tests in `test_memory_*_integration.py`
and `tests/service/profile/`.

## Authored-rubric grading cases

### Personal feedback grounding

Author-provided mistakes and sample diagnoses are possible answers, not evidence
of this learner's beliefs. Wrong-answer hints, accepted-answer explanations and
later reviews must ground personal diagnoses in original submissions for the
current question, distinguishing earlier attempts, corrections and omissions.
An omitted point does not establish an opposite or unrelated misconception.
A conditional hint applies only when its stated case matches the actual
submission. When none matches, follow the current authored stage using a
genuinely unmatched requirement instead of forcing an unrelated sample. Under
an authored one-aspect limit, select the relevant exact clause from a compound
criterion and ask about that gap alone; a paragraph is not one indivisible
requirement. Matching and focus selection remain model judgments, not host
semantic validation.
Required authored distinctions may still be taught as general examples without
claiming the learner made those mistakes. Earlier generated feedback and lossy
teaching summaries cannot substitute for original learner input; unavailable
evidence limits the personal claim. Grading criteria and retries stay unchanged.
Final reports and study advice have the same evidence boundary: an omitted item
does not prove a personal habit, belief, ability or cause. Describe the observed
omission, without narrowing away items the learner actually supplied. A corrected
submission after a supplied hint does not prove independent reasoning or effort.

Core feedback and the interaction tool also require a supporting original quote
before naming a personal misconception, including after a correction. Without
that evidence, teach the authored distinction generally.

Personal omission claims must also follow the authored equivalent-coverage rule:
compare the full submitted meaning before repeating a hint or listing a gap.
Concrete examples and their effects can cover a category without its title; an
answer still missing another concept does not make already covered points missing.
Recheck original input instead of inheriting a prior generated gap list.

Default engine prompts also append a request-local review when deferred
interaction answers are resumed, including saved-answer recovery. Before feedback,
match every authored requirement to the complete original answer, distinguish
covered, contradicted and absent points, and select hints only from genuinely
unmatched requirements. Explicit equivalent-coverage allowances apply before
checking whether a category title is present. Clarifications and navigation do
not become answer attempts. A synthetic host result for an unshown question is
not learner evidence; re-ask that unanswered question in a renderable form.
This transient guidance adds no grade, persisted
evidence, model call or request budget; custom prompt bundles can omit it.
It remains model guidance rather than a semantic validator.

For one resumed text interaction with a unique exact authored input hint, the
default engine may also copy its static Markdown section into the final
current-turn feedback instructions. The reference is supplied once, after the
feedback policies, rather than in an older learner request preceding the
unanswered question. Only its exact instruction suffix is removed when saving
new SDK requests, including interrupted teaching; learner parts, tool returns,
other instructions and original history stay unchanged. The whole enclosing section is bounded by heading
ancestry and the next authored interaction. Exact introductions from the enclosing
Markdown ancestors are copied alongside the local section, before their first
child heading or interaction. This keeps a later question's local hint near the
applicable parent instructions without copying sibling exercises. It does not
interpret precedence or infer an aspect count. The combined source remains at
most 8 KiB; no grade is selected and the script does not advance. If ancestor
context contains substitution syntax or the combined source exceeds this bound,
the reference retains only its answer binding and a full-script notice, with
null local text and no preambles. A local-only copy must not imply complete scope.
Ambiguous hints, non-standalone/multiline controls,
variable-containing sections and oversized sections retain the full script
without a focused copy. Code/comment examples do not locate an interaction.
Matching first applies the host's existing interaction normalization to a copy
of the original tool arguments: unadmitted variable names are ignored only under
the declared-key policy, and exact authored input hints are restored by the same
normalizer used for displayed controls. The raw call and answer stay unchanged.
Unrestricted memory hosts and admitted-but-mismatched bindings retain conservative
matching; normalization does not resolve duplicate anchors or enlarge the 8 KiB
bound. Ignoring a rejected key for matching never grants permission to store it.
This projection is host reference data, not learner input or memory permission;
original messages and tool-result answers are retained unchanged, including
without other history compaction. It adds no model call or request budget and
remains subject to the existing complete-request input backstop. Real-model
compliance is independently required.

Correction pacing follows the author's current hint level and aspect limit
across the entire response, including the interaction's question and placeholder.
Checking every requirement internally does not authorize exposing every gap in
one correction. An authored one-aspect hint addresses the current unresolved
aspect only; authored graduated help starts with a checking direction and deepens
as later learner responses warrant. Keep accepted points unless contradicted.
A partial correction does not pass other unmet requirements, while a complete
answer can pass immediately without artificial staged resubmissions. Scripts
that permit multiple aspects or worked solutions retain that behavior; this
policy adds no global one-aspect rule or retry limit. When complete-answer
disclosure is forbidden, a copyable passing answer, an ordered answer checklist
or a worked solution ending in "try again" still violates that boundary. A
direction-only hint points to what to examine without reciting the answer;
previous side-question help does not relax the authored restriction on correction
hints. These remain model-facing
instructions, not a semantic output filter or a host-generated hint.

At an authored checking-direction stage, feedback briefly identifies the issue
and follows the authored aspect and guiding-question limits. A one-aspect or
one-question limit uses one bounded unanswered question. Stages permitting or
requiring several aspects or questions retain that multiplicity; an unspecified
count does not create a one-question limit. Leave the questions unanswered for the
learner. A question surrounded by its worked reasoning or several explanatory
paragraphs already moves into explanation, even without disclosing the complete
answer. The generic feedback requirement does not override the author's stage.
Actual correction history and authored progression determine later steps; a
knowledge explanation counting as help in the report does not itself authorize
skipping a required correction stage. Explicit author permission for immediate
explanation or a different progression remains authoritative.

Select the feedback phase before applying a local authored hint example.
Conditional examples are alternatives for matching submitted cases, not a
checklist to combine for every wrong answer. Acceptance criteria support internal
comparison; post-correct explanations require a passing submission. The
request-local exact reference repeats this interpretation beside the original
text without editing it or deciding the grade, hint level or next step in code.
A matching local example remains subject to the lesson-wide stage and aspect
limit. At a direction stage, stop after the permitted question or questions;
follow-up subquestions must not exceed the authored count or collectively reveal
the remaining solution.

The request-only reference keeps its source text before the host phase notice.
The resumed-answer review separates failed and passing feedback branches: at an
authored checking direction with a one-aspect or one-question limit, a brief
observed issue and one unanswered guiding question are followed by the correction
input. Other authored counts remain authoritative. Worked reasoning and a transfer
method remain in the passing branch unless the author permits an earlier help
stage. These instructions do not introduce a host semantic filter or another
model request, and require separate actual-model acceptance.

### Structured checking directions

For a uniquely anchored returned text input, the existing `interact` tool accepts
an optional `direction` object when the current stage has an authored positive
aspect/question count. The model selects that count, phase and unmatched focuses. Each focus carries an exact current-section
criterion, an exact submitted quote for a contradiction (null for an omission),
an internal observed issue and one unanswered guiding question. Select one
concrete missing or contradicted requirement per focus, not a heading or coverage
checklist bundling several gaps. Diagnose only that requirement and ask about it;
a broad request for everything else missing is not one aspect just because it is
one sentence. These native-field instructions guide the model; quote provenance
and array length cannot prove semantic focus. Required
`accepted_quotes` contains unique exact excerpts from this actual submission that
the model judges correct, including acknowledgements required by the author, or
an explicit empty list. The stage rule must also quote original author text. The
host verifies these sources and the declared cardinality before displaying
accepted excerpts with a check mark, contradiction excerpts and unanswered
questions. Criteria, diagnoses, internal rules and declared limits are retained in
the original tool arguments for audit, without becoming teaching text. The host
verifies quote provenance, not correctness. Saved pending controls lacking this
new field, or with an old null/missing count, can still resume their original
answer; existing history is preserved.

The call defers the same normalized text input with an empty prompt and its
original placeholder and eligible variable. Eligibility follows that normalized
text control; both browser `values` and portable-host `text` transports, including
saved-answer recovery, provide actual evidence without their formatting prefixes. Mixed free prose, additional
tool calls, forged sources and unexecuted interaction markup reject the whole
response through the existing SDK retry budget. Built-in sibling calls are
rejected before their bodies execute, including finish and memory writes in either
order. The host neither clips a hint
nor adds a planning request. A valid first call works with a one-request budget.
Explicit multiple authored counts remain supported by the structured tool. New
structured calls cannot use null to avoid declaring a count. When no count is
authored, ordinary review-authored feedback quotes the current stage rule and
preserves the author's multiplicity and disclosure limits; no one-question rule
is invented. Passing
answers, later help, navigation, clarifications, multiple required questions within one aspect and unsupported
anchors retain
the ordinary interaction path and protocols.

The production host enables `Engine(feedback_contract=True)`. For supported
returned text answers, visible ordinary feedback or an interaction/finish must
declare `review` in that same existing tool response: `accepted`, `clarification`
or `authored_help`, bound to an actual answer ID and submitted quote with an
internal reason. Authored help also cites exact current author text permitting
that stage, including lesson-wide rules outside the current question heading.
Exact source provenance does not establish that the quoted rule applies now.
A checking-direction correction must instead use `direction`; multiple authored
guiding questions keep separate Markdown paragraphs.
Omitting the branch retries before display, including plain-text output and
prose preceding any built-in tool; invalid finish/memory siblings cannot execute.
Read-only lookups without prose may precede the decision, and later report pages
inherit it without a separate planning request. Portable hosts default to the
previous optional contract. Unsupported anchors and navigation are unaffected.
The declaration makes the model decision explicit and validates its sources;
it does not prove that the model graded the answer or chose the stage correctly.
Native review.phase guidance repeats the branch-choice boundary where the model
selects it: a local conditional hint is not permission to waive a lesson-wide
checking count, and earlier knowledge help is not a failed answer attempt. These
remain model judgments, not a new host semantic grader or planning request.

When ordinary prose has been withheld during this run, a replacement interaction
or finish cannot silently complete with only a control or internal review reason.
It must supply new visible content with its valid branch, or a successful earlier
page must already have supplied the replacement. Read-only lookups remain allowed
without content but cannot clear this delivery obligation. A valid structured
direction supplies its own rendered correction instead of ordinary prose. Calls
that never had rejected prose retain authored control-only behavior. Accepted
answers must deliver content before navigation or finish even when no earlier
prose was rejected. A successful earlier content page satisfies that obligation;
a lookup alone does not. Explicit authored control-only acceptance remains
available by quoting its exact current rule in review.rule_quote and explaining
the exception in reason. All supplied rule quotes are source-checked, without
interpreting whether the model selected the applicable rule. This checks
presence and tool success, not whether new text is a correct or complete answer;
never restore rejected explanations verbatim or increase request budgets.
When both a replacement's rule source and its missing content are invalid,
report those problems together in the existing retry. Do not mask the source
error until a later retry or spend an additional request to discover it.
The request-local pending-delivery state also keeps the complete recovery notice
on the latest retry after an earlier SDK projection has removed rejected prose.
Do not infer that recovery is complete merely because that response is absent
from the projected history. Preserve the actual validation error, require fresh
content with a native tool and applicable branch, and append the notice only
once. Successful earlier pages and raw stored evidence remain unchanged; this
does not restore rejected prose or increase the existing request/retry budget.

Accepted excerpts cannot also appear as the same exact contradiction quote in a
structured direction. Reject incompatible annotations before display and let the
existing retry select distinct correct excerpts or an empty list. This does not
grade the answer, compare overlapping text spans or invent an acknowledgement;
different model-selected correct and contradicted excerpts remain supported.

On supported resumed answers, text waits until the first new tool identifies
whether its model response uses this contract. Declared ordinary calls release the
unchanged chunks; a structured response is displayed only after validation, with
its pending correction and visible history already prepared. A host-only content
metadata field carries the complete validated turn, including earlier ordinary
chunks. It is excluded from SSE serialization. The production host commits that
state and full filtered block before displaying the first direction chunk,
including content fully held by host filters and later released during flush; a
disconnect reloads the correction rather than the original answered input. The
normal terminal path does not commit it twice. Buffered provider
failures before any display retain the original answer for recovery. This adds
response-level latency for supported ordinary answer turns but no whole-turn
report buffer. Old evidence stays unchanged; new rejected prose is retained only
in raw tool/retry evidence, not as displayed teaching.

This is structural provenance, not a semantic grader: the model can still choose
the wrong phase, misread an authored count, combine checks in one question or
misdiagnose a genuine quoted answer. Real-model pacing and complete fresh
natural-compression acceptance therefore remain separate gates. Earlier failed
probes cannot be replaced by controlled SDK success.

SDK feedback tests verify policy delivery and preservation of original attempts
through corrections and reload. Controlled responses do not establish real-model
compliance; deployed checkpoint and fresh-classroom evidence remain separate.

The report-specific prompt, calculator description and successful-calculation
reminder repeat the original-submission evidence boundary at the point of final
review. A correct evidence table does not license unsupported personal advice:
quote the actual mistake briefly or name the observed omission, without attaching
an authored diagnosis or inferred cause. Closing prose uses calculated counts.
SDK delivery regressions establish these reminders reach the model after a real
calculation; real-model compliance remains a separate acceptance check.

### Interaction tool boundary

An unexecuted standalone `<interact ...>` text tag creates no controls and is
not evidence that the learner answered. The engine suppresses complete
single-line tags outside Markdown code and asks the model to call the real tool,
under the SDK's existing bounded output retry. It never executes parsed tag
attributes or writes a named answer. A failed recovery emits an error and keeps
the lesson unfinished; `finish` cannot bypass that unresolved interaction.
Exact tag literals in the author's documents, fenced/indented code, inline
examples and ordinary HTML remain content. Inline/multiline tool imitations are
outside this deliberately narrow correction.

The first fresh eleven-question classroom after #3096 failed at its first
question because repeated tags were treated as completion. Retain that failed
classroom and its three settled requests; offline recovery controls do not turn
it into a successful full-lesson acceptance. See the
[fresh classroom plan](../exec-plans/completed/mdf2-fresh-grading-classroom.md).

On sim a7c72ea22, both API replicas match 55 source/runtime hashes. An in-memory
restore of the genuine saved pre-repeat checkpoint recovers the original first
text question: the course model repeats the tag, receives the bounded retry and
calls the real tool. Two traced generations settle 2.31 credits; prefix and
memory remain intact, with no summary request, errors or lesson completion.
Read-only checks preserve the original progress, session, variables, four blocks
and ten history elements. This scoped replay does not close fresh-lesson acceptance.

### Pre-answer help and independent first answers

Hint timing is relative to the first actual answer attempt, after skipping
`not_answer` inputs. Apply the author's definition of help: an explanation that
qualifies as a hint before the first attempt contributes to both `hints` and
`hints_before_first`. A later correct first answer remains first-correct but is
not independent-first. Formatting clarification, unrelated explanations and
post-answer teaching do not automatically count as pre-answer hints. Unknown
timing remains null. The calculator performs arithmetic on model-supplied
judgments; it does not infer semantic hints from the mere presence of a question.
The same timing guidance reaches the model in its report policy, calculator
description and parameter schema after a saved-session resume.

After #3097, the retained new learner completed all eleven authored questions in
27 normal HTTP/SSE requests with valid controls, order and correction boundaries.
All 27 visible teaching elements match stable persisted history (54 elements).
The 39 actual model requests settle 65.70 credits with matching real progress,
block and owner attribution. No actual compression occurs: maximum original
teaching is 3,412 bytes, below the unchanged 4,096-byte threshold.

The report correctly counts 14 attempts, three retries, eight first-correct and
two non-answer knowledge questions, but incorrectly reports eight independent
first answers instead of six. Both pre-answer explanations qualify as hints
under the author's explicit rules, yet the model supplies zero pre-first hints.
Keep this completed classroom as failed report evidence. A genuine saved
pre-final-answer checkpoint can verify a correction without overwriting that
history; it does not establish a new successful whole-lesson acceptance. The
[fresh classroom plan](../exec-plans/completed/mdf2-fresh-grading-classroom.md) tracks
the failed journey, scoped verification and separate successful fresh lesson.

On sim 116f7287f (API 2/2, web 1/1 Ready; 55 matching fingerprints per API
replica), a single in-memory replay of that genuine checkpoint reports six
independent-first, eight first-correct, 14 attempts and three retries. All eleven
calculator rows and the visible eleven-row report match the pre-saved expectation;
the two knowledge explanations each have one pre-first hint. All eleven traced
generations carry the timing guidance and settle 25.25 credits with matching
learner/course/lesson/owner scope and no fabricated classroom attempt IDs. No
errors or summary generation. Read-only comparison preserves original progress,
sessions, variables and all historical element rows. The failed natural report
remains failed; this scoped replay does not close fresh full-lesson acceptance.

### Fresh full-lesson acceptance after the corrections

After #3098 and the separate #3099 UI upgrade merged, a new internal learner
completed the existing eleven-question published lesson through normal HTTP/SSE
on sim f138f1fd3. Both API replicas matched all 55 merged runtime/resource
fingerprints. This was 27 requests from the first question to the final report,
without checkpoint replay, learner reset, authored-script edits or retrospective
changes to expected results. Three wrong/incomplete answers required actual
learner corrections; two knowledge questions remained non-answer inputs. The
complete five-point answer advanced without an extra peripheral requirement,
and the authored dot matrix stayed unchanged.

Before the final answer, independent expectations were saved. Four sequential
original-history pages covered all 16 relevant inputs, and all question/outcome
bindings, eleven calculator rows, visible rows and report totals matched:

| Measure | Expected and observed |
| --- | --- |
| Passed questions | 11 |
| Answer attempts / retries | 14 / 3 |
| First-correct / independent-first | 8 / 6 |
| Corrected passes / known failed submissions | 3 / 3 |
| Hint rounds / questions with hints | 5 / 5 |
| Non-answer knowledge questions | 2 |

Both qualifying pre-answer explanations contribute one pre-first hint. The
session finishes normally. One unsolicited memory attempt is refused; custom
memory remains empty and no course variable is stored. Original pre-final
messages and the script remain unchanged. All 27 visible teaching elements match
persisted history exactly; two reads return the same 54 elements.

All 35 actual model generations settle **54.21 credits**, with real
progress/block attribution, matching course-owner charges and no failed or
outstanding billable requests. This cost is separate from every earlier failed
journey and scoped replay. The model is `ark/deepseek-v4-1-flash-260910`.
Maximum original teaching is 3,712 JSON-wire bytes, below the unchanged 4,096-byte
threshold: no summary generation or summary cache occurs. This establishes one
fresh lesson's report acceptance, not natural compression, full-course, browser
rendering, other-model/language/provider, human or long-term cost acceptance.
Those wider items remain open. MarkdownFlow 1.0 is retained.

Private identities, tokens, course content, session records and billing evidence
remain outside the repository. See the
[completed classroom plan](../exec-plans/completed/mdf2-fresh-grading-classroom.md)
and [completed grading plan](../exec-plans/completed/mdf2-authored-grading-criteria.md).

### Single-choice navigation and refused report coverage

A new isolated learner starts the same published eleven-question lesson on sim
96d6b87c8 through normal HTTP/SSE. Both API replicas match 55 source fingerprints.
A substantive pre-answer explanation reaches 4237 JSON-wire bytes and triggers
one billed teaching-summary generation and one nonempty summary-cache entry at
the unchanged 4096-byte threshold. All eleven exercise answers reach their
feedback, but the final report fails; the lesson remains unfinished.

The final turn reads all ten original-evidence pages. Its 27 records include
seventeen relevant exercise inputs and ten ordinary single-choice navigation
clicks. Unlike typed confirms, those single choices remain in the evidence.
Both calculator attempts cover the seventeen exercise inputs but omit every
navigation reference from `excluded`. Exact coverage correctly returns
`invalid_coverage`, then the unchanged twelve-request budget is exhausted.
This is not proof that compression caused the failure. The 28 HTTP requests
include one terminal SSE error. All forty actual generations settle 71.82 credits
with real progress/block attribution, matching owner charges, no failed
generations and no unsettled billable requests. A successful model response is
not a successful engine turn or finished lesson.

Coverage errors now retain their status and return bounded missing, unknown and
duplicate reference lists, complete category counts and an explicit truncation
flag. At most 32 references per category are considered for the diagnostic, and
the serialized result still fits the existing 8192-byte UTF-8 limit. No raw
answers or teaching are added. Reader/tool/report instructions clarify that the
model must explicitly exclude non-exercise navigation; an option label alone
never causes automatic exclusion. Invalid calculations still clear successful
totals, and original messages, reference membership and arithmetic are unchanged.

Four new regressions fail before this correction and pass afterward, including
real SDK recovery and multibyte/escaped result bounds. An offline check of the
retained failed input identifies all ten missing navigation references; adding
their explicit exclusions permits calculation without model calls or database
writes. This is calculator recovery only. The original model judgments count
five hints where the independently saved pre-final expectation requires six;
that semantic quality gap remains separate. The original classroom stays failed,
and fresh complete compressed-classroom acceptance remains open in the
[broader classroom plan](../exec-plans/active/mdf2-broader-classroom-acceptance.md).

The correction deploys to sim 1f1e27f75 through manual Drone build 5330
(build 541) followed by automatic rollout on 2026-10-11. API 2/2 and web 1/1
are ready. Both APIs match 55 source/resource fingerprints and each deployed
image passes 43 isolated report checks, including SDK recovery. These checks
use no paid model calls or database writes and do not replace fresh acceptance.

Private trace-list retrieval timed out; no trace-input observation is claimed.
Persisted summaries and the attributed summary usage establish summary activity.
No old learner is reset, no published lesson is changed, and no replay or paid
retry relabels this failed journey as a passing natural classroom.

### Hint rounds spanning the first answer

The same retained failed classroom exposes a separate model-supplied undercount
in question 1-2. Its pre-answer knowledge explanation and later incorrect-answer
correction are two qualifying rounds under the author rules. Both calculator
attempts instead supply hints=1 and hints_before_first=1. Original records retain
both teaching rounds; the calculator correctly sums the supplied count. This is
not an arithmetic defect or proof of missing original evidence after compression.

A prompt/schema-description-only candidate still reports five hints in a
non-persisting real-model checkpoint probe on sim a77744fea. It reads all ten
pages, excludes ten navigation records correctly, and finishes, but its first
question still has total one. Fifteen teaching requests and one new summary
settle 42.72 credits. Observed gateway inputs retain one summary marker and
projected original, with the guidance present. Preserve this failed candidate;
more wording alone does not establish correct aggregation.

The tool now accepts semantic round judgments: question-level `hint_before`
classifies teaching accompanying the first submitted interaction, and each
submission's `hint_after` classifies its exact `following_teaching`. These strict
boolean-or-null flags follow the author's definition; outcomes do not imply
hints. The calculator derives total hints and before-first timing from original
answer-group positions. A shared answer group counts once per question, and
conflicting flags are refused. Unknown relevant rounds preserve null counts;
a known before-first subset can remain known when only later rounds are unknown.
A known zero total also yields zero before-first hints for an unanswered question;
nonzero or unknown totals without an actual answer retain unknown timing.
Initial qualifying teaching counts before the first actual answer, while
ordinary question instructions and post-correct analysis do not automatically
qualify. Semantic classification still belongs to the model.

Initial `hint_before` judges the first record's `teaching` and visible question
fields, independently of its `following_teaching`. A solution-helping placeholder
can qualify under the author's rules; ordinary input labels and formatting cues
do not automatically qualify. Under rules excluding ordinary
instructions, course logistics, a question-only introduction and a promise of
future hints are not delivered help. A later knowledge explanation belongs only
to that input's `hint_after`; the calculator derives whether it preceded the
first answer. Initial teaching that actually provides qualifying help still
counts. This refines model-facing evidence selection without changing schemas,
original records, semantic ownership, arithmetic or budgets.

Legacy scalar counts remain optional assertions; they cannot override or
replace round evidence. Mismatches or known assertions over unknown rounds are
refused with bounded derived-count diagnostics, and old successful totals are
cleared. Omit assertions in new calls. Stored sessions and old tool arguments
remain loadable without rewriting; new calculations use this stronger contract.
Original reference coverage, answer grading arithmetic, request/result limits,
memory permissions and authored scripts are unchanged. Hint aggregation now
comes from classified rounds rather than trusting a model-supplied total.

The final classified-round candidate is verified on sim de8cf2629, built by
push-triggered build 545 / Drone 5334. API 2/2 and web 1/1 are ready; both APIs
match 55 runtime/resource fingerprints and each passes 58 isolated report checks.
Final local checks pass: 617 engine, 3179 learning/quality (one expected skip and
four subtests), and full repository gates; sim engine/quality checks pass 663.

One genuine pre-final checkpoint probe reads ten exact pages containing all 27
original records, binds seventeen relevant inputs and explicitly excludes ten
navigation records. One calculation and the generated report match all eleven
rows and the independently saved totals: six hints across five questions,
fourteen attempts, three retries, eight first-correct and six independent-first.
The first question has two hint rounds, one before its first actual answer.
The report finishes normally. Fourteen teaching requests and one summary settle
39.65 credits with actual progress/block and owner attribution. Each observed
teaching gateway request retains the summary/projection and round-field guidance.
Original persisted session, progress and variables are unchanged, as are the
content/order of 55 history elements; a synthetic pending element ID varies on
read-only projection. No classroom state is persisted by this probe, while normal
generation metering and tracing remain enabled. Keep the earlier 42.72-credit
prompt-only failure and original natural classroom failure separately. This
checkpoint pass does not establish a fresh complete compressed-classroom pass,
other-provider readiness, or independent human acceptance.

Regression coverage includes provider delivery and reload, original long
teaching under a model-facing projection, before/after aggregation, strict flags,
initial hints, shared-group deduplication/conflicts, scalar disagreement and
unknown propagation. Fixed judgments in offline tests do not prove real model
classification. Retained real-model verification and fresh complete compressed
acceptance remain separate in the
[broader plan](../exec-plans/active/mdf2-broader-classroom-acceptance.md).

### Authored next-question navigation

Standalone text imitations of `interact` include both an opening/self-closing tag
and an empty single-line pair such as `<interact type="single"></interact>`.
The existing guard suppresses these imitations and requests the actual tool;
it never interprets attributes as a question, a learner answer or memory
permission. Finish cannot replace the unasked question, and repeat attempts
retain the same bounded retry. Inline, indented and fenced examples, exact
authored literals and nonempty HTML content retain their original behavior.
Quote-aware opening-tag boundaries preserve `<` and `>` inside attribute values and
prevent nonempty body text ending in `>` from being mistaken for an empty pair.
This recognizes a control-shaped text boundary; it does not infer course
progress or decide whether an answer is correct.

The sixth fresh learner on sim d312f7ad6 exposes the previously missed paired
shape: the first accepted correction prints navigation as text and proceeds
without a click. Stop after four ordinary requests and preserve the unfinished
classroom, thirteen history elements, one real summary and 13.00 settled credits.
No final report or complete fresh pass follows. The paired-tag correction has
nine initially failing regressions; actual model recovery and another complete
fresh journey remain separate acceptance work.

After #3103 merges as a7345f6de, a fresh internal learner on sim de8cf2629
exposes an independent order/pacing failure. Question 1-2 is explained and
corrected, but the model directly asks question 1-3 instead of offering the
script's single-option next-question interaction. Preserve all four normal
HTTP requests and 5.29 settled credits. The 4663-byte original explanation has
not yet produced a summary, so this is not successful compression acceptance.

The notation-only candidate deployed on sim 42dcaf263, build 547 / Drone 5336.
Both APIs match 55 runtime/resource fingerprints and pass six isolated SDK
checks each. The genuine pre-wrong-answer checkpoint still skips navigation
after the correct retry, despite the actual Gateway receiving the new policy.
Stop after two teaching requests, all settled at 2.75 credits with actual
progress/block/owner attribution. Original session, progress, variables and
eight history elements retain their content and order. No summary runs.
Preserve this separate failed checkpoint probe.

Notation guidance, core turn structure and the actual interact tool description
now preserve authored one-option navigation as a required single-choice
interaction after the answer's explanation. A three-turn example separates the
answer input, explanation with navigation, and the following question after the
actual selection. A correct answer or side question cannot replace that click;
proceed directly after selection without asking for another confirmation.
This is model guidance, not a host cursor or inference that every option named
next is navigation. Ordinary choices, authored retries, section separators,
existing pause permissions, grading, budgets and memory scope remain intact.
Six controlled SDK cases check policy/tool-description delivery and deferred
controls across corrections, clarification submissions and serialization.
A real MessageTurn while navigation is pending is rejected without another
model call, changed answers or a consumed option; this is not semantic Ask
handling. The core/tool delivery assertions fail before their additions.
All 623 engine tests and 3185 learning/quality tests pass, with one expected skip
and four subtests; developer tools and repository gates pass.

The reinforced policy passes narrow real-model recovery on sim ecbe49e29,
automatic build 548 / Drone 5337. API 2/2 and web 1/1 are updated/ready; HTTP 200;
both APIs match 55 runtime/resource fingerprints and pass six isolated checks
each. From the genuine turn-two checkpoint, a wrong answer waits for correction;
the accepted correction offers only next-question navigation; its actual selection
opens question 1-3 directly. All three Gateway requests receive the guidance;
the third also receives one actual semantic-summary projection/cache entry.
Three teaching generations plus one summary settle 4.27 credits, with actual
progress/block/owner attribution and no failed or unsettled generation. Original
messages/memory remain intact; stored session, progress, variables and eight
history elements are unchanged. The authored example of hard-disk/file-saving
confusion is still incorrectly attributed to this learner in feedback; preserve
that independent quality observation rather than declaring feedback acceptance.
Fresh complete compressed-classroom acceptance remains separate and open, as do
broader model/language/provider, memory/Ask, human and cost checks. MDF 1.0 remains
intact. AI findings have original-thread replies; CodeRabbit substantively reviews
functional head 76aa35e5e without new findings and reports 100% docstring coverage.

### Answer criteria

The runtime's answer-criteria policy anchors judgments to the current question's
authored requirements, including applicable lesson-wide requirements. Equivalent
wording may satisfy a criterion. Optional facts, another question's rubric and
the teacher's own earlier hints do not add pass conditions; learners cannot
rewrite the rubric. Missing or contradictory required points still need correction.
When the author requires a corrected learner submission, a teacher-supplied hint
or explanation cannot replace it or authorize advancement. Authored retry limits
still apply.
This is model guidance, not a deterministic grading oracle or a change to saved
judgments and statistics.

Six synthetic cases use the real engine to ask a question, serialize/reload its
session, submit one answer and observe the next text interaction. A complete
paraphrase without optional facts must advance, as must one with a correct
optional addition; missing program control, a learner's request to bypass
criteria, a contradictory extra claim and a missing explicitly authored
peripheral-device requirement must retry the same question. The next question
requires peripherals even when the first does not. Exact, full question prompts
make advancement observable without asking a model to grade its own output;
bare internal labels do not satisfy question delivery.
Feedback, preserved prior history, unchanged memory and a waiting interaction
without errors are also required. During both initial question setup and answer
feedback, a content-only turn gets at most one ordinary host continuation,
never another answer. Empty or failed setup is not continued. These cases use temperature zero,
2,048 output tokens and the existing twelve-request limit. Reports include the
grading evaluator fingerprint and generation settings without raw answers/output.

Offline doubles test evaluator failure detection and policy delivery after
reload; they do not establish semantic grading quality. Live selected cases and
saved-checkpoint replays remain bounded evidence for that model/context, not a
new complete natural classroom, other models/languages or human acceptance.

## Long-history cases

Four teaching cases combine an eligible older long assistant message, two recent
turns, the production semantic-summary factory, a JSON session round trip and
actual engine projection. They distinguish changed/deleted current learner memory
from a precise question about an original classroom example. The exact code is
inside the source, outside both excerpt edges. Historical answers require a paired
current-turn original page containing that code before learner output; a plausible
answer or current memory read alone fails. Current-fact answers retain the exact
recall-evidence requirement.

Three cases require a real, nonempty bounded semantic summary. A fourth explicitly
injects a summary failure to exercise cached excerpt fallback; it is not evidence
of an actual provider outage. Each case records one logical summary attempt and
requires the same derivative cache after serialization/reload, no additional
summary attempt, and the expected source-bound excerpt/summary in actual model
requests. Missing real summaries are evaluation errors even if an answer is correct.
All cases require unchanged memory, original history and finished teaching.

Teaching uses the same controlled 512-token/temperature-zero settings as recall.
Summary generation uses the production prompt and 256-token settings, with an
eight-second provider timeout/cooperative deadline and complete 40 KiB input
budget. These settings are reported separately. Teaching `usage` and completed
summary `summary_usage` are separate. Logical summary attempts remain counts,
including explicitly injected failure; actual summary generations are billed/traced
under `agent_memory_quality_teaching_summary`. They are not a cost ledger.
See [cache usage observations](markdownflow-cache-usage.md) for valid provider
coverage, unknown metadata, matching token denominators and complete-course testing.
Synthetic round trips establish cache/tool behavior, not database authorization,
complete natural teaching quality or long-term cache savings.

## Exercise-statistics cases

Two synthetic English cases resume eleven arithmetic questions after original
paired submissions, feedback and continue-button clicks. Three questions needed
one correction each. The cases place those corrections on different questions
while retaining identical totals; correct aggregate counts cannot hide swapped
first-pass results. The session is serialized and reloaded before the actual
engine produces its final report. No expected rows or totals are sent to the model.
Fixture responses stay below the teaching-excerpt threshold and no semantic
summarizer is configured. These are intentionally full-history statistics cases,
matching the observed natural failure's absence of teaching summaries. Enabling
the projection option does not establish that projection happened. The four
separate long-history cases cover summary/read behavior.

Two additional exercise cases place one older correction and hint in the middle
of an eligible long teaching part, outside both excerpt edges. One requires a
real production-factory semantic summary; the other explicitly injects a failure
and requires cached excerpt fallback, not a real provider-outage claim. Both warm
the derivative cache, serialize/reload the session, and observe source-bound
markers in actual engine requests. A projection flag alone is insufficient.
They require one summary attempt, no additional summary after reload, unchanged
original history and the same strict original-read/calculation/report checks.
A missing or invalid required summary is an evaluation error even when the final
statistics are correct. Summary usage remains separate from exercise usage.
These are selected synthetic statistics-after-compaction checks, not evidence
of a complete natural long-course or long-term fee acceptance.

The author requests one JSON object (plain or in a single Markdown JSON fence)
containing per-question first-result booleans,
attempt and hint counts, plus aggregate counts. Scoring rejects missing/duplicate
questions, duplicate JSON keys, invalid scalar types, wrong per-question assignments and inconsistent
totals. The evaluator now enables the product exercise tools and requires complete
original-evidence pages plus an evidence-correct calculation before any report
text. A correct report that skips those tools fails protocol acceptance. Calculator
labels may be the fixture numeric ID, exact original question prompt or exact
original teaching title; every reference must still belong to that same original
question. Wrong titles or swapping equally graded answers between questions fail.
It also requires actual completion, unchanged memory and preserved original
history. A successful finish with wrong statistics remains a semantic failure.
Invalid report formatting fails checks; provider/engine errors remain evaluation
errors. The report stores checks and usage, never raw model output or attempts.

These controlled cases use temperature zero and a 2,048-token cap, separately
reported as `exercise_generation_settings`; other families retain their settings.
They use the existing 15-second gateway timeout/deadline and twelve-request limit,
with at most one host-style completion turn. They are evidence checks, not a
natural-course grading benchmark or deterministic enforcement of model output.
The product now offers session-local original submission reads and a calculator
that validates exhaustive, unique references and chronological attempts. Counts
come from question rows, not model arithmetic. Following teaching stops at the
next user/continue or accepted-answer boundary and before the next interaction
call. It remains exact context, not an extracted grade; a combined text part may
also introduce the following interaction. Shared answer-group markers identify
simultaneously answered questions. No language heuristic splits that original text.
Known zero total hints establishes zero hints before the first answer. Semantic
grades, question grouping
and hint identification remain model judgments. Unknown hint counts remain null.
No profile or course memory is written, and no persistent grading ledger is added.

### Knowledge questions are not answer attempts

A new natural eleven-question journey completed in 28 HTTP turns, but its report
counted two knowledge clarifications as unverified answers: sixteen attempts and
five retries instead of fourteen and three. The original calculator also reported
two unverified submissions. Preserve this failure. All 38 actual requests settled
for 67.95 credits with real progress/block/owner attribution. The longest teaching
part was 4,055 JSON-wire bytes and no semantic summary existed; this is not a
compressed-history test or evidence that compression caused the counting error.

The existing SubmissionJudgment now accepts not_answer for a knowledge question
or clarification containing no attempted answer. Its original reference remains
covered in chronological order, and a separate non_answer_messages count makes
the distinction visible. It does not add an attempt, retry or failure, or replace
the first real answer. Unverified real answers still count as attempts. A wrong
attempt accompanied by a question remains graded; learner requests cannot erase
errors. Classification and hint judgments remain model-supplied, without a new
classifier or keyword filter. Original references, byte bounds, exhaustive
coverage, memory isolation and actual wrong-answer counts remain protected.

Zero non-answer fields are omitted from both rows and totals; absence means
zero, so old reports do not lose byte capacity. Devin's 41-question case fails
before this correction. Four count cases fail before the outcome change;
615 engine/evaluator cases and 3,176 learning/profile/evaluator cases plus four
subtests pass, with one expected skip. Sim abc0d39c0 has both API replicas Ready
and all 44 expected runtime hashes matching functional source 62fd4c25f.

One non-persisting replay of the original pre-report pause reads all sixteen
accepted inputs and correctly classifies both knowledge questions as not_answer.
All eleven final question rows match the originals: fourteen attempts, three
retries, three known wrong attempts, eight first-correct, three corrected and five
hints. Original messages, memory, completed progress/session and variables remain
unchanged. Twelve successful replay requests settle for 31.53 credits with real
course/lesson/owner attribution and no fabricated classroom IDs. This passes the
narrow correction, not a new complete classroom or compressed-history journey.
Functional CI and CodeRabbit review pass; documentation increments are checked
separately. Earlier failed evidence remains retained.
See the [clarification-count plan](../exec-plans/completed/mdf2-exercise-clarification-counts.md).
The synthetic scorer accepts only exact fixture IDs, prompts, teaching titles or
short arithmetic titles; it still independently checks each answer's original
question membership. Calculation diagnostics are fixed status enums, without
raw tool arguments, output or exception details.
Results are bounded to 8 KiB of UTF-8 JSON; over 200 accepted submissions, ambiguous
pairing or oversized reports are refused explicitly. The existing overall input
budget still applies; per-result bounds do not bound cumulative history.
Portable Engine hosts retain the old tool set unless they opt in. The AI-Shifu
lesson entry enables it for classroom and preview in read and listen modes.

The retained natural eleven-question failure was replayed without persistence.
The original runtime passed 0/3; an earlier reader-only prototype passed 1/3.
The first calculator prompt was skipped (1/3 final reports correct); a stronger
protocol then exposed the diagnostic six-request cap (two errors). With the
product twelve-request limit and final candidate, fresh replays passed 3/3 with
complete source reads, correct calculation, matching final rows/totals, no engine
errors and no memory writes. These are original-history replays, not three new
classroom journeys, independent human tests, or deterministic grading guarantees.
The evaluator initially rejected exact original prompt/title labels; their
normalization plus reference grouping rescores six unchanged captured outputs
6/6, with a subsequent fresh final-source selected CLI run passing 2/2. Earlier
failing reports remain retained privately, not relabeled as new passing runs.
The additional compacted exercise cases now cover summary success and injected
failure/cache fallback with selected synthetic evidence. Natural-course
statistics after semantic-summary compaction, other models/languages and
independent human acceptance remain separate items. Full-catalog repetitions on
the current course model are recorded below; they do not close those other items.

## Complete current-model baseline: October 10, 2026

The unchanged twenty-eight-case catalog passed three complete repetitions
(**84/84**, zero evaluation errors) on `ark/deepseek-v4-1-flash-260910`, from
01:24:00Z to 01:29:59Z. The evaluator and fixtures came from merged revision
`6bbae6ecc`, including the original-message/part binding added in `d7cf9ba6b`.
All twenty-eight report fingerprints match that checkout. Both ready sim API
replicas (`sim-6002c01`) match the twenty-five runtime fingerprints. Contributor
scripts ran from an isolated temporary directory, importing the unchanged
installed runtime; no candidate prompt or engine overrides were used.

| Case family | Fixed cases | Repetitions | Passing results |
| --- | --- | --- | --- |
| Semantic admission | 14 | 3 | 42/42 |
| Current-memory recall | 6 | 3 | 18/18 |
| Long teaching history | 4 | 3 | 12/12 |
| Exercise statistics | 4 | 3 | 12/12 |
| Total | 28 | 3 | 84/84 |

There were eighteen logical summary attempts: twelve completed provider requests
and six explicitly injected failures that make no summary-provider request.
Summary and excerpt evidence, serialized cache reuse, exact original reads and
per-question statistics passed the existing checks in each relevant repetition.
The observer rejects known references copied into later responses or wrong parts;
its eight offline position cases include four demonstrated pre-fix failures.

Read-only reconciliation found 252 actual gateway rows: 42 admission, 75 recall,
61 teaching, 62 exercise and 12 summary requests. Diagnostic request counts agree
with that ledger count, but the ledger independently establishes billing. Every
row is attributed to the dedicated learner, validated course/lesson and resolved
owner; no classroom progress/block IDs were fabricated. There are zero failed
rows or unsettled billable successes. Settled cost is **135.19 credits**, separate
from earlier natural-classroom and selected-case runs. This is one complete
synthetic evaluation cost, not a per-lesson price or long-term savings estimate.

The initial report, observational diagnostics and ledger evidence are retained
privately, with no real memory or classroom-session persistence. The isolated
remote directory was removed after evidence was copied and verified. This result
does not replace natural-course statistics after compaction, storage-backed
journeys, real Bot/knowledge-base/Workflow acceptance, other models/languages,
human teaching-quality feedback or long-term cost observation. Earlier failures
remain historical evidence; this passing run does not relabel them.

## Running

From `src/api` in the backend environment:

```bash
python scripts/evaluate_mdf2_memory.py --list
python scripts/evaluate_mdf2_memory.py --live \
  --course COURSE_BID --lesson ACCESSIBLE_LESSON_BID \
  --learner DEDICATED_TEMPORARY_LEARNER_BID \
  --repeat 3 --output /tmp/mdf2-memory-quality.json
```

Use an environment already enabled for 2.0 and an accessible published lesson.
The evaluator refuses a 1.0 deployment and resolves the model through the same
course-selection/access path as teaching. It supplies only synthetic inputs and
never loads real learner memory or calls the session/profile persistence path.
Existing shared-gateway usage, billing and tracing still occur, attributed to the
provided dedicated learner, validated course and published lesson under
`agent_memory_quality_admission`,
`agent_memory_quality_recall`, `agent_memory_quality_teaching`,
`agent_memory_quality_exercise` and the separate
`agent_memory_quality_teaching_summary` generation. Shared settlement resolves
that course's owner; normal billability and built-in-demo exemptions still apply.
Generation names distinguish these synthetic costs from natural classroom costs.
No classroom progress/block IDs or learning mode are fabricated. Earlier rows
created before course attribution was added remain unchanged; do not infer their
course from a learner ID alone. The evaluator does not modify the engine switch.

`--case ID` may be repeated to diagnose selected cases; `--repeat` accepts 1–5,
defaulting to one. Recall deliberately uses controlled temperature 0 and a
512-token cap, recorded as recall_generation_settings, rather than the course
temperature and unbounded teaching output. The admission judge uses its actual
product settings. These are bounded fact/tool checks, not an identical-settings
production teaching benchmark. A subset report has `full_catalog=false` even when every selected
case passes. Each admission case has the product judge's one-request limit. Recall has
a six-request limit per turn and at most two turns including automatic completion. Gateway requests use a 15-second provider timeout and cooperative deadline
with SDK retries disabled; this is not a hard wall-clock deadline for an entire
case. The fixed suite runs sequentially to bound concurrent provider load.

The private, atomically written JSON report records denominators, repetitions,
per-case assertions, errors, UTC start/end times, elapsed times, usage where
available, course selection and resolved model, optional checkout source commit and hashes of the evaluator, fixture, judge prompt and runtime.
It contains no credentials, learner IDs, raw requests, responses or provider errors.
Usage is the judge/engine's diagnostic counters where available, with completed
summary responses reported separately. Optional cache coverage distinguishes a
valid reported zero from unknown metadata. These counters are not a billing or
cost ledger; use shared-gateway accounting/traces for those acceptance decisions.
The runtime image need not include Git: file fingerprints remain available.
A failed case remains in the report; it is never silently removed or converted
into a successful retry. Exit codes: 0 for a complete passing selected run,
1 for semantic/assertion failures, 2 for invocation/provider/response errors.

For a complete baseline, use the complete catalog with three repetitions and
retain the initial report. Diagnose failures with a separate selected-case report;
compare source fingerprints before combining evidence from different versions.

## Current evidence rule

With memory recall enabled, the system rule and tool description both require
current verification of learner saved facts, preferences and project details,
even without the word "remember". A learner question about a remembered fact requires
an exact current-turn read even when earlier teaching contains an answer. Earlier
recall results and the first memory block are historical evidence. A current
`unavailable` or `too_large` result must not be replaced by the historical value.
For prior exact-key reads, the engine also compares their latest results with
the current authorized snapshot. Changed, removed, excluded or compacted facts
receive a revalidation notice in current instructions and, when a current prompt
exists, beside that prompt in an explicitly marked host memory context. It names
at most 20 whole keys within 1,024 JSON characters; no values are copied into the
notice. A fresh matching read clears the dynamic instruction notice. Accepted
learner input and current-turn write authorization remain verbatim and exclude
host context. Original stored messages remain unchanged.
This addresses updates and deletions without rewriting stored teaching history
or changing the host's authorized snapshot.
Current-memory revalidation is scoped to current-fact questions. An explicit
question about what appeared in earlier teaching uses original historical evidence;
today's memory must not replace an earlier quote or example. Exact historical
codes, equations, quotations and decisions require `read_teaching` when projected,
even if a lossy overview appears to contain the answer. Historical reads neither
restore deleted memory nor authorize writes.
It requests a relevant read for memory questions, not an exhaustive memory scan.
This is model guidance, not deterministic output enforcement. Retain intermittent
violations as failed quality evidence; a passing run cannot erase an earlier failure.

Default contextual text follow-ups also expose the same bounded `recall` tool.
Current saved-fact answers require a fresh relevant read, using key discovery
when necessary. An update or menu deletion in another lesson invalidates old
answer/save-confirmation claims as current evidence. Explicit historical
questions can still quote the original conversation without restoring memory.
The final model-facing question carries a fixed host revalidation reminder;
stored messages and raw learner write evidence remain unchanged. A current
missing or different value cannot establish that an earlier save failed or
that the learner never supplied it, so the answer must not invent that cause.
The follow-up run keeps its authorized snapshot in user memory so a same-turn
accepted write is visible to subsequent recall. Read-only calls do not invoke
semantic write admission. Follow-up request/tool limits cover the snapshot's
actual byte-bounded discovery pages, one exact read and three write attempts
(plus up to three new pages). Write attempts remain capped at three separately;
ordinary answers still need only one model request. Preview no-write rules
remain unchanged. External provider-only answers and Live do not acquire
these tools. See the [natural follow-up plan](../exec-plans/completed/mdf2-natural-memory-follow-up.md)
for the initial failing journey and candidate acceptance.

### Remaining natural answer quality

The merged current-value fix does not close causal or chronological quality.
Three final natural answers reported the correct current value but invented
that an earlier save failed, did not overwrite a value, or never happened.
Those transcripts remain failed evidence. Future quality acceptance must
preserve historical statements without inferring a past operation's outcome
from the current snapshot alone. Current-value correctness does not erase
these failures or establish full memory, human or provider acceptance.

The [follow-up evidence plan](../exec-plans/completed/mdf2-follow-up-memory-evidence.md)
adds explicit provenance guidance to the system instructions, final-question
projection and follow-up-only recall description. Found establishes the current
value only; unavailable does not mean never saved, and too_large does not mean
absent. Historical assistant confirmations are not write receipts. Answer a
current-memory question directly without an unsolicited historical diagnosis;
when explicitly asked for a cause, acknowledge that it is not established.
Only the current run's remember result supports an acknowledged write outcome.
This remains model guidance requiring natural validation. It does not alter
recall's exact byte-bounded results, learner authorization or stored messages.
An exact follow-up read also carries a separate fixed host interpretation after
the unchanged tool return. Current absence uses present-tense wording; do not
claim a value was never saved or list unrelated profile fields. Exact historical
quotes must come verbatim from learner messages, not assistant suggestions;
label paraphrases and acknowledge when original wording is unavailable. The
post-read context is excluded from raw write permission evidence and still
counts toward the gateway's total input budget. The first candidate's fresh-
lesson and quotation failures remain failed evidence, not overwritten retries.

The corrected sim sample has four correct current-value answers and an explicit
unknown-cause answer without the earlier false save diagnoses. Eighteen requests
settle completely (10.25 credits), with correct answer/progress/owner attribution
and all 184 original elements preserved. This is narrow current-memory/causal
acceptance only. Initial failures, including the first candidate's 17 requests
(9.43 credits), remain recorded. Verbose suggestions and a generic unrelated
field list in the final why answer remain quality observations.

### Remaining exact follow-up quotations

Both new natural samples correctly name the earlier analogy but present an
assistant's suggested request as the learner's verbatim original. Stronger
quotation guidance did not fix this. Exact-quotation acceptance remains failed
and is the next separate evidence-grounding task, not part of the narrow
save-cause acceptance. Preserve the original messages and failed responses.
Read-only reconstruction of the final sample found that the actual last ten
sidecars were all assistant answers: query ordering compared run-local counters
across requests. Order sidecars by their original question row IDs, binding
answer snapshots through ask_element_bid so late updates stay in their turn.
Unlinked legacy rows retain insertion order. History limits and anchor scope
remain unchanged for both text and Live consumers.

Native text follow-ups expose learner_quotes over immutable original user-role
messages in that authorized window, captured before host projection and excluding
the current question. Keep raw text in new ask blocks/events and the existing
sidecar payload.user_input; retain brace escaping only in transport prompts.
Pass proven quote sources separately through the internal context/factory; a
user role alone does not prove verbatim input. Synthesized classroom joins,
embedded legacy history and old brace-bearing text without raw provenance are
unavailable as exact sources. Do not guess at legacy decoding or rewrite old
records. Existing brace-free canonical text asks are unchanged by historical
escaping and can be exact sources. Live transcripts are trimmed during
persistence and require explicit raw-input provenance; otherwise they are
unavailable as exact sources while remaining general conversation context.
Results include source index, learner role, before_current_question relation,
oldest_to_newest order and explicit supplied-history-only coverage. A separate
SDK ToolReturn host notice follows the JSON result to distinguish the current
question from an earlier identical question; assistant timing assertions are
not evidence. The total gateway input limit also counts that notice, which
cannot grant write permission. Page complete messages within 8192 UTF-8 JSON
bytes; an oversized message reports too_large, never shortened wording. Reserve
read calls in the existing Agent budget. Exact quotations must copy available
source content verbatim; missing originals mean unavailable in this context,
not that the learner never said them. Assistant suggestions and current memory
cannot substitute. Reading historical save requests grants no write permission
and must not restore deleted notes. No additional DB history is loaded.

See the [quotation plan](../exec-plans/completed/mdf2-follow-up-learner-quotations.md).
The first new candidate (18da49cdc / sim 5ea6b4011) quotes exact complete text
but misstates its order relative to an earlier identical question in two answers.
Both remain failed evidence. Seven questions completed; fourteen requests settled
for 7.7 credits, with correct new-answer attribution. All 200 original elements,
nine lessons, eleven progress rows, nine finished sessions, profile and unrelated
memory survive. Deleted-current-memory, missing-source and literal-brace checks
hold. Explicit current-relative metadata and the late notice are the next
correction; six relevant assertions fail before it. The final candidate (291df6c57 / sim f0108018c) passes three new complete
quotation answers: first ask, identical repeated ask and post-deletion ask, with
correct chronology relative to the current question. Four HTTP questions complete;
nine actual requests settle for 4.7 credits with real new-answer attribution.
All 214 original elements, nine lessons, eleven progress rows, nine finished
sessions, profile and unrelated memory survive. The temporary preference remains
deleted. Both ready sim APIs match 42 runtime hashes. User merged #3088 as
2ba2420f7; this closes only the narrow quotation/chronology task. First-candidate
verbosity and unrelated profile disclosure remain quality observations; other
models and human acceptance remain open independently.

### Follow-up usage attribution

Text follow-up model requests, including memory admission and guardrail
replies, use the new answer block's generated_block_bid. Create the frozen
UsageContext after that placeholder is allocated and flushed, before model
or provider execution. Preserve the actual progress, user, course, lesson,
scene and learning mode. The question's block and historical teaching anchor
must not stand in for this answer. Guardrail audit records still identify the
learner's question. Existing usage rows are not backfilled. See the
[follow-up attribution plan](../exec-plans/completed/mdf2-follow-up-block-attribution.md)
for regression and live-ledger acceptance; this does not change settlement,
transaction ownership, external provider-only routing or Live behavior.

## Release boundary

A passing suite does not complete the entire memory milestone or authorize a
production switch. System-registered profile fields remain global; ordinary course
variables, named answers and explicit remembered notes remain course-local. No
custom cross-course sharing is restored by this evaluator. Historical data and
engine 1.0 remain until their separate acceptance and retirement conditions hold.

### Natural-language text controls

Text-bearing interactions must remain writable when the model omits a hint.
The legacy UI uses a nonempty placeholder to expose its text box, so the host
renders absent or whitespace-only hints through shared learner-language text.
Explicit hints, prompts, options, variables and stored specs remain unchanged;
this presentation fallback does not guess an authored question or an answer.

Blank free-text values, including a nonempty list of empty strings, keep the
original question pending without model execution or answer/memory writes.
Real answers retain their original whitespace. Confirmations and named choices
that intentionally store an empty value preserve their existing meanings.
See the [text-control plan](../exec-plans/completed/mdf2-natural-text-controls.md)
for current component, saved-session, sim and CI evidence. This reported bug takes
priority before the next natural compressed-statistics journey; it does not close
that acceptance item or authorize 1.0 deletion.


The same missing-hint correction applies to narrated interaction spans emitted
without a typed tool call. Add only an escaped localized hint; require parsed
options, variable and selection semantics to remain identical, and leave existing
hints/choice-only spans byte-for-byte unchanged. SDK whitespace preservation means
text as received by the engine; the browser's existing trim/deduplication contract
is unchanged. Blank browser input is already removed before `_turn_input`, so it
cannot choose an empty-valued option accidentally; explicitly selected empty SDK
values remain valid.


### Natural compressed classroom: report-tool compliance

After #3092 merged, a new internal learner completed the eleven-question course
in eighteen successful HTTP requests and nineteen engine turns. A genuine
4,110-byte explanation crosses the unchanged 4,096-byte threshold; later turns
retain one successful semantic-summary cache entry. This establishes actual
natural compression, unlike the earlier short-history sample. The final report
still fails: it calls neither original-submission reads nor the calculator,
miscounts a knowledge question, and contradicts its own per-question table.
Four questions required corrections, while the summary claimed three. Preserve
this failure; compression occurring does not establish that it caused the defect.
All twenty-one actual requests settle for 30.35 credits with real classroom and
owner attribution. No original learner is reset and no SQL writes are performed.
The teacher also required peripheral devices beyond the authored five-point
criterion; retain this separate quality finding. Hardware multithreading was
initially misidentified as another expansion, but the full saved lesson explicitly
requires it. Original pass/fail reporting fidelity does not validate the teacher's
underlying grading or authorize changing the criteria.

Opted-in reporting now appends request-local host status to model instructions.
It names the next contiguous original-history page, then the calculation step,
then only successful calculator totals. Out-of-order/invalid reads cannot advance
that status; invalid/oversized calculations cannot provide successful totals.
Only a successful post-read calculation supplies those totals. Earlier calculator
responses retain compatibility but require recalculation after reading. A latest
SDK schema rejection invalidates old success even when the function was not called.
The real SDK sees the state changes on successive requests. State lives only in
Deps and resets for the next run; original messages, answers, semantic grades,
tool-result byte limits, schemas and portable defaults remain unchanged.
The reminder applies only when the script requests statistics and does not add
reports to ordinary lessons. This is model guidance, not deterministic prevention
of reporting or finishing without tools. A same-turn final answer still needs
feedback before evidence reads and reporting. After delivering the report, finish
when the script is complete. A script request to remember the report cannot bypass
the existing declared-or-learner-requested memory policy, invent a summary key, or
justify retrying refused writes. A candidate replay produced correct rows/counts
but exhausted its unchanged twelve-request budget attempting that unauthorized
write; retain the unfinished failure while validating this completion guidance.

The final report-turn replay succeeds with exact totals, normal finish and no
memory-write attempts; #3094 is merged. See the
[completed compressed-statistics plan](../exec-plans/completed/mdf2-natural-compressed-statistics.md)
for retained failures and bounded validation, and the
[authored-grading plan](../exec-plans/completed/mdf2-authored-grading-criteria.md)
for the separate grading drift and completed fresh-lesson follow-up.
A non-persisting replay of a real pre-final-answer checkpoint
must be identified as such; it cannot relabel the failed classroom or establish a
new full-course/human acceptance. Initial trace reads failed; the supported trace
API through the observed internal service later returns eighteen traces and all
twenty-one generations. Fourteen actual teaching requests contain a semantic
summary bound by position and content hash to the original 4,110-byte source.

# Hide extra interaction questions in reading mode

## Purpose / Big Picture

Reading and Debug show interaction controls without appending the native
question as extra prose. The question travels as `interaction_question`
metadata; interaction `content` contains controls only. Listen/classroom title
presentation belongs to the dependent PR #3340. The canonical contract is
[`learner-listen-playback.md`](../../product-specs/learner-listen-playback.md).

## Progress

- [x] 2026-11-04 CST: Split shared transport and reading behavior from the
  listen/classroom title renderer; preserve metadata, history and answer IDs.
- [x] 2026-11-04 CST: Use `interaction_question` consistently for question
  presentation, keeping the existing engine tool/session schema unchanged.
- [x] 2026-11-04 CST: Require ordinary course/Profile questions in Markdown
  prose before `interact` in the same response, with one concise instruction.
- [x] 2026-11-04 CST: Remove Profile question fallback and prose matching;
  interactions contain controls only, including recovery and queued questions.
- [x] 2026-11-04 CST: Complete preceding-head validation: 3,749 local engine,
  Profile and course-host tests, then 15,995 backend CI tests (20 skipped).
  Applicable checks passed and both actionable review threads were resolved.
- [x] 2026-11-04 CST: Remove the old-frontend compatibility prefix producer,
  all frontend prefix stripping and tests specific to that removed layer.
  Affected backend coverage passes 259 cases and reading/Debug coverage passes
  295 frontend cases; type checking, lint and all-file repository gates pass.
- [ ] 2026-11-04 CST: Verify metadata-only question transport and current-head
  CI/review, then await maintainer acceptance without automatic merging.

## Surprises & Discoveries

The earlier compatibility layer placed encoded question text in wire content
and removed it in updated clients. The user explicitly removed that layer.
The final contract sends pure controls and keeps the question in metadata.
The concise question-first instruction supplies visible and spoken questions.

Removing separate question CONTENT events also removes their independent audio
and marker elements. Authored narration and its audio remain intact.

## Decision Log

- Keep the listen/classroom title UI and cache in the dependent PR. This PR
  supplies metadata without placing it in the interaction body in any mode.
- Serialize canonical controls unchanged. Do not encode or prepend question
  text and do not strip prefixes in frontend consumers.
- Keep metadata persistence, answer identity and replay behavior. Do not infer
  or delete authored or historical prose.
- Profile emits only controls; the shared system instruction owns asking the
  question. No local question matching or extra model call is introduced.
- Keep the question-first instruction concise. Existing authored-input,
  navigation and structured-direction rules retain their responsibilities.
- Use `question` for presentation wording. Actual system/course prompts and
  the existing engine `interact(prompt=...)` schema retain their meaning.
- This changes existing-content placement, with no new action or analytics
  meaning. Questions never enter analytics.

## Outcomes & Retrospective

The reading/shared contract is isolated from title presentation. The removal
of the compatibility layer is under validation. PR checks are the live source
for current-head acceptance; maintainers own merge and deployment.

## Context and Orientation

`agent/legacy_protocol.py` creates interaction events with question metadata.
`learn_dtos.py` serializes them, and formal/preview sidecars persist metadata.
Reading uses `ContentBlock`; Debug and shared learner consumers parse the
original control content directly. The engine system prompt supplies the
question-first rule to both courses and Profile questionnaires. Profile
interaction projection returns normalized controls without a question fallback.

## Plan of Work

Remove the prefix producer and reading/Debug consumers together, verify the
shared contract, then rebase and simplify dependent title consumers.

## Concrete Steps

Run affected learning serializers/history tests and focused reading, print,
Debug and history frontend tests. Run frontend type checking, lint and all-file
repository gates. Push the reading change and rebase the title branch with an
exact remote lease, preserving its separate scope.

## Validation and Acceptance

DTO, SSE and refreshed-history interaction content stays exactly the controls;
question metadata survives serialization, storage and replay. Reading, mobile,
print and Debug show controls without the metadata question. Authored narration,
system/payment/feedback classification, answers and IDs remain intact. No
question encoder or prefix-stripping helper remains. The dependent PR alone
uses question metadata as the listen/classroom panel title.

## Idempotence and Recovery

No migration or dependency bump is required. Existing stored prose and exact
request replays remain unchanged. Remote rebases use an exact lease.

## Interfaces and Dependencies

Optional `interaction_question` carries the question separately from control
content on run events and element payloads. Producers and consumers use that
same metadata contract. The dependent title PR reuses the existing
`markdown-flow-ui` title API without a helper or package release.

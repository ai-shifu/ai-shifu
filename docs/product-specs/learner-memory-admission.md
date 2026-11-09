---
title: Learner Memory Admission
status: implemented
owner_surface: backend
last_reviewed: 2026-11-08
canonical: true
---

# Learner Memory Admission

AI-Shifu's MarkdownFlow 2.0 host enables admission at its single engine factory.
The portable engine retains its optional default and unrestricted recording
instructions for other hosts; system and tool instructions select the same policy. The existing
profile writer and the session's unit of work remain responsible for persistence.

The model supplies `question` for each answer interaction. For a leading
`?[{{key}} ...]` binding, trim leading and trailing whitespace inside the braces
and use the resulting text as the exact question and storage key. This applies
to short labels as well. A later `{{key}}` reference reads that same entry.
For exercises without a binding, the model supplies the question from the
lesson prose or context. Reusing the exact question updates the current
answer. Navigation and confirmation clicks do not record answers. Existing
percent-prefixed declarations have the same meaning. Earlier questions and
answers keep their original storage keys and history.

For writes through `remember`, a key declared by a leading binding in the main
script is eligible. Briefs, reference documents, ordinary `{{key}}` references,
and existing stored keys do not themselves grant permission for those writes.
Information saved by an explicit request remains course memory and does not
acquire a fabricated question or answer provenance.

An edited draft can carry forward a percent-prefixed system declaration already
present in its previous revision. Restoring a stored version preserves those
declarations from the selected version. Imports create new lesson identities and
cannot introduce system declarations.

For an undeclared note, `remember` must quote a complete accepted free-text input
from the current model turn as `request` (at most 4096 characters). Enabled hosts
make this field required in the model-facing schema; declared keys may supply null.
Portable hosts retain the optional field and unrestricted recording policy. An independent
structured model check must confirm both a direct affirmative request to remember
and a faithful proposed value. Casual preferences, ordinary answers, fabricated
quotes, option displays/stored values, hypothetical or quoted requests, negations
and requests to forget are insufficient. Pending multi-question inputs survive
session serialization and failed resumes, then clear after a successful model
response. Rewind restores only the checkpoint's pending evidence; legacy
checkpoints supply none.

The semantic check uses the existing billed/traced GatewayModel with the course's
model and selection metadata, including preview usage classification. It has no
write tools. Duplicate checks share results; at most three distinct checks run
per host request, each with one model request, no validation retries and a
512-token output limit. Errors or uncertain results refuse admission and teaching
continues. Semantic interpretation remains probabilistic; exact input grounding,
reserved keys, lifecycle, scope and capacity guards are deterministic.

Admitted undeclared requests use user scope within the current course. They cannot
write `sys_*` or any key the profile writer routes globally. The only global
profile keys are `sys_user_nickname`, `sys_user_language` and
`sys_user_background`. Former built-ins `language`, `sex`, `birth` and `avatar`
follow ordinary course scope and admission rules. The generic `sys_` authoring
restriction has no exception for `sys_user_style`. Existing stored course
definitions keep ordinary key/scope reads and writes; value writes do not create
missing definitions, and supplementary reads exclude undefined `sys_` keys.
Active legacy system declarations retain their canonical profile mapping in
both published lessons and ordinary draft preview. A write to one of those
account fields can therefore affect the same account in other courses.
Custom course memory stays scoped to the current course.
Only the agent's memory reader opts into additional current-course variable rows;
other consumers retain definition-based runtime resolution. The supplementary
projection considers only the newest 100 unresolved course keys and includes whole
values fitting 32768 JSON characters, counting escaping. Existing canonical/defined
variable resolution remains exact and does not consume this allowance. Oversized or
older supplementary values remain stored and available through the existing memory
inspection reader. A later lesson that explicitly references an oversized text
answer can use [bounded recall pages](../references/markdownflow-memory-recall.md)
to read its original text when needed. Normal-sized references retain their
existing behavior.

Existing key/value/count and per-scope JSON growth limits also apply. After an
asynchronous check, capacity and finished state are checked again before mutation.
A refusal emits no persistence update. Session state and accepted memory updates
commit or roll back together. Named answers and old snapshots are not truncated.

Ordinary draft preview and published learning use the same admission and
persistent memory for the signed-in account and course. Each turn uses the
declarations from the script version it runs, including in free follow-up
questions. A value saved from one version can be recalled by the other, and an
admitted write to the same key can replace it. A draft-only key can stay in
memory after the draft changes or is published. Retaking from either classroom
entry point retires the shared attempt without deleting memory. A follow-up
started in a retired attempt cannot persist updates. The editor debug simulator retains independent state.

See [Course Memory Management](course-memory-management.md) for viewing and
deletion.

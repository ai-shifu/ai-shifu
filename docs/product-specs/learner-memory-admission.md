---
title: Learner Memory Admission
status: implemented
owner_surface: backend
last_reviewed: 2026-10-07
canonical: true
---

# Learner Memory Admission

AI-Shifu's MarkdownFlow 2.0 host enables admission at its single engine factory.
The portable engine retains its optional default for other hosts. The existing
profile writer and the session's unit of work remain responsible for persistence.

A lesson may record a key declared as `%{{key}}` in its main script, outside
fenced examples. Briefs, reference documents, `{{key}}` substitutions and existing
stored keys do not grant write permission. Named interaction answers require the
same declaration and retain their exact original values and existing scope rules.
An undeclared interaction variable is dropped without dropping the question.

For an undeclared note, `remember` must quote a complete accepted free-text input
from the current model turn as `request` (at most 4096 characters). An independent
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
write `sys_*` or any key the profile writer routes globally, such as `language`,
`sex`, `birth` or `avatar`. Declared keys retain existing profile mapping semantics.
Canonical account fields remain authoritative. There is no cross-course sharing.
Only the agent's memory reader opts into additional current-course variable rows;
other consumers retain definition-based runtime resolution. Existing course rows
remain readable without fabricated provenance or a historical data purge.

Existing key/value/count and per-scope JSON growth limits also apply. After an
asynchronous check, capacity and finished state are checked again before mutation.
A refusal emits no persistence update. Session state and accepted memory updates
commit or roll back together. Named answers and old snapshots are not truncated.

Viewing/deletion, author-declared cross-course sharing, independent human course
acceptance and a hard budget for all injected context are separate follow-up work.

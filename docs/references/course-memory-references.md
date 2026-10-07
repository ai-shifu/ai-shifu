---
title: Explicit Course Memory References
status: in-progress
owner_surface: learner
last_reviewed: 2026-10-07
canonical: true
---

# Explicit Course Memory References

Authors can explicitly read a learner's custom value from another course belonging
to the same course owner with `{{course:SOURCE_COURSE_ID:VARIABLE_KEY}}`.
The source ID is a 32-character lowercase hexadecimal course business ID.
For example, `{{course:0123456789abcdef0123456789abcdef:learning_goal}}`
reads that learner's `learning_goal` from the specified course. It does not
replace or merge the destination course's own `learning_goal`.

This first cross-course increment is read-only. Values remain in their original
course; learners view and delete them using that course's existing memory controls.
It introduces no account-wide memory, shared writer, database schema, automatic
same-name merging or destination-course variable copies. Progress is never shared.

Only references in currently published author content are eligible. Each runtime
request also names the references in its current lesson script or effective
teaching brief; a declaration in another lesson cannot inject that source value.
The memory/profile facade returns no cross-course values without an explicit
author-document context. Parse separate documents separately so their code fences
cannot change each other's meaning. Draft edits,
fenced examples, HTML comments, learner messages and model-produced names do not
authorize a read. Normal authoring automatically registers variable definitions;
a reference must have a current destination-course definition. Teacher debug can
still use explicit simulated preview values; it does not read another learner.
Both MarkdownFlow runtimes use the shared profile/memory reader.

The source and destination must both have live published and current owner
records, agree with their current owner records, and belong to the same nonempty
owner. Collaborator access alone is insufficient. Reads use the requesting
learner's ID and the latest source-course row by ID, including deletion markers.
No global fallback, system/profile keys, self-reference or recursive reference is
allowed. Missing, deleted, unpublished, transferred or unauthorized sources remain
unknown. At most 32 distinct references are considered per read.

The `course:` namespace is read-only and cannot be collected using `%{{...}}`,
written by `remember`, named answers or profile settings, or shadowed by a local
stored value. The memory adapter removes rejected assignments from its update
payload; 1.0 answers retain their history and normal progress without announcing
a variable update for a discarded reference. Resumed 2.0 lessons refresh their initial memory and exact author
substitutions on every request, including source updates, deletion and permission
revocation. Existing classroom conversation remains historical evidence.

Whole values remain exact; existing memory-section and complete-input budgets
still apply. This feature adds no provider calls. Shared writing, owner-scoped
shared storage and automatic semantic recall remain separate follow-ups.

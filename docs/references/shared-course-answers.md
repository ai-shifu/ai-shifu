---
title: Explicit same-owner shared course answers
status: implemented
owner_surface: learner
last_reviewed: 2026-10-08
canonical: true
---

# Explicit same-owner shared course answers

A 2.0 published main lesson can collect a fresh answer directly for an existing
custom variable in another course belonging to the same course owner:

```markdown
?[%{{share:0123456789abcdef0123456789abcdef:learning_goal}} ...Your updated goal]
```

The source ID is 32 lowercase hexadecimal characters; the source key uses letters,
digits, underscores and hyphens, starting with a letter or underscore. The entire
alias fits the existing 255-character variable-key limit. Source and destination
require active definitions, matching current/published nonempty owners and live
courses. The source must already contain a live value for the requesting learner.
The current published destination lesson must declare the collection outside code
fences and HTML comments. A read, another lesson, a brief, learner text, a model
name or a draft does not authorize a shared write. At most 32 aliases per request.

Only accepted named answers write back; `remember`, including explicit learner
requests, and profile settings cannot write either shared aliases or `course:`
references. `course:` remains read-only. Normal 1.0 named-answer writes refuse
both reserved aliases while preserving answer history/progress. Preview, debug and
regenerated-input replay cannot write shared values. A newly submitted answer after
rewind may write if authority and the source are currently eligible.

Before a model run the host captures exact source versions. Inside the session
save transaction it locks/rechecks owners, publication, definitions and source
versions, then uses the existing profile writer. Deleted/missing/changed sources
are never created, restored or overwritten by an in-flight answer. Rejected
assignments retain the full classroom answer while clearing that alias from
current memory. Failed session saves roll back source writes too. No provider
calls are made inside this persistence transaction.

Values stay in the source course. Its existing learner memory controls view/delete
them. No destination copy, global fallback, progress sharing or owner-wide store
is introduced. Local stored aliases cannot shadow source values. A later explicit
`{{share:SOURCE_COURSE_ID:key}}` read resolves the latest authorized value when
published destination main content contains that read and the current author
context requests it; resumed 2.0 sessions refresh substitutions without rewriting
historical classroom conversation. Ordinary `course:` reads continue to work.

This adds no schema, configuration, dependency or frontend protocol. It does not
complete shared model-authored notes, owner-scoped memory or semantic summaries.

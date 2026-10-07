---
title: Lesson Memory Context
status: implemented
owner_surface: backend
last_reviewed: 2026-10-07
canonical: true
---

# Lesson Memory Context

AI-Shifu's MarkdownFlow 2.0 host bounds the JSON payload of its initial `<memory>`
section to 32768 characters, including JSON escaping and indentation. Session and
user scopes share this allowance after merging, with session values winning.
Canonical/profile values and learner-requested course notes share the same final
projection. Variables collected by this lesson remain excluded as before.

Whole values whose keys are referenced outside fenced examples in the script or
teaching brief, and host-reserved account keys, are considered first. Within each
priority group, input dictionary order is stable. Oversized entries are skipped;
smaller later entries may still fit. No partial value, summary or invented fact is
substituted. When values are omitted, a static model-facing notice says that an
absent key is unknown in this context, rather than forgotten or deleted.

Exact `{{key}}` substitutions in the main script and brief retain their complete
values. Named interaction answers, tool results, profile rows and session memory
are not truncated or deleted. Consequently this allowance is not a token limit
or a cap on the complete prompt: repeated substitutions, learner messages,
teaching material and growing conversation history remain separate follow-ups.

Resuming a legacy session projects only the engine-owned initial memory section
in a request-local copy. JSON decoding identifies its boundary even if a value
contains `</memory>`. Saved historical messages remain intact; only new run
messages are appended after success. Failed requests retain history and deferred
answer evidence for retry. Later learner messages resembling tagged sections and
tool results are not rewritten. The nickname refresher shares the structural parser,
retains omission notices and uses saved full values to recognize exact substitutions
that were omitted from JSON. Literal tags in values are never treated as projection
metadata. Unrecognized historical formats retain the
existing compatibility behavior rather than guessing which content to alter.

The portable engine defaults to no projection limit. The single AI-Shifu factory
enables the limit for both learner and teacher-preview requests. There is no new
configuration, dependency, migration, cross-course sharing or persistence policy.
The supplementary database-reader budget from
[learner memory admission](learner-memory-admission.md) remains an independent
earlier filter; the final section limit also covers canonical and session values.

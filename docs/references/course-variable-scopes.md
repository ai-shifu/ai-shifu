---
title: System and course variable isolation
status: implemented
owner_surface: learner
last_reviewed: 2026-10-29
canonical: true
---

# System and course variable isolation

System-recognized profile fields are global to the learner. For example, the
canonical nickname and language remain consistent between courses. Registration
in the shared profile-label mapping determines global scope; a `sys_` prefix alone
never grants global storage or arbitrary profile editing. Existing registered
legacy label names keep their mappings.

All other durable variables belong to the current course. Two courses can use
the same key with different answers. If course A records that a learner likes
hamburgers, course B does not receive that fact, even when its lesson concerns
food or both courses have the same owner. Course B asks its own question when
needed. A missing course variable never falls back to a global custom-variable
row. No automatic account-wide memory is introduced.

## Authored memory key names

MarkdownFlow variable names are opaque text keys. Read from `{{` to the first
literal `}}`, trim the body's leading and trailing Python whitespace, and
require a nonempty result without C0/C1 controls or U+2028/U+2029. Preserve
internal spaces, repeated spaces, punctuation, Unicode, quotes and backslashes
exactly. There is no expression evaluation, quote decoding, backslash decoding
or recursive recognition of markers inside a key. A literal `}}` remains a
reserved sequence and cannot be part of a name.

For example, `?[{{ What is your gender? }} Male | Female | Private]` stores the selected
answer under `What is your gender?`. `{{ What is your gender? }}` references that same key.
`user  name` keeps its two internal spaces. Generate markers with padding on
both sides (`{{ key }}`) to preserve a key ending in a single `}`. FEFF is key
content, not trim whitespace. The exact trim set and shared conformance cases
are owned by the [coordinated MarkdownFlow specification change](https://github.com/ai-shifu/markdown-flow/pull/11).

Names are case-sensitive and are not normalized. Changing a question or its
punctuation creates a different key; it does not rename an existing answer.
A question key is a course variable unless it exactly matches a registered
system key, so this example does not update the system `sex` field.

Both frontend editors use the shared `remark-flow` name helper rather than
independent character whitelists. The Python library and vendored engine run
the same conformance corpus. Assignment and reference markers share name
recognition; option separators are parsed after the complete assignment marker.
A `]`, `|`, `//` or `...` inside that marker is key content, not an interaction
operator. An interaction's variable name is not its displayed
question: write the learner-facing question separately when exact wording is
required.

The wider rule intentionally recognizes some markers that older parsers
treated as plain text, including names with internal spaces. Existing ordinary
identifiers and literal quote/backslash keys retain their identity. Invalid
markers remain literal text and do not expose nested variables. Definition
create/save and browser submissions trim using the same rule, while existing
stored memory is not migrated. Machine-only format placeholders in
`learn/utils_v2.py` have a separate restricted contract and are not teaching
prompt memory keys.

Author scripts, teaching briefs, follow-up prompts, learner requests and model
output cannot grant cross-course access. Both runtimes and follow-up context use
the same scoped profile reader. The current-course supplement can read permitted
local notes without definitions; it never merges another course or undeclared
global custom values. Ordinary `remember` remains declared-or-requested within
the current course and retains its capacity/deletion rules.

The former `course:` and `share:` aliases are retired. Entire namespaces,
including malformed and old saved names, remain blocked for profile/settings
writes, memory patches, model notes and named answers. Template formatting does
not resolve them, even from a supplied dictionary. The shared-answer host grant
and source-version writer are removed rather than left behind a runtime switch.

Resuming a saved 2.0 session clears retired aliases from current memory and
initial substitutions, including the original structured memory prompt. Pending
old shared questions still accept an answer as classroom evidence but do not
write either course. Original answers and later classroom history remain intact;
previously delivered content is historical evidence, not current shared memory.
Preview/debug sessions also discard retired snapshots. No historical data or
source-course values are deleted, migrated or retroactively undone.

This policy supersedes [explicit references](course-memory-references.md) and
[shared named answers](shared-course-answers.md). It adds no schema, dependency,
configuration flag or frontend protocol. Sim remains 2.0; production stays 1.0.
Semantic history summaries and full quality/cache/cost acceptance remain separate
work. Cross-course model notes and owner-wide custom storage are cancelled.

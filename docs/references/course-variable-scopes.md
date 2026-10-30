---
title: System and course variable isolation
status: implemented
owner_surface: learner
last_reviewed: 2026-10-30
canonical: true
---

# System and course variable isolation

Only `sys_user_nickname`, `sys_user_language` and `sys_user_background` are
registered global profile fields. Their canonical account values remain
consistent between courses. The shared exact-name registry determines global
scope; a `sys_` prefix alone never grants global storage or arbitrary profile
editing.

The former built-ins `sex`, `birth`, `avatar` and `language` are ordinary course
variables. Historical global definitions and values remain stored but are not
advertised, read as defaults, or mapped to account fields. Their names do not
block automatic creation of course definitions. Legacy `sys_user_style` answers
also use course scope: existing published courses can create a missing local
definition during normal answer persistence. This narrow runtime compatibility
does not permit new authored `sys_` questions. All non-system variable writes
require a course identifier. Account avatars, language settings and canonical
learner profiles keep their separate APIs.
Only `sys_user_language` selects teaching language; an authored `language`
variable is independent and is never overwritten by that selection.

All other durable variables belong to the current course. Two courses can use
the same key with different answers. If course A records that a learner likes
hamburgers, course B does not receive that fact, even when its lesson concerns
food or both courses have the same owner. Course B asks its own question when
needed. A missing course variable never falls back to a global custom-variable
row. No automatic account-wide memory is introduced.

## Product wording and compatibility

The overall product feature is "Memory". Its entries have a question-and-answer
structure backed by the existing key and value. The teacher's learning simulator
labels its panel "Memory" and distinguishes simulated answers from personal
information such as nickname and teaching language. The learner's course-scoped
collection remains "Course memory". This display structure does not establish an
original interaction: saved answers and explicit requests to remember information
do not all have evidence of an original question. Do not invent questions or
answer provenance for those entries.

System memory fields use localized labels throughout the simulator, including
tooltips, input names and placeholders. Hovering or focusing never reveals their
internal keys; an unknown system field uses the localized Memory label. Authored
course questions and legacy custom keys retain their existing text and identity.

This wording keeps the existing technical key/value contract. Within a course,
entries with the same exact key share the current value across lessons. Changing
the key creates a different entry and does not transfer an existing answer.
Changing only the displayed question does not change the key. Existing identifiers
are not rewritten into questions, and no new question identity or answer-history
model is introduced. API fields, storage, cache keys, runtime prompts and analytics
contracts retain their existing names and behavior.

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

A complete question can also bind and reference a free-text answer:

```md
What would you like to learn?

?[{{ What would you like to learn? }}...Share your goal]

Use {{ What would you like to learn? }} to choose a relevant example.
```

The existing percent-prefixed form
`?[%{{ What would you like to learn? }}...Share your goal]` binds the same key.
Neither form changes the memory admission rules or requires historical keys to
be written as questions.

Names are case-sensitive and are not normalized. Changing a question or its
punctuation creates a different key; it does not rename an existing answer.
A course question key must not start with the case-sensitive prefix `sys_`.
That namespace is reserved for the system, including unregistered names.
Draft saving, parsing, history restoration, import and publication reject
reserved question bindings in both `?[{{sys_name}} ...]` and
`?[%{{sys_name}} ...]` syntax after trimming outer whitespace. Ordinary question
keys remain course variables. Neither this example nor a variable named `sex`
updates an account field.

Body references such as `{{sys_user_nickname}}` remain valid and do not create
course-owned definitions. Code examples, comments, escaped interactions and
other literal Markdown are not question declarations. Existing stored answers
and published courses are not migrated or deleted; a historical draft with a
reserved question must be corrected before it can be saved or published again.

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
markers remain literal text and do not expose nested variables. Automatic
definition creation and browser submissions trim using the same rule, while
existing stored memory is not migrated. Machine-only format placeholders in
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

Restored database-backed lesson sessions also refresh host-injected retired
profile defaults in current memory and initial prompt snapshots. Current-course
values, accepted classroom answers and later history remain intact. Editor debug
previews do not run this compatibility cleanup or persist its marker. Restarting
a preview creates a fresh debug session; unused cache entries expire after thirty
minutes. Continuing an existing preview retains that session's cached state.
Legacy learning style no longer prefills the canonical learner-profile editor;
nickname compatibility remains available.

This policy supersedes [explicit references](course-memory-references.md) and
[shared named answers](shared-course-answers.md). It adds no schema, dependency,
configuration flag or frontend protocol. Sim remains 2.0; production stays 1.0.
Semantic history summaries and full quality/cache/cost acceptance remain separate
work. Cross-course model notes and owner-wide custom storage are cancelled.


## Memory definition API type compatibility

The definition list has no type filter. Requests use `parent_id` for course scope;
legacy `type` query parameters are ignored. Listed definitions retain the fixed
`profile_type: "text"` response and the existing `profile_type_str` label for
compatibility.

The manual definition endpoints are removed:

- `POST /api/profiles/add-profile-item-quick`
- `POST /api/profiles/save-profile-item`
- `POST /api/profiles/delete-profile-item`

Requests to these unregistered paths receive the standard JSON not-found response
with `code: 404`. Saving MarkdownFlow content still automatically creates missing
definitions through the shared internal helper, including its legacy text-table
fallback. Definition listing, usage inspection, hiding and restoring remain
available. Existing keys, scopes, stored answers and legacy text rows remain
unchanged. Learner course-memory deletion and personal-profile editing use their
own APIs and remain available.

The fixed text fields describe memory definition metadata. Single-choice,
multi-choice and free-text controls continue to follow the authored MarkdownFlow
interaction syntax.

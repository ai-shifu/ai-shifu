---
title: System and course variable isolation
status: implemented
owner_surface: learner
last_reviewed: 2026-10-08
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

The [public MarkdownFlow specification](https://markdownflow.ai/docs/specification/variables/)
currently documents a narrower letters/numbers/underscore rule. The behavior
below describes the existing AI-Shifu 2.0 implementation and its frontend
compatibility, not an amendment to that public specification.

Use the existing 2.0 name rule in teaching prompts and frontend editors: a name
is nonempty and contains no whitespace or braces (`[^{}\s]+` in Python).
Question marks, other ordinary punctuation and Unicode characters are valid.
For example, `?[%{{你的性别是？}} 男 | 女 | 秘密]` stores the selected answer
under the exact key `你的性别是？`; `{{你的性别是？}}` references that value.
The key is case-sensitive, and punctuation is not normalized. Changing a
question or its punctuation creates a different key; it does not rename an
existing answer. A question key is a course variable unless it exactly matches
a registered system key, so this example does not update the system `sex` field.

Both frontend editors use the shared `remark-flow` name helper rather than
independent character whitelists. That helper follows Python whitespace
semantics as well as the visible punctuation rule. Assignment and reference
markers share name recognition; option separators are parsed after the
assignment marker. An interaction's variable name is not its displayed
question: write the learner-facing question separately when exact wording is
required.

Existing interaction delimiters still apply: a closing `]` ends the
control. This repair does not add escaping or new delimiter syntax inside key
names. The older Python backend remains deliberately more permissive about
some whitespace, braces and multiline inputs for compatibility; those inputs
are not new frontend authoring syntax. Machine-only format placeholders in
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

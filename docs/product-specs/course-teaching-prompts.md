---
title: Course Teaching Prompts
status: implemented
owner_surface: shared
last_reviewed: 2026-11-04
canonical: true
---

# Course Teaching Prompts

The course teaching prompt is the only author-configurable teaching instruction.
Chapter and lesson teaching prompts are retired, including nonempty historical
values. A lesson no longer overrides its course or inherits instructions from
an ancestor chapter. An empty course prompt resolves to no authored teaching
instruction. Engine rules and lesson script content retain their separate roles.

Teaching and follow-up requests use the appropriate draft or published course
version. Existing publication pinning, course boundaries, permissions, and
outline availability checks remain authoritative. Removing outline instruction
inheritance must not remove these checks.

Resuming a saved Agent session refreshes its instruction bundle and identifiable
engine-owned constraints in the initial model message to the course prompt,
including removal when it is blank. The saved lesson script, extra documents,
initial learner input, and subsequent conversation remain intact. Historical
messages whose host constraints cannot be distinguished from learner-authored
text are preserved rather than guessed at. Before the later schema cleanup,
these ambiguous legacy sessions need a separate reset or migration policy;
application field retirement alone cannot safely reinterpret their text.

Chapter and lesson settings expose title, permission, and visibility controls
as appropriate to the outline type. Their APIs and DTOs omit `system_prompt`.
Legacy clients may send it, including through bulk creation, but the server
ignores it. Loading old nonempty values does not expose an editor or trigger
an automatic settings save.

Publication, draft revision comparison, copying, and backup export do not
read or copy outline `llm_system_prompt`. Backup import ignores that legacy
outline field. Course-level prompts still round-trip through backups. Operator
details show only the course prompt and its `course` source (or an empty source
when the course prompt is blank); cost estimates count only that prompt.

This application cleanup retains the existing outline teaching columns and
their empty defaults until a separate schema migration. Historical database
rows and saved history are not rewritten. Reverting this stage can still
restore the old application behavior without a database downgrade.

Outline `ask_llm_system_prompt` is distinct: it stores generated follow-up
context, including learned and upcoming lesson summaries. Its publication,
backup, and runtime behavior remain in use, along with outline follow-up
enablement. Course-level follow-up prompts and internal temperatures also
remain effective. The outline temperatures were already removed by Alembic
revision `fde432bceab4`; they require no additional application cleanup here.

Settings analytics and the retirement of prompt-edit reporting are defined in
[Web Umami Contract Remediation](web-umami-contract-remediation.md#chapter-and-lesson-settings-save-outcomes-2026-11-04).

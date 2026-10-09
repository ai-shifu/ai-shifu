# Inventory MarkdownFlow 1.0 dependencies without retiring them

## Purpose / Big Picture

Make the remaining 1.0 entry paths and the infrastructure shared with 2.0
reviewable. The user explicitly authorized inventory only on 2026-10-09.
Do not delete code/data, extract runtime modules, change flags, or remove rollback.
The dated evidence belongs in the
[runtime inventory](../../history/mdf2-legacy-runtime-inventory-2026-10-09.md).

## Progress

- [x] 2026-10-09: Inspected teaching, ASK, preview, persistence, navigation,
  routing, publication fields, and dynamic service registration on main 9057bb429.
- [x] 2026-10-09: Reused the existing static import inventory and passed 46
  existing learning boundary tests without runtime changes.
- [x] 2026-10-09: Wrote the dated evidence with preservation boundaries and
  explicit limits; separated inventory from quality acceptance and retirement.
- [ ] 2026-10-09: Publish the documentation-only PR after generated indexes,
  repository harness, developer-tool check, and full pre-commit gates pass.
- [ ] 2026-10-09: Inspect reviews and reply to each independent AI opinion in
  its original discussion; human merge remains separate.

## Surprises & Discoveries

Full deployment enablement still permits no-script 1.0 fallback and old-client
block preview. ASK uses the legacy host beside agent teaching. Agent recording
and rewind use generated blocks/elements, and navigation still consumes
`block_position`. Service modules are dynamically imported at startup, making
absence of a static importer a weak deletion signal.

## Decision Log

- Inventory only: no removal or runtime restructuring is authorized.
- Record source evidence, not a list of files declared safe to delete.
- Use main 9057bb429 as the reproducible baseline; exclude unmerged #3064.
- Do not deploy a documentation-only change to sim or alter production.
- Keep real-course and external-provider acceptance outside this docs PR;
  record those results in the development workspace, without learner credentials.

## Outcomes & Retrospective

The inventory corrects the assumption that full 2.0 routing makes the 1.0 host
and generated-record tables obsolete. Existing boundary tests pass. Publication
and original-thread review disposition remain to be recorded in the PR. This
work does not complete a retirement milestone or authorize its implementation.

## Context and Orientation

The main surfaces are `src/api/flaskr/service/learn/runscript_v2.py`,
`context_v2.py`, `routes.py`, `agent/lesson_record.py`, and `agent/rewind.py`.
TTS models, course publication, dynamic module loading, and the learner chat
hook provide additional consumers. The dated inventory links those sources.

## Plan of Work

Trace actual entry paths, classify mixed/shared dependencies, verify existing
boundary tests, and publish only the inventory, this plan, and generated doc
indexes. Any separately requested runtime cleanup starts with a fresh audit.

## Concrete Steps

1. Run the existing import-graph script and inspect the runtime call sites.
2. Run the two boundary test modules listed in the dated inventory.
3. Stage the new Markdown documents, regenerate knowledge indexes, and run
   `python scripts/check_repo_harness.py`.
4. Run `python scripts/check_dev_tools.py` and
   `lefthook run pre-commit --all-files`; inspect the final diff for docs only.
5. Commit with the repository identity, push to GitHub origin, and create a main
   PR. Review inline comments, reviews, and issue comments; reply in place.

## Validation and Acceptance

Every claimed active boundary has a current source consumer. Existing tests
pass, generated knowledge artifacts match, and the repository gates pass. The
diff contains only docs, with no application, schema, dependency, or deployment
changes. An inventory does not establish production usage rates, full quality
acceptance, or the safety of future deletion.

## Idempotence and Recovery

All inventory commands are local static reads or offline tests. Index generation
is repeatable. Reverting this PR affects documentation only. Preserve unrelated
worktree files and private test evidence; do not stage logs, tokens, or learner
records. No environment recovery or database rollback is needed.

## Interfaces and Dependencies

Preserve engine selection, ASK, old/new preview, existing SSE/element contracts,
TTS readiness, generated records, agent sessions, progress/navigation, metering,
and course publication. The current
[follow-up context contract](../../references/follow-up-classroom-context.md)
remains authoritative; the inventory introduces no replacement interface.

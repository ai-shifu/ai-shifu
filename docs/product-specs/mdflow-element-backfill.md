---
title: MDFlow Element Backfill
status: implemented
owner_surface: shared
last_reviewed: 2026-04-17
canonical: true
---

# MDFlow Element Backfill

## Goal

Backfill `learn_generated_elements` from existing `learn_generated_blocks`
using `markdown_flow.format_content(...)` as the canonical block-to-element
splitter.

## Scope

- Process only Markdown-Flow block types:
  `MDCONTENT`, `MDERRORMESSAGE`, `MDINTERACTION`, `MDASK`, `MDANSWER`
- Persist only `learn_generated_elements`
- Ignore legacy TTS audio records and do not emit audio events
- Keep batching at the `progress_record` level so each progress backfill can
  commit or roll back independently

## Rules

- Content and error blocks are split with `format_content(...)`
- Interaction blocks persist one `interaction` element using
  `block_content_conf`, with `generated_content` reused as `payload.user_input`
- Follow-up backfill only accepts immediate `MDASK -> MDANSWER` pairs, or
  `MDASK -> MDCONTENT` fallback pairs when the next teacher block has the same
  `position`
- Follow-up pairs bind to the latest finalized non-follow-up content element
  emitted earlier in the same progress backfill
- If no reliable anchor exists, skip the follow-up pair and report it instead
  of inventing an anchor

## Persistence Notes

- Default mode skips block groups that already have active element rows
- Overwrite mode retires active rows for the matched block group only
- Backfill uses the listen adapter’s element path for compatibility, then
  removes same-run inactive provisional rows so the result stays element-only

# Next Chapter Auto-Advance Tasks

## Discovery & Alignment
- [x] Agree on the workflow rule: finish each task atomically, run the relevant self-tests immediately, and create a commit before moving to the next task.
- [x] Clarify with product whether “一节” = child outline node and “一章” = catalog node to ensure our logic matches the structure returned by `get_outline_item_tree` (`src/api/flaskr/service/learn/learn_funcs.py`). (Confirmed via existing data model: catalogs map to chapters, nested lessons map to outline leaves.)
- [x] Audit the current Markdown Flow authoring patterns to confirm where a lesson is marked completed so we know the earliest safe point to inject the “next chapter” interaction. (Completion occurs when `RunScriptContextV2._current_attend.block_position` reaches `len(block_list)` and `_get_next_outline_item` emits `LearnStatus.COMPLETED`, followed by `_render_outline_updates`.)
- [x] Inventory all client surfaces (new markdown-flow chat at `src/cook-web/src/app/c/[[...id]]` plus any legacy `ChatComponents`) that must react to `_sys_next_chapter`. (Current hits: `useChatLogicHook`, `ChatComponents`, `ChatInputButton`, course constants, and legacy `NewChatComp`.)

## Backend – Interaction Emission
- [ ] Add an i18n key (e.g. `server.learn.nextChapterButton`) under both locales in `src/i18n` so the button label is not hardcoded in Chinese.
- [ ] Extend `RunScriptContextV2` (`src/api/flaskr/service/learn/context_v2.py`) to detect when a leaf outline item finishes (either via `_get_next_outline_item` returning the next sibling or `LEARN_STATUS_COMPLETED`) and enqueue a `GeneratedType.INTERACTION` event whose markdown is `?[{label}//_sys_next_chapter]({label})`.
- [ ] Ensure the injected interaction persists by creating a `LearnGeneratedBlock` row via `init_generated_block` with `type=BLOCK_TYPE_MDINTERACTION_VALUE`, `block_content_conf` set to the markdown button, and a deterministic `position` (e.g. last block index + 1) so history queries stay ordered.
- [ ] Guard against duplicates on re-run/reload by checking whether the latest active `LearnGeneratedBlock` for that outline already contains `_sys_next_chapter` before inserting a new one.
- [ ] Update `_render_outline_updates` (or a helper) so that when the current outline completes and the returned update list already triggers a chapter switch, we still emit the button before handing control back to the client.

## Backend – Records & APIs
- [ ] Re-enable and modernize the fallback logic in `get_learn_record` so completed lessons that existed before this feature still append a virtual `_sys_next_chapter` interaction when no persisted block is found.
- [ ] Make sure `GET /api/learn/shifu/<bid>/records/<outline_bid>` serializes the new block with `block_type=interaction` so Cook Web history loads it.
- [ ] Verify `run_script` SSE responses stream the interaction chunk-by-chunk (CONTENT → BREAK → INTERACTION) so the UI can display the button without waiting for a new request.
- [ ] Consider a backfill job or admin script if existing learners need the record inserted into `learn_generated_blocks`; document the approach if we decide not to backfill.

## Backend – Testing & Tooling
- [ ] Add unit/functional tests around `RunScriptContextV2` (or a slimmer service seam) that simulate completion and assert one `_sys_next_chapter` block is persisted and streamed.
- [ ] Add tests for `get_learn_record` ensuring the fallback interaction appears only when progress status is `LEARN_STATUS_COMPLETED`.
- [ ] Update or add fixtures covering the new i18n key and any markdown-flow snapshots touched by the change.

## Frontend – Lesson Navigation (markdown-flow chat)
- [ ] Update `getNextLessonId` in `src/cook-web/src/app/c/[[...id]]/hooks/useLessonTree.ts` to return the next lesson inside the same chapter before falling back to the first lesson of the next chapter, so requirement “自动跳到下一节” is satisfied.
- [ ] Ensure `useChatLogicHook.onSend` handles `_sys_next_chapter` by calling the updated `getNextLessonId` and gracefully no-ops when there is no upcoming lesson (e.g. show toast).
- [ ] Confirm `mapRecordsToContent` renders the persisted interaction button (both in desktop and mobile `appendCustomButtonAfterContent` paths) without needing manual intervention.
- [ ] Verify SSE live streaming inserts the button in the tracked list as soon as the backend emits it, keeping scroll/auto-play behavior intact.

## Frontend – Legacy Chat Components
- [ ] For `ChatComponents.tsx` + `ChatInputButton.tsx`, decide whether they still ship; if yes, wire `_sys_next_chapter` markdown interactions to reuse the same jump logic or retire the unused modal-based next button.
- [ ] Add/adjust tests (or Storybook stories) to cover `_sys_next_chapter` so regressions are caught by CI.

## QA, Docs & Release
- [ ] Run targeted backend tests (`cd src/api && pytest tests/service/learn`) plus Cook Web checks (`cd src/cook-web && npm run lint && npm run type-check`) before merging.
- [ ] Document the authoring guidance for creators (e.g. “No need to manually add 下一章 buttons”) in `docs/` or the CMS help panel.
- [ ] Communicate the new behavior in release notes and ensure ops knows whether any DB backfill or migration needs to run.

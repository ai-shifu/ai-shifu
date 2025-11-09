# Release Notes

## 2025-11-09 — Next Chapter Auto-Advance

- Backend now emits a `_sys_next_chapter` markdown interaction (plus DB record) whenever a lesson completes; older history is covered via a fallback in `get_learn_record`, so no data backfill is required.
- Cook Web automatically navigates to the next section (or shows a toast when there are no sections left) when learners click the button; the same logic falls back to the next chapter’s first lesson when an entire chapter is finished.
- Ops: no migrations or manual scripts need to run for this feature; ensure translators keep `server.learn.nextChapterButton` and `module.chat.noMoreLessons` localized when adding new languages.

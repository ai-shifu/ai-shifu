export const RESET_CHAPTER_EVENT = 'reset_chapter';
export const RESET_CHAPTER_CONFIRM_EVENT = 'reset_chapter_confirm';
export const RESET_CHAPTER_BLOCKED_EVENT = 'lesson_reset_blocked';

export const buildResetChapterBlockedAnalytics = (
  input: ResetChapterAnalyticsInput,
  source: 'catalog' | 'lesson_update',
  reason: 'limit_reached' | 'unavailable',
) => ({ ...buildResetChapterConfirmAnalytics(input), source, reason });

type ResetChapterAnalyticsInput = {
  shifuBid?: string | null;
  chapterId?: string | null;
  lessonId?: string | null;
};

export const shouldTrackResetChapter = (previewMode: boolean) => !previewMode;

export const buildResetChapterAnalytics = ({
  shifuBid,
  chapterId,
}: ResetChapterAnalyticsInput) => ({
  shifu_bid: shifuBid || '',
  chapter_id: chapterId || '',
});

export const buildResetChapterConfirmAnalytics = ({
  shifuBid,
  chapterId,
  lessonId,
}: ResetChapterAnalyticsInput) => ({
  shifu_bid: shifuBid || '',
  chapter_id: chapterId || '',
  lesson_id: lessonId || '',
});

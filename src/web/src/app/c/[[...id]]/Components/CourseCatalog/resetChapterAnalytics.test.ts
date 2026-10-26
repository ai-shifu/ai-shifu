import {
  buildResetChapterAnalytics,
  buildResetChapterConfirmAnalytics,
  RESET_CHAPTER_CONFIRM_EVENT,
  RESET_CHAPTER_EVENT,
  shouldTrackResetChapter,
} from './resetChapterAnalytics';

describe('reset chapter analytics', () => {
  it('excludes teacher preview while keeping live learner resets eligible', () => {
    expect(shouldTrackResetChapter(true)).toBe(false);
    expect(shouldTrackResetChapter(false)).toBe(true);
  });

  it('keeps accepted-click data machine-ID-only', () => {
    const payload = buildResetChapterAnalytics({
      shifuBid: 'course-1',
      chapterId: 'chapter-1',
    });

    expect(RESET_CHAPTER_EVENT).toBe('reset_chapter');
    expect(payload).toEqual({
      shifu_bid: 'course-1',
      chapter_id: 'chapter-1',
    });
    expect(payload).not.toHaveProperty('chapter_name');
  });

  it('keeps successful-reset data machine-ID-only', () => {
    const payload = buildResetChapterConfirmAnalytics({
      shifuBid: 'course-1',
      chapterId: 'chapter-1',
      lessonId: 'lesson-1',
    });

    expect(RESET_CHAPTER_CONFIRM_EVENT).toBe('reset_chapter_confirm');
    expect(payload).toEqual({
      shifu_bid: 'course-1',
      chapter_id: 'chapter-1',
      lesson_id: 'lesson-1',
    });
    expect(payload).not.toHaveProperty('chapter_name');
  });
});

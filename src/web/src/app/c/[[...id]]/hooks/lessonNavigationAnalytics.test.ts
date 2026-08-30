import {
  buildLessonNavigationAnalytics,
  LESSON_NAVIGATION_EVENT,
  shouldTrackLessonNavigation,
} from './lessonNavigationAnalytics';

describe('lesson navigation analytics', () => {
  it('uses stable machine IDs without lesson or chapter text', () => {
    const payload = buildLessonNavigationAnalytics({
      shifuBid: 'course-1',
      fromLessonId: 'lesson-1',
      toLessonId: 'lesson-2',
    });

    expect(LESSON_NAVIGATION_EVENT).toBe('nav_section_switch');
    expect(payload).toEqual({
      shifu_bid: 'course-1',
      from_lesson_id: 'lesson-1',
      to_lesson_id: 'lesson-2',
    });
    expect(payload).not.toHaveProperty('from');
    expect(payload).not.toHaveProperty('to');
    expect(payload).not.toHaveProperty('lesson_name');
  });

  it.each([
    ['preview navigation', true, 'lesson-1', 'lesson-2'],
    ['same lesson', false, 'lesson-1', 'lesson-1'],
    ['missing current lesson', false, null, 'lesson-2'],
    ['missing target lesson', false, 'lesson-1', ''],
  ])('excludes %s', (_label, previewMode, fromLessonId, toLessonId) => {
    expect(
      shouldTrackLessonNavigation({
        previewMode,
        fromLessonId,
        toLessonId,
      }),
    ).toBe(false);
  });

  it('includes a real learner lesson change', () => {
    expect(
      shouldTrackLessonNavigation({
        previewMode: false,
        fromLessonId: 'lesson-1',
        toLessonId: 'lesson-2',
      }),
    ).toBe(true);
  });
});

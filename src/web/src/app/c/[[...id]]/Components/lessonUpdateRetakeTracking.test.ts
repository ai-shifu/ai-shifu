import { startLessonUpdateRetakeTracking } from './lessonUpdateRetakeTracking';

describe('recommended retake tracking lifecycle', () => {
  it('defers ordered callbacks without awaiting delivery and deduplicates terminal results', async () => {
    const trackEvent = jest.fn(() => new Promise<void>(() => {}));
    const finish = startLessonUpdateRetakeTracking({
      shifuBid: 'course-1',
      outlineBid: 'lesson-1',
      previewMode: true,
      trackEvent,
    });
    finish?.('success');
    finish?.('failed');
    finish?.('success');
    expect(trackEvent).not.toHaveBeenCalled();
    await Promise.resolve();
    expect(trackEvent.mock.calls).toEqual([
      [
        'lesson_update_retake_attempt',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          surface: 'teacher_preview',
        },
      ],
      [
        'lesson_update_retake_result',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          surface: 'teacher_preview',
          outcome: 'success',
        },
      ],
    ]);
  });

  it.each([
    ['', 'lesson-1'],
    ['course-1', ''],
    [' ', 'lesson-1'],
    ['course-1', ' '],
  ])('excludes missing identifiers %j / %j', async (shifuBid, outlineBid) => {
    const trackEvent = jest.fn();
    expect(
      startLessonUpdateRetakeTracking({
        shifuBid,
        outlineBid,
        previewMode: false,
        trackEvent,
      }),
    ).toBeUndefined();
    await Promise.resolve();
    expect(trackEvent).not.toHaveBeenCalled();
  });
});

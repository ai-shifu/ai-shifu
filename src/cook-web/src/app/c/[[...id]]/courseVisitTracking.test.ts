import {
  buildCourseVisitEventName,
  trackCourseVisitIfNeeded,
} from './courseVisitTracking';

describe('courseVisitTracking', () => {
  test('builds a stable event name from the course bid', () => {
    expect(buildCourseVisitEventName('course-1')).toBe('course_visit_course-1');
  });

  test('tracks a logged-in learner visit with auth metadata', async () => {
    const trackEvent = jest.fn().mockResolvedValue(undefined);

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: true,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'catalog',
        trackEvent,
      }),
    ).resolves.toBe(true);

    expect(trackEvent).toHaveBeenCalledTimes(1);
    expect(trackEvent).toHaveBeenCalledWith('course_visit_course-1', {
      shifu_bid: 'course-1',
      entry_type: 'catalog',
      auth_state: 'logged_in',
      preview_mode: false,
    });
  });

  test('tracks guest visits too', async () => {
    const trackEvent = jest.fn().mockResolvedValue(undefined);

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: false,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'deep_link',
        trackEvent,
      }),
    ).resolves.toBe(true);

    expect(trackEvent).toHaveBeenCalledWith('course_visit_course-1', {
      shifu_bid: 'course-1',
      entry_type: 'deep_link',
      auth_state: 'guest',
      preview_mode: false,
    });
  });

  test('skips uninitialized users and preview mode', async () => {
    const trackEvent = jest.fn().mockResolvedValue(undefined);

    await expect(
      trackCourseVisitIfNeeded({
        initialized: false,
        isLoggedIn: false,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'catalog',
        trackEvent,
      }),
    ).resolves.toBe(false);

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: true,
        previewMode: true,
        shifuBid: 'course-1',
        entryType: 'deep_link',
        trackEvent,
      }),
    ).resolves.toBe(false);

    expect(trackEvent).not.toHaveBeenCalled();
  });

  test('returns false when the tracking call fails', async () => {
    const trackEvent = jest
      .fn()
      .mockRejectedValueOnce(new Error('track failed'));

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: true,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'catalog',
        trackEvent,
      }),
    ).resolves.toBe(false);
    expect(trackEvent).toHaveBeenCalledTimes(1);
  });
});

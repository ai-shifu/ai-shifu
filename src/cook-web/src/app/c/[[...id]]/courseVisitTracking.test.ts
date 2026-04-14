import {
  buildCourseVisitEventName,
  buildCourseVisitSessionKey,
  trackCourseVisitIfNeeded,
} from './courseVisitTracking';

describe('courseVisitTracking', () => {
  test('builds a stable event name and session key from the course bid', () => {
    expect(buildCourseVisitEventName('course-1')).toBe('course_visit_course-1');
    expect(buildCourseVisitSessionKey('course-1')).toBe(
      'course_visit:course-1',
    );
  });

  test('tracks once per session for logged-in learner visits', async () => {
    const trackEvent = jest.fn().mockResolvedValue(undefined);
    const storage = (() => {
      const map = new Map<string, string>();
      return {
        getItem: (key: string) => map.get(key) ?? null,
        setItem: (key: string, value: string) => {
          map.set(key, value);
        },
      };
    })();

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: true,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'catalog',
        storage,
        trackEvent,
      }),
    ).resolves.toBe(true);

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: true,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'catalog',
        storage,
        trackEvent,
      }),
    ).resolves.toBe(false);

    expect(trackEvent).toHaveBeenCalledTimes(1);
    expect(trackEvent).toHaveBeenCalledWith('course_visit_course-1', {
      shifu_bid: 'course-1',
      entry_type: 'catalog',
      preview_mode: false,
    });
  });

  test('skips guests and preview mode', async () => {
    const trackEvent = jest.fn().mockResolvedValue(undefined);

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: false,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'catalog',
        storage: null,
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
        storage: null,
        trackEvent,
      }),
    ).resolves.toBe(false);

    expect(trackEvent).not.toHaveBeenCalled();
  });

  test('does not mark the session when tracking fails', async () => {
    const trackEvent = jest
      .fn()
      .mockRejectedValueOnce(new Error('track failed'))
      .mockResolvedValueOnce(undefined);
    const storage = (() => {
      const map = new Map<string, string>();
      return {
        getItem: (key: string) => map.get(key) ?? null,
        setItem: (key: string, value: string) => {
          map.set(key, value);
        },
      };
    })();

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: true,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'catalog',
        storage,
        trackEvent,
      }),
    ).resolves.toBe(false);

    await expect(
      trackCourseVisitIfNeeded({
        initialized: true,
        isLoggedIn: true,
        previewMode: false,
        shifuBid: 'course-1',
        entryType: 'catalog',
        storage,
        trackEvent,
      }),
    ).resolves.toBe(true);

    expect(trackEvent).toHaveBeenCalledTimes(2);
  });
});

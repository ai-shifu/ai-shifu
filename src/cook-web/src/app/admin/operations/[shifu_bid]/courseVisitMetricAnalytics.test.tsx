import { renderHook, waitFor } from '@testing-library/react';
import {
  COURSE_VISITOR_METRIC_SHOWN_EVENT,
  resolveCourseVisitMetricExposure,
  useCourseVisitMetricExposure,
} from './courseVisitMetricAnalytics';

const mockTrackEvent = jest.fn();

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

const eligibleParams = {
  isOperatorReady: true,
  routeCourseId: 'course-1',
  loadedCourseId: 'course-1',
};

describe('course visit metric analytics', () => {
  beforeEach(() => {
    mockTrackEvent.mockReset();
    mockTrackEvent.mockResolvedValue(undefined);
  });

  test('resolves only a ready operator with matching route and loaded course', () => {
    expect(resolveCourseVisitMetricExposure(eligibleParams)).toBe('course-1');
    expect(
      resolveCourseVisitMetricExposure({
        ...eligibleParams,
        isOperatorReady: false,
      }),
    ).toBeNull();
    expect(
      resolveCourseVisitMetricExposure({
        ...eligibleParams,
        routeCourseId: '',
      }),
    ).toBeNull();
    expect(
      resolveCourseVisitMetricExposure({
        ...eligibleParams,
        loadedCourseId: 'stale-course',
      }),
    ).toBeNull();
  });

  test('tracks one exposure with only the stable course identifier', async () => {
    const { rerender } = renderHook(
      (params: typeof eligibleParams) => useCourseVisitMetricExposure(params),
      { initialProps: eligibleParams },
    );

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith(
        COURSE_VISITOR_METRIC_SHOWN_EVENT,
        { shifu_bid: 'course-1' },
      ),
    );
    const payload = mockTrackEvent.mock.calls[0][1];
    expect(payload).not.toHaveProperty('visit_count_30d');
    expect(payload).not.toHaveProperty('course_name');
    expect(payload).not.toHaveProperty('url');
    expect(payload).not.toHaveProperty('user_id');

    rerender({ ...eligibleParams });
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  });

  test('waits for eligible detail and emits once per route visit', async () => {
    const { rerender } = renderHook(
      (params: typeof eligibleParams) => useCourseVisitMetricExposure(params),
      {
        initialProps: {
          ...eligibleParams,
          loadedCourseId: '',
        },
      },
    );

    expect(mockTrackEvent).not.toHaveBeenCalled();

    rerender(eligibleParams);
    await waitFor(() => expect(mockTrackEvent).toHaveBeenCalledTimes(1));

    rerender({
      ...eligibleParams,
      routeCourseId: 'course-2',
      loadedCourseId: 'course-2',
    });
    await waitFor(() => expect(mockTrackEvent).toHaveBeenCalledTimes(2));

    rerender(eligibleParams);
    await waitFor(() => expect(mockTrackEvent).toHaveBeenCalledTimes(3));
    expect(mockTrackEvent.mock.calls).toEqual([
      [COURSE_VISITOR_METRIC_SHOWN_EVENT, { shifu_bid: 'course-1' }],
      [COURSE_VISITOR_METRIC_SHOWN_EVENT, { shifu_bid: 'course-2' }],
      [COURSE_VISITOR_METRIC_SHOWN_EVENT, { shifu_bid: 'course-1' }],
    ]);
  });

  test('keeps tracking failures fail-open without retrying the same mount', async () => {
    mockTrackEvent.mockRejectedValueOnce(new Error('blocked'));
    const { rerender } = renderHook(
      (params: typeof eligibleParams) => useCourseVisitMetricExposure(params),
      { initialProps: eligibleParams },
    );

    await waitFor(() => expect(mockTrackEvent).toHaveBeenCalledTimes(1));
    rerender({ ...eligibleParams });
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  });

  test('swallows a synchronous tracking failure', () => {
    mockTrackEvent.mockImplementationOnce(() => {
      throw new Error('unavailable');
    });

    expect(() =>
      renderHook(() => useCourseVisitMetricExposure(eligibleParams)),
    ).not.toThrow();
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  });
});

import { act, renderHook } from '@testing-library/react';
import { usePlaceholderAcceptedTracking } from './use-placeholder-accepted-tracking';

const mockTrackEvent = jest.fn();
jest.mock('./use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

beforeEach(() => mockTrackEvent.mockReset());

it.each(['course_read', 'course_listen', 'profile_onboarding'] as const)(
  'records accepted use with only the %s surface',
  surface => {
    const { result, rerender } = renderHook(() =>
      usePlaceholderAcceptedTracking(surface, true),
    );
    expect(mockTrackEvent).not.toHaveBeenCalled();
    act(() => result.current());
    rerender();
    expect(mockTrackEvent.mock.calls).toEqual([
      ['learner_interaction_placeholder_accepted', { surface }],
    ]);
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('inputText');
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('placeholder');
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('user_id');
    act(() => result.current());
    expect(mockTrackEvent).toHaveBeenCalledTimes(2);
  },
);

it('excludes preview and closed hosts and respects eligibility changes', () => {
  const { result, rerender } = renderHook(
    ({ enabled }) => usePlaceholderAcceptedTracking('course_read', enabled),
    { initialProps: { enabled: false } },
  );
  act(() => result.current());
  expect(mockTrackEvent).not.toHaveBeenCalled();
  rerender({ enabled: true });
  act(() => result.current());
  expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  rerender({ enabled: false });
  act(() => result.current());
  expect(mockTrackEvent).toHaveBeenCalledTimes(1);
});

it.each(['throw', 'reject', 'unavailable'])(
  'isolates %s tracking failures',
  async failure => {
    mockTrackEvent.mockImplementation(() => {
      if (failure === 'throw') throw new Error('tracking unavailable');
      if (failure === 'reject') return Promise.reject(new Error('unavailable'));
      return undefined;
    });
    const { result } = renderHook(() =>
      usePlaceholderAcceptedTracking('profile_onboarding', true),
    );
    await act(async () => {
      expect(() => result.current()).not.toThrow();
      await Promise.resolve();
    });
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  },
);

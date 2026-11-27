import { act, renderHook } from '@testing-library/react';
import {
  useCodeWrapToggleTracking,
  type CodeWrapToggleSurface,
} from './use-code-wrap-toggle-tracking';

const mockTrackEvent = jest.fn();
jest.mock('./use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

const mockListeners = new Set<(wrap: boolean) => void>();
jest.mock('markdown-flow-ui/renderer', () => ({
  subscribeCodeWrapToggle: (listener: (wrap: boolean) => void) => {
    mockListeners.add(listener);
    return () => mockListeners.delete(listener);
  },
}));

const toggle = (wrap: boolean) =>
  act(() => mockListeners.forEach(listener => listener(wrap)));

// The renderer is imported on demand; let that import settle.
const settle = () =>
  act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });

beforeEach(() => {
  mockTrackEvent.mockReset();
  mockListeners.clear();
});

it.each(['course_read', 'course_listen', 'course_classroom'] as const)(
  'records each toggle with only the %s surface and the chosen state',
  async surface => {
    const { rerender } = renderHook(() => useCodeWrapToggleTracking(surface));
    await settle();
    expect(mockTrackEvent).not.toHaveBeenCalled();
    toggle(true);
    rerender();
    toggle(false);
    expect(mockTrackEvent.mock.calls).toEqual([
      ['learner_code_block_wrap_toggled', { surface, wrap_enabled: true }],
      ['learner_code_block_wrap_toggled', { surface, wrap_enabled: false }],
    ]);
    expect(Object.keys(mockTrackEvent.mock.calls[0][1])).toEqual([
      'surface',
      'wrap_enabled',
    ]);
  },
);

it('excludes previews, follows surface changes and stops after unmount', async () => {
  const { rerender, unmount } = renderHook(
    ({ surface }: { surface: CodeWrapToggleSurface | null }) =>
      useCodeWrapToggleTracking(surface),
    { initialProps: { surface: null as CodeWrapToggleSurface | null } },
  );
  await settle();
  toggle(true);
  expect(mockTrackEvent).not.toHaveBeenCalled();
  rerender({ surface: 'course_listen' });
  await settle();
  toggle(false);
  expect(mockTrackEvent.mock.calls).toEqual([
    [
      'learner_code_block_wrap_toggled',
      { surface: 'course_listen', wrap_enabled: false },
    ],
  ]);
  expect(mockListeners.size).toBe(1);
  unmount();
  expect(mockListeners.size).toBe(0);
});

it.each(['throw', 'reject', 'unavailable'])(
  'isolates %s tracking failures',
  async failure => {
    mockTrackEvent.mockImplementation(() => {
      if (failure === 'throw') throw new Error('tracking unavailable');
      if (failure === 'reject') return Promise.reject(new Error('unavailable'));
      return undefined;
    });
    renderHook(() => useCodeWrapToggleTracking('course_read'));
    await settle();
    await act(async () => {
      expect(() =>
        mockListeners.forEach(listener => listener(true)),
      ).not.toThrow();
      await Promise.resolve();
    });
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  },
);

it('does not subscribe when unmounted before the renderer loads', async () => {
  const { unmount } = renderHook(() =>
    useCodeWrapToggleTracking('course_read'),
  );
  unmount();
  await settle();
  expect(mockListeners.size).toBe(0);
});

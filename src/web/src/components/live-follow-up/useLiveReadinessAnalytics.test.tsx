import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { useLiveReadinessAnalytics } from './useLiveReadinessAnalytics';

const trackEvent = jest.fn();
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent }),
}));
const input = {
  enabled: true,
  previewMode: false,
  shifuBid: 'course',
  outlineBid: 'lesson',
  anchorElementBid: 'private-anchor',
  surface: 'read_content' as const,
  state: 'checking' as const,
};
const visible = (hidden: boolean) => {
  Object.defineProperty(document, 'hidden', {
    configurable: true,
    value: hidden,
  });
  document.dispatchEvent(new Event('visibilitychange'));
};
beforeEach(() => {
  trackEvent.mockReset();
  visible(false);
});

it('counts each committed state once per opening, including blocked panels without attempts', () => {
  const { rerender } = renderHook(useLiveReadinessAnalytics, {
    initialProps: {
      ...input,
      state: 'checking' as 'checking' | 'warming' | 'unavailable' | 'ready',
    },
    wrapper: React.StrictMode,
  });
  for (const state of [
    'warming',
    'warming',
    'unavailable',
    'ready',
    'checking',
  ] as const)
    rerender({ ...input, state });
  expect(trackEvent.mock.calls).toEqual(
    ['checking', 'warming', 'unavailable', 'ready'].map((state, index) => [
      'learner_voice_follow_up_readiness',
      {
        shifu_bid: 'course',
        outline_bid: 'lesson',
        learning_mode: 'read',
        surface: 'read_content',
        state,
        initial: index === 0,
      },
    ]),
  );
  rerender({ ...input, enabled: false });
  rerender({ ...input, state: 'ready' });
  const events = trackEvent.mock.calls.map(([, payload]) => payload);
  expect(events.filter(event => event.initial)).toHaveLength(2);
  expect(events.filter(event => event.state === 'ready')).toHaveLength(2);
  expect(
    events.filter(event => event.initial && event.state === 'checking'),
  ).toHaveLength(1);
});

it.each([
  { enabled: false },
  { previewMode: true },
  { surface: 'teacher_preview' as const },
])('excludes ineligible panels (%j)', excluded => {
  renderHook(() => useLiveReadinessAnalytics({ ...input, ...excluded }));
  expect(trackEvent).not.toHaveBeenCalled();
});

it('ignores hidden states and stale listeners, and resets only for a new scope or opening', () => {
  visible(true);
  const { rerender, unmount } = renderHook(useLiveReadinessAnalytics, {
    initialProps: {
      ...input,
      state: 'checking' as 'checking' | 'ready',
      surface: 'read_content' as 'read_content' | 'listen_player',
    },
  });
  rerender({ ...input, state: 'ready' });
  expect(trackEvent).not.toHaveBeenCalled();
  act(() => visible(false));
  expect(trackEvent).toHaveBeenCalledTimes(1);
  expect(trackEvent.mock.calls[0][1]).toMatchObject({
    state: 'ready',
    initial: true,
  });
  act(() => {
    visible(true);
    visible(false);
  });
  expect(trackEvent).toHaveBeenCalledTimes(1);
  for (const changes of [
    { shifuBid: 'another-course' },
    { outlineBid: 'another-lesson' },
    { anchorElementBid: 'another-anchor' },
    { surface: 'listen_player' as const },
  ])
    rerender({ ...input, ...changes });
  expect(trackEvent).toHaveBeenCalledTimes(5);
  expect(trackEvent.mock.calls[4][1]).toEqual({
    shifu_bid: 'course',
    outline_bid: 'lesson',
    learning_mode: 'listen',
    surface: 'listen_player',
    state: 'checking',
    initial: true,
  });
  unmount();
  act(() => visible(false));
  expect(trackEvent).toHaveBeenCalledTimes(5);
});

it.each(['throw', 'reject'])(
  'keeps analytics fail-open on %s and never retries delivery',
  async failure => {
    trackEvent.mockImplementationOnce(() => {
      if (failure === 'throw') throw new Error('private tracking error');
      return Promise.reject(new Error('private tracking error'));
    });
    const { rerender } = renderHook(useLiveReadinessAnalytics, {
      initialProps: input,
    });
    await act(async () => rerender({ ...input }));
    expect(trackEvent).toHaveBeenCalledTimes(1);
    expect(Object.keys(trackEvent.mock.calls[0][1]).sort()).toEqual([
      'initial',
      'learning_mode',
      'outline_bid',
      'shifu_bid',
      'state',
      'surface',
    ]);
  },
);

import { act, renderHook } from '@testing-library/react';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import { useReadingFollowUp } from './use-reading-follow-up';
import { useAskStateStore } from './use-ask-state-store';

let mockPoint: string | null = 'first';
const mockPointOptions = jest.fn();
jest.mock('./use-reading-follow-up-point', () => ({
  useReadingFollowUpPoint: (options: unknown) => {
    mockPointOptions(options);
    return { anchorElementBid: mockPoint };
  },
}));

const items: ChatContentItem[] = [
  {
    type: ChatContentItemType.CONTENT,
    element_bid: 'first',
    content: 'private lesson content',
  },
  {
    type: ChatContentItemType.CONTENT,
    element_bid: 'second',
    content: 'later content',
  },
  { type: ChatContentItemType.CONTENT, element_bid: 'loading' },
  { type: ChatContentItemType.INTERACTION, element_bid: 'interaction' },
];

function setup(
  overrides: Partial<Parameters<typeof useReadingFollowUp>[0]> = {},
) {
  const props = {
    items,
    eligibleAnchors: new Set(['first', 'second', 'loading', 'interaction']),
    enabled: true,
    mobile: false,
    previewMode: false,
    rootRef: { current: null },
    scopeKey: 'lesson-1',
    ...overrides,
    onEnsureAsk: jest.fn(overrides.onEnsureAsk),
    trackEvent: jest.fn(overrides.trackEvent),
  };
  const hook = renderHook(next => useReadingFollowUp(next), {
    initialProps: props,
  });
  return { ...hook, props };
}

beforeEach(() => {
  mockPoint = 'first';
  mockPointOptions.mockClear();
  useAskStateStore.getState().clearLessonScope();
});

test('tracks accepted opens and closes once with exact private-free payloads', () => {
  const { result, props, rerender } = setup();
  expect(result.current.candidateAnchor).toBe('first');
  expect(props.trackEvent).not.toHaveBeenCalled();
  act(() => {
    result.current.toggle('first', 'boundary');
    result.current.toggle('first', 'boundary');
  });
  expect(result.current.expandedAnchor).toBe('first');
  expect(result.current.candidateAnchor).toBeNull();
  expect(props.onEnsureAsk).toHaveBeenCalledTimes(1);
  expect(props.trackEvent.mock.calls).toEqual([
    [
      'learner_read_follow_up_opened',
      { surface: 'desktop', entry: 'boundary' },
    ],
  ]);
  rerender({ ...props });
  act(() => {
    result.current.close('continue');
    result.current.close('continue');
  });
  expect(result.current.expandedAnchor).toBeNull();
  expect(props.trackEvent.mock.calls).toEqual([
    [
      'learner_read_follow_up_opened',
      { surface: 'desktop', entry: 'boundary' },
    ],
    [
      'learner_read_follow_up_closed',
      { surface: 'desktop', method: 'continue' },
    ],
  ]);
});

test('supports mobile history and changing anchors without synthetic close events', () => {
  const { result, props } = setup({ mobile: true });
  act(() => result.current.toggle('first', 'boundary'));
  act(() => result.current.toggle('second', 'history'));
  act(() => result.current.close('close'));
  expect(props.trackEvent.mock.calls).toEqual([
    ['learner_read_follow_up_opened', { surface: 'mobile', entry: 'boundary' }],
    ['learner_read_follow_up_opened', { surface: 'mobile', entry: 'history' }],
    ['learner_read_follow_up_closed', { surface: 'mobile', method: 'close' }],
  ]);
});

test('excludes disabled, preview and stale or non-finalized targets', () => {
  const { result, props, rerender } = setup();
  act(() => {
    result.current.toggle('interaction', 'boundary');
    result.current.toggle('loading', 'boundary');
    result.current.toggle('missing', 'history');
  });
  expect(props.onEnsureAsk).not.toHaveBeenCalled();
  rerender({
    ...props,
    eligibleAnchors: new Set(['first']),
    previewMode: true,
  });
  act(() => result.current.toggle('second', 'boundary'));
  act(() => result.current.toggle('first', 'boundary'));
  expect(result.current.expandedAnchor).toBe('first');
  act(() => result.current.close('close'));
  expect(props.trackEvent).not.toHaveBeenCalled();
  rerender({ ...props, enabled: false });
  act(() => result.current.toggle('first', 'boundary'));
  expect(result.current.expandedAnchor).toBeNull();
  expect(result.current.candidateAnchor).toBeNull();
  expect(props.trackEvent).not.toHaveBeenCalled();
});

test('locks a collapsed draft at its own point and clears lock when draft empties', () => {
  const { result, rerender, props } = setup();
  act(() => result.current.toggle('first', 'boundary'));
  act(() => result.current.onDraftChange('first', true));
  act(() => result.current.close('close'));
  mockPoint = 'second';
  rerender({ ...props });
  expect(result.current.candidateAnchor).toBe('first');
  expect(mockPointOptions.mock.calls.at(-1)?.[0].locked).toBe(true);
  act(() => result.current.onDraftChange('first', false));
  expect(result.current.candidateAnchor).toBe('second');
  expect(mockPointOptions.mock.calls.at(-1)?.[0].locked).toBe(false);
});

test('locks streaming from the scoped shared store without copying messages', () => {
  const { result } = setup();
  act(() => {
    useAskStateStore.getState().ensureLessonScope('lesson-1');
    useAskStateStore.getState().setAskList('second', [
      {
        type: 'answer',
        content: 'private streamed answer',
        isStreaming: true,
      },
    ]);
  });
  expect(result.current.candidateAnchor).toBe('second');
  expect(mockPointOptions.mock.calls.at(-1)?.[0].locked).toBe(true);
  act(() => useAskStateStore.getState().ensureLessonScope('another-lesson'));
  expect(result.current.candidateAnchor).toBe('first');
  expect(mockPointOptions.mock.calls.at(-1)?.[0].locked).toBe(false);
});

test('scope changes immediately hide old state and reject callbacks from the old lesson', () => {
  const { result, rerender, props } = setup();
  act(() => result.current.toggle('first', 'boundary'));
  act(() => result.current.onDraftChange('first', true));
  const stale = result.current;
  rerender({ ...props, scopeKey: 'lesson-2' });
  expect(result.current.expandedAnchor).toBeNull();
  expect(result.current.selectedAnchor).toBeNull();
  act(() => {
    stale.toggle('second', 'boundary');
    stale.close('close');
    stale.onDraftChange('first', true);
  });
  expect(result.current.expandedAnchor).toBeNull();
  expect(props.onEnsureAsk).toHaveBeenCalledTimes(1);
  rerender({ ...props });
  expect(result.current.expandedAnchor).toBeNull();
  expect(mockPointOptions.mock.calls.at(-1)?.[0].locked).toBe(false);
  act(() => stale.toggle('second', 'boundary'));
  expect(result.current.expandedAnchor).toBeNull();
});

test.each(['throw', 'reject'] as const)(
  'tracking can %s without affecting UI transitions',
  async failure => {
    const trackEvent = jest.fn(() => {
      if (failure === 'throw') throw new Error('unavailable');
      return Promise.reject(new Error('unavailable'));
    });
    const { result } = setup({ trackEvent });
    await act(async () => result.current.toggle('first', 'boundary'));
    expect(result.current.expandedAnchor).toBe('first');
    await act(async () => result.current.close('close'));
    expect(result.current.expandedAnchor).toBeNull();
  },
);

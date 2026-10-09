import { useLayoutEffect } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useRetakeAllowance } from './useRetakeAllowance';
import { getRetakeStatus } from '@/api/retake';
const mockTrack = jest.fn();
const mockUser = { userInfo: { user_id: 'learner' } };
jest.mock('@/store/useUserStore', () => ({
  useUserStore: (fn: (s: object) => unknown) => fn(mockUser),
}));
const mockSystem = { previewMode: false };
jest.mock('@/api/retake', () => ({ getRetakeStatus: jest.fn() }));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrack }),
}));
jest.mock('@/store/envStore', () => ({
  useEnvStore: (fn: (s: object) => unknown) => fn({ courseId: 'course' }),
}));
jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: (fn: (s: object) => unknown) => fn(mockSystem),
}));
const status = {
  available: true,
  limit: 2,
  used: 1,
  reserved: 0,
  remaining: 1,
  allowed: true,
  in_progress: false,
  title: 'PRIVATE',
  error: 'PRIVATE',
};
beforeEach(() => {
  jest.clearAllMocks();
  mockTrack.mockReset();
  mockSystem.previewMode = false;
  mockUser.userInfo.user_id = 'learner';
  jest.mocked(getRetakeStatus).mockResolvedValue(status);
});

it('blocks until admission information loads, tracks once per open and only allowlisted fields', async () => {
  const hook = renderHook(
    ({ open }) => useRetakeAllowance(open, 'lesson', 'catalog'),
    { initialProps: { open: false } },
  );
  expect(getRetakeStatus).not.toHaveBeenCalled();
  hook.rerender({ open: true });
  expect(hook.result.current.blocked).toBe(true);
  await waitFor(() => expect(hook.result.current.blocked).toBe(false));
  expect(mockTrack).toHaveBeenCalledWith('learner_retake_admission_checked', {
    shifu_bid: 'course',
    outline_bid: 'lesson',
    entry: 'catalog',
    state: 'available',
  });
  hook.rerender({ open: true });
  expect(mockTrack).toHaveBeenCalledTimes(1);
  act(() => hook.result.current.result(true));
  act(() => hook.result.current.result(false));
  expect(mockTrack.mock.calls.slice(1)).toEqual([
    [
      'learner_retake_reset_result',
      {
        shifu_bid: 'course',
        outline_bid: 'lesson',
        entry: 'catalog',
        result: 'success',
      },
    ],
    [
      'learner_retake_reset_result',
      {
        shifu_bid: 'course',
        outline_bid: 'lesson',
        entry: 'catalog',
        result: 'failed',
      },
    ],
  ]);
  expect(JSON.stringify(mockTrack.mock.calls)).not.toContain('PRIVATE');
  hook.rerender({ open: false });
  hook.rerender({ open: true });
  await waitFor(() => expect(mockTrack).toHaveBeenCalledTimes(4));
});

it.each([
  { remaining: 0, allowed: false, in_progress: false, state: 'exhausted' },
  { remaining: 1, allowed: false, in_progress: true, state: 'busy' },
])('blocks $state', async value => {
  jest.mocked(getRetakeStatus).mockResolvedValue({ ...status, ...value });
  const { result } = renderHook(() =>
    useRetakeAllowance(true, 'lesson', 'update'),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.blocked).toBe(true);
  expect(mockTrack.mock.calls[0][1].state).toBe(value.state);
});

it('fails closed on a balance error without emitting exposure', async () => {
  jest.mocked(getRetakeStatus).mockRejectedValue(new Error('PRIVATE'));
  const { result } = renderHook(() =>
    useRetakeAllowance(true, 'lesson', 'catalog'),
  );
  await waitFor(() => expect(result.current.failed).toBe(true));
  expect(result.current.blocked).toBe(true);
  expect(mockTrack).not.toHaveBeenCalled();
});
it('excludes preview from balance requests and events', () => {
  mockSystem.previewMode = true;
  const { result } = renderHook(() =>
    useRetakeAllowance(true, 'lesson', 'catalog'),
  );
  expect(result.current.blocked).toBe(false);
  result.current.result(true);
  expect(getRetakeStatus).not.toHaveBeenCalled();
  expect(mockTrack).not.toHaveBeenCalled();
});
it('keeps unconfigured courses usable without retake-limit events', async () => {
  jest
    .mocked(getRetakeStatus)
    .mockResolvedValue({ ...status, available: false });
  const { result } = renderHook(() =>
    useRetakeAllowance(true, 'lesson', 'catalog'),
  );
  await waitFor(() => expect(result.current.blocked).toBe(false));
  result.current.result(true);
  expect(mockTrack).not.toHaveBeenCalled();
});
it('tracking failure cannot change allowance or throw into a successful reset', async () => {
  mockTrack.mockImplementation(() => {
    throw new Error('analytics unavailable');
  });
  const { result } = renderHook(() =>
    useRetakeAllowance(true, 'lesson', 'catalog'),
  );
  await waitFor(() => expect(result.current.blocked).toBe(false));
  expect(() => result.current.result(true)).not.toThrow();
  expect(result.current.failed).toBeUndefined();
});

it('allows course owners without tracking learner quota events', async () => {
  jest
    .mocked(getRetakeStatus)
    .mockResolvedValue({ ...status, quota_exempt: true });
  const { result } = renderHook(() =>
    useRetakeAllowance(true, 'lesson', 'catalog'),
  );
  await waitFor(() => expect(result.current.blocked).toBe(false));
  result.current.result(true);
  expect(mockTrack).not.toHaveBeenCalled();
});
it('still blocks an exempt owner during an active generation', async () => {
  jest.mocked(getRetakeStatus).mockResolvedValue({
    ...status,
    quota_exempt: true,
    allowed: false,
    in_progress: true,
  });
  const { result } = renderHook(() =>
    useRetakeAllowance(true, 'lesson', 'catalog'),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.blocked).toBe(true);
  expect(mockTrack).not.toHaveBeenCalled();
});

it('prefetches a notice without counting it as a confirmation and deduplicates notice states', async () => {
  const hook = renderHook(
    ({ open }) => useRetakeAllowance(open, 'lesson', 'update', true),
    { initialProps: { open: false } },
  );
  await waitFor(() => expect(hook.result.current.blocked).toBe(false));
  expect(mockTrack).toHaveBeenCalledWith('learner_lesson_update_notice_shown', {
    shifu_bid: 'course',
    outline_bid: 'lesson',
    state: 'available',
  });
  expect(mockTrack).toHaveBeenCalledTimes(1);
  expect(JSON.stringify(mockTrack.mock.calls)).not.toContain('PRIVATE');
  hook.rerender({ open: true });
  await waitFor(() =>
    expect(mockTrack).toHaveBeenCalledWith('learner_retake_admission_checked', {
      shifu_bid: 'course',
      outline_bid: 'lesson',
      entry: 'update',
      state: 'available',
    }),
  );
  hook.rerender({ open: false });
  await waitFor(() => expect(hook.result.current.blocked).toBe(false));
  expect(mockTrack).toHaveBeenCalledTimes(2);
});
it.each([
  { allowed: false, in_progress: false, state: 'exhausted' },
  { allowed: false, in_progress: true, state: 'busy' },
])('tracks notice $state without an admission event', async value => {
  jest.mocked(getRetakeStatus).mockResolvedValue({ ...status, ...value });
  const hook = renderHook(() =>
    useRetakeAllowance(false, 'lesson', 'update', true),
  );
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  expect(mockTrack.mock.calls).toEqual([
    [
      'learner_lesson_update_notice_shown',
      { shifu_bid: 'course', outline_bid: 'lesson', state: value.state },
    ],
  ]);
});
it('notice tracking failure leaves the action available', async () => {
  mockTrack.mockRejectedValue(new Error('PRIVATE'));
  const hook = renderHook(() =>
    useRetakeAllowance(false, 'lesson', 'update', true),
  );
  await waitFor(() => expect(hook.result.current.blocked).toBe(false));
  expect(hook.result.current.failed).toBeUndefined();
});
it('failed notice lookup remains blocked without emitting learner analytics', async () => {
  jest.mocked(getRetakeStatus).mockRejectedValue(new Error('PRIVATE'));
  const hook = renderHook(() =>
    useRetakeAllowance(false, 'lesson', 'update', true),
  );
  await waitFor(() => expect(hook.result.current.failed).toBe(true));
  expect(hook.result.current.blocked).toBe(true);
  expect(mockTrack).not.toHaveBeenCalled();
});
it.each([true, false])(
  'excludes owners and preview from notice analytics: preview=%s',
  async preview => {
    mockSystem.previewMode = preview;
    jest
      .mocked(getRetakeStatus)
      .mockResolvedValue({ ...status, quota_exempt: true });
    const hook = renderHook(() =>
      useRetakeAllowance(false, 'lesson', 'update', true),
    );
    await waitFor(() => expect(hook.result.current.blocked).toBe(false));
    expect(mockTrack).not.toHaveBeenCalled();
    if (preview) expect(getRetakeStatus).not.toHaveBeenCalled();
  },
);

it('refreshes failed and busy notices on recovery events without polling or duplicate exposures', async () => {
  jest
    .mocked(getRetakeStatus)
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({ ...status, allowed: false, in_progress: true })
    .mockResolvedValue(status);
  const hook = renderHook(() =>
    useRetakeAllowance(false, 'lesson', 'update', true),
  );
  await waitFor(() => expect(hook.result.current.failed).toBe(true));
  act(() => window.dispatchEvent(new Event('online')));
  await waitFor(() =>
    expect(hook.result.current.status?.in_progress).toBe(true),
  );
  act(() => window.dispatchEvent(new Event('focus')));
  await waitFor(() => expect(hook.result.current.blocked).toBe(false));
  act(() => window.dispatchEvent(new Event('focus')));
  await waitFor(() => expect(getRetakeStatus).toHaveBeenCalledTimes(4));
  expect(mockTrack.mock.calls.map(call => call[1].state)).toEqual([
    'busy',
    'available',
  ]);
  hook.unmount();
  act(() => window.dispatchEvent(new Event('focus')));
  expect(getRetakeStatus).toHaveBeenCalledTimes(4);
});
it('invalidates the old identity and ignores its pending response when the account changes', async () => {
  let resolveOld!: (value: typeof status) => void;
  jest.mocked(getRetakeStatus).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        resolveOld = resolve;
      }),
  );
  const hook = renderHook(() =>
    useRetakeAllowance(false, 'lesson', 'update', true),
  );
  mockUser.userInfo.user_id = 'another-learner';
  hook.rerender();
  await waitFor(() => expect(hook.result.current.blocked).toBe(false));
  await act(async () => resolveOld({ ...status, allowed: false }));
  expect(hook.result.current.blocked).toBe(false);
  expect(getRetakeStatus).toHaveBeenCalledTimes(2);
});

it('emits exposure only after the loaded status has committed to the interface', async () => {
  const sequence: string[] = [];
  mockTrack.mockImplementation(() => {
    sequence.push('tracked');
  });
  renderHook(() => {
    const allowance = useRetakeAllowance(false, 'lesson', 'update', true);
    useLayoutEffect(() => {
      if (allowance.status) sequence.push('rendered');
    }, [allowance.status]);
    return allowance;
  });
  await waitFor(() => expect(mockTrack).toHaveBeenCalledTimes(1));
  expect(sequence).toEqual(['rendered', 'tracked']);
});

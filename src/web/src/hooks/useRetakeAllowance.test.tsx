import { act, renderHook, waitFor } from '@testing-library/react';
import { useRetakeAllowance } from './useRetakeAllowance';
import { getRetakeStatus } from '@/api/retake';
const mockTrack = jest.fn();
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

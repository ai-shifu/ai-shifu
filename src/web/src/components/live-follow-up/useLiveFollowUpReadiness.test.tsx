import { act, renderHook } from '@testing-library/react';
import { getLiveFollowUpReadiness } from '@/lib/liveVoiceFollowUp';
import { useLiveFollowUpReadiness } from './useLiveFollowUpReadiness';

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  getLiveFollowUpReadiness: jest.fn(),
}));
const probe = jest.mocked(getLiveFollowUpReadiness);
beforeEach(() => {
  jest.useFakeTimers();
  probe.mockReset();
});
afterEach(() => {
  jest.useRealTimers();
});

it('probes on prepare once, polls warming, and never renews after ready', async () => {
  probe
    .mockResolvedValueOnce({ status: 'warming', retry_after_ms: 30000 })
    .mockResolvedValue({ status: 'ready' });
  const { result } = renderHook(() => useLiveFollowUpReadiness('scope'));
  expect(probe).not.toHaveBeenCalled();
  await act(async () => {
    result.current.prepare();
    result.current.prepare();
  });
  expect(result.current.readiness).toBe('warming');
  expect(probe).toHaveBeenCalledTimes(1);
  await act(async () => jest.advanceTimersByTime(30000));
  expect(result.current.readiness).toBe('ready');
  await act(async () => jest.advanceTimersByTime(60000));
  expect(probe).toHaveBeenCalledTimes(2);
});

it('fails closed, recovers, and discards old scope responses', async () => {
  let resolve!: (value: { status: 'ready' }) => void;
  probe.mockImplementationOnce(
    () =>
      new Promise(next => {
        resolve = next;
      }),
  );
  const { result, rerender, unmount } = renderHook(
    ({ scope }) => useLiveFollowUpReadiness(scope),
    { initialProps: { scope: 'old' } },
  );
  await act(async () => result.current.prepare());
  const signal = probe.mock.calls[0][0];
  probe.mockRejectedValueOnce(new Error('offline'));
  await act(async () => rerender({ scope: 'new' }));
  expect(signal.aborted).toBe(true);
  expect(probe).toHaveBeenCalledTimes(1);
  await act(async () => result.current.prepare());
  await act(async () => resolve({ status: 'ready' }));
  expect(result.current.readiness).toBe('unavailable');
  probe.mockResolvedValue({ status: 'ready' });
  await act(async () => jest.advanceTimersByTime(30000));
  expect(result.current.readiness).toBe('ready');
  unmount();
  expect(jest.getTimerCount()).toBe(0);
});

it('aborts stalled requests after a bounded timeout and clears work on unmount', async () => {
  probe.mockImplementation(
    signal =>
      new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')));
      }),
  );
  const { result, unmount } = renderHook(() =>
    useLiveFollowUpReadiness('scope'),
  );
  await act(async () => result.current.prepare());
  await act(async () => jest.advanceTimersByTime(5000));
  expect(result.current.readiness).toBe('unavailable');
  unmount();
  expect(jest.getTimerCount()).toBe(0);
});

it('aborts on backgrounding and rechecks on foreground without stale response races', async () => {
  probe.mockImplementation(
    signal =>
      new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')));
      }),
  );
  const { result, unmount } = renderHook(() =>
    useLiveFollowUpReadiness('scope'),
  );
  await act(async () => result.current.prepare());
  await act(async () => {
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      value: true,
    });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(probe.mock.calls[0][0].aborted).toBe(true);
  probe.mockResolvedValue({ status: 'ready' });
  await act(async () => {
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      value: false,
    });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(result.current.readiness).toBe('ready');
  unmount();
  expect(jest.getTimerCount()).toBe(0);
});

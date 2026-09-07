import {
  heartbeatLiveFollowUpSession,
  LiveFollowUpControlError,
} from '@/lib/liveVoiceFollowUp';
import { LiveFollowUpOwnership } from './liveFollowUpOwnership';

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  ...jest.requireActual('@/lib/liveVoiceFollowUp'),
  heartbeatLiveFollowUpSession: jest.fn(),
}));
jest.mock('@/lib/request', () => ({ __esModule: true, default: {} }));

describe('Live ownership fencing', () => {
  const heartbeat = jest.mocked(heartbeatLiveFollowUpSession);
  let guard: LiveFollowUpOwnership;
  let valid: jest.Mock;
  let lost: jest.Mock;
  beforeEach(() => {
    jest.useFakeTimers();
    heartbeat.mockReset().mockResolvedValue({});
    valid = jest.fn();
    lost = jest.fn();
    guard = new LiveFollowUpOwnership('session', 'revision', valid, lost);
  });
  afterEach(() => {
    guard.stop();
    jest.useRealTimers();
  });

  it('checks immediately and every three seconds without additional tokens', async () => {
    await guard.start();
    expect(valid).toHaveBeenLastCalledWith(10_000);
    await jest.advanceTimersByTimeAsync(3_000);
    expect(heartbeat).toHaveBeenCalledTimes(2);
    expect(valid).toHaveBeenLastCalledWith(13_000);
    expect(lost).not.toHaveBeenCalled();
  });

  it('fences ownership conflict immediately and never reacquires it', async () => {
    await guard.start();
    heartbeat.mockRejectedValueOnce(
      new LiveFollowUpControlError('ownership_conflict'),
    );
    await jest.advanceTimersByTimeAsync(3_000);
    expect(lost).toHaveBeenCalledTimes(1);
    await jest.advanceTimersByTimeAsync(30_000);
    expect(heartbeat).toHaveBeenCalledTimes(2);
  });

  it('stops after ten seconds even if HTTP never settles; late success cannot revive it', async () => {
    await guard.start();
    let finish!: (value: unknown) => void;
    heartbeat.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        }),
    );
    await jest.advanceTimersByTimeAsync(10_000);
    expect(lost).toHaveBeenCalledTimes(1);
    finish({});
    await Promise.resolve();
    expect(valid).toHaveBeenCalledTimes(1);
  });

  it('recovers a transient transport error only within its previous authorization', async () => {
    await guard.start();
    heartbeat.mockRejectedValueOnce(new Error('offline'));
    await jest.advanceTimersByTimeAsync(6_000);
    expect(valid).toHaveBeenLastCalledWith(16_000);
    expect(lost).not.toHaveBeenCalled();
  });

  it('broadcast prompts server verification and does not trust other users notifications', async () => {
    const previous = globalThis.BroadcastChannel;
    let listener: ((event: { data: unknown }) => void) | null = null;
    const post = jest.fn();
    const close = jest.fn();
    globalThis.BroadcastChannel = class {
      set onmessage(callback: typeof listener) {
        listener = callback;
      }
      postMessage = post;
      close = close;
    } as unknown as typeof BroadcastChannel;
    try {
      await guard.start('previous');
      expect(post).toHaveBeenCalledWith({ previousRevision: 'previous' });
      listener!({ data: { previousRevision: 'another-user-revision' } });
      expect(heartbeat).toHaveBeenCalledTimes(1);
      heartbeat.mockRejectedValueOnce(
        new LiveFollowUpControlError('ownership_conflict'),
      );
      listener!({ data: { previousRevision: 'revision' } });
      await jest.advanceTimersByTimeAsync(0);
      expect(lost).toHaveBeenCalledTimes(1);
      expect(close).toHaveBeenCalledTimes(1);
    } finally {
      globalThis.BroadcastChannel = previous;
    }
  });
});

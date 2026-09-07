import {
  commitLiveFollowUpTurn,
  endLiveFollowUpSession,
  finalizeLiveFollowUpSession,
} from '@/lib/liveVoiceFollowUp';
import type { GeminiLiveTurnCommit } from './geminiLiveTurnAccumulator';
import { LiveFollowUpTurnWriter } from './liveFollowUpTurnWriter';

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  commitLiveFollowUpTurn: jest.fn(),
  endLiveFollowUpSession: jest.fn(),
  finalizeLiveFollowUpSession: jest.fn(),
}));

const turn = (turnIndex: number): GeminiLiveTurnCommit => ({
  turnIndex,
  userTranscript: `Question ${turnIndex}`,
  playedAnswerTranscript: 'Answer',
  fullAnswerTranscript: 'Answer',
  interrupted: false,
  usageMetadata: null,
  latencyMs: 10,
});

const acknowledgement = {
  session_bid: 'session-1',
  turn_index: 1,
  history_saved: true,
  ask_element_bid: 'ask-1',
  answer_element_bid: 'answer-1',
};

describe('Live turn report handoff', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.resetAllMocks();
    jest.mocked(commitLiveFollowUpTurn).mockResolvedValue(acknowledgement);
    jest.mocked(endLiveFollowUpSession).mockResolvedValue({});
    jest.mocked(finalizeLiveFollowUpSession).mockResolvedValue({});
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it.each(['ended_by_user', 'connection_error'])(
    'hands off a stalled normal request within five seconds (%s)',
    async reason => {
      let completeFirst!: () => void;
      jest.mocked(commitLiveFollowUpTurn).mockReturnValueOnce(
        new Promise(resolve => {
          completeFirst = () => resolve(acknowledgement);
        }),
      );
      const committed = jest.fn();
      const onError = jest.fn();
      const writer = new LiveFollowUpTurnWriter(
        'session-1',
        committed,
        onError,
      );
      writer.enqueue([turn(1), turn(2)]);
      const finished = writer.finish(reason);
      expect(writer.finish(reason)).toBe(finished);

      await jest.advanceTimersByTimeAsync(4999);
      expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
      await jest.advanceTimersByTimeAsync(1);
      await finished;

      expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(1);
      expect(finalizeLiveFollowUpSession).toHaveBeenCalledWith(
        'session-1',
        [
          expect.objectContaining({ turn_index: 1 }),
          expect.objectContaining({ turn_index: 2 }),
        ],
        reason,
      );
      expect(endLiveFollowUpSession).not.toHaveBeenCalled();
      expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
        1, 2,
      ]);
      completeFirst();
      await jest.advanceTimersByTimeAsync(45_000);
      expect(committed).toHaveBeenCalledTimes(2);
      expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(1);
      expect(onError).not.toHaveBeenCalled();
      expect(jest.getTimerCount()).toBe(0);
    },
  );

  it('clears the drain deadline when normal writes finish promptly', async () => {
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      jest.fn(),
      jest.fn(),
    );
    writer.enqueue([turn(1), turn(2)]);
    await writer.finish('ended_by_user');
    expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
    expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
    expect(jest.getTimerCount()).toBe(0);
    await jest.advanceTimersByTimeAsync(45_000);
    expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
  });

  it('distinguishes durable turns from a failed binding close', async () => {
    jest
      .mocked(endLiveFollowUpSession)
      .mockRejectedValueOnce(new Error('Close response lost'));
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      jest.fn(),
      jest.fn(),
    );
    expect(writer.hasPendingTurns).toBe(false);
    writer.enqueue([turn(1)]);
    expect(writer.hasPendingTurns).toBe(true);
    await expect(writer.finish('ended_by_user')).rejects.toThrow(
      'Close response lost',
    );
    expect(writer.hasPendingTurns).toBe(false);
    await writer.retryFinish('ended_by_user');
    expect(endLiveFollowUpSession).toHaveBeenCalledTimes(2);
    expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(1);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('retries a failed finish with a fresh bounded budget and the same outbox', async () => {
    let completeFirst!: () => void;
    jest.mocked(commitLiveFollowUpTurn).mockImplementation(
      () =>
        new Promise(resolve => {
          completeFirst ??= () => resolve(acknowledgement);
        }),
    );
    jest
      .mocked(finalizeLiveFollowUpSession)
      .mockReturnValue(new Promise(() => {}));
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue([turn(1), turn(2)]);
    const initial = writer.finish('connection_error');
    const rejected = expect(initial).rejects.toThrow('timed out');
    expect(writer.retryFinish('connection_error')).toBe(initial);
    await jest.advanceTimersByTimeAsync(25_000);
    await rejected;
    expect(writer.hasPendingTurns).toBe(true);
    const previousRequests = jest.mocked(finalizeLiveFollowUpSession).mock.calls
      .length;
    jest.mocked(finalizeLiveFollowUpSession).mockResolvedValue({});

    const retried = writer.retryFinish('connection_error');
    expect(writer.retryFinish('connection_error')).toBe(retried);
    await retried;
    expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(
      previousRequests + 1,
    );
    expect(finalizeLiveFollowUpSession).toHaveBeenLastCalledWith(
      'session-1',
      [
        expect.objectContaining({ turn_index: 1 }),
        expect.objectContaining({ turn_index: 2 }),
      ],
      'connection_error',
    );
    expect(writer.hasPendingTurns).toBe(false);
    expect(committed.mock.calls.map(([report]) => report.turnIndex)).toEqual([
      1, 2,
    ]);
    completeFirst();
    await jest.advanceTimersByTimeAsync(0);
    expect(committed).toHaveBeenCalledTimes(2);
    expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(1);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('keeps an explicit failed recovery bounded without dropping reports', async () => {
    jest.mocked(commitLiveFollowUpTurn).mockReturnValue(new Promise(() => {}));
    jest
      .mocked(finalizeLiveFollowUpSession)
      .mockReturnValue(new Promise(() => {}));
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      jest.fn(),
      jest.fn(),
    );
    writer.enqueue([turn(1)]);
    const rejected = expect(writer.finish('connection_error')).rejects.toThrow(
      'timed out',
    );
    await jest.advanceTimersByTimeAsync(25_000);
    await rejected;
    const retry = writer.retryFinish('connection_error');
    const retryRejected = expect(retry).rejects.toThrow('timed out');
    let settled = false;
    void retry.catch(() => {
      settled = true;
    });
    await jest.advanceTimersByTimeAsync(24_999);
    expect(settled).toBe(false);
    await jest.advanceTimersByTimeAsync(1);
    await retryRejected;
    expect(writer.hasPendingTurns).toBe(true);
    expect(endLiveFollowUpSession).not.toHaveBeenCalled();
    expect(jest.getTimerCount()).toBe(0);
  });

  it('never reopens successful or finalized writers on explicit retry', async () => {
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      jest.fn(),
      jest.fn(),
    );
    writer.enqueue([turn(1)]);
    await writer.finish('ended_by_user');
    await writer.retryFinish('ended_by_user');
    expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
    expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(1);

    const unloaded = new LiveFollowUpTurnWriter(
      'session-2',
      jest.fn(),
      jest.fn(),
    );
    await unloaded.handOffForUnload([turn(1)], 'page_hidden');
    await unloaded.retryFinish('page_hidden');
    expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(1);
    expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('retries a rejected takeover while the predecessor still owns the write lock', async () => {
    let completeFirst!: () => void;
    jest.mocked(commitLiveFollowUpTurn).mockReturnValueOnce(
      new Promise(resolve => {
        completeFirst = () => resolve(acknowledgement);
      }),
    );
    jest
      .mocked(finalizeLiveFollowUpSession)
      .mockRejectedValueOnce(new Error('write lock busy'));
    const committed = jest.fn();
    const onError = jest.fn();
    const writer = new LiveFollowUpTurnWriter('session-1', committed, onError);
    writer.enqueue([turn(1), turn(2)]);
    const finished = writer.finish('ended_by_user');
    // Attach a rejection handler before advancing fake time; success is still
    // asserted on the original promise below.
    void finished.catch(() => {});
    await jest.advanceTimersByTimeAsync(5000);
    expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(1);
    completeFirst();
    await jest.advanceTimersByTimeAsync(1000);
    await finished;

    expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(2);
    for (const [, reports] of jest.mocked(finalizeLiveFollowUpSession).mock
      .calls) {
      expect(reports.map(report => report.turn_index)).toEqual([1, 2]);
    }
    expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
      1, 2,
    ]);
    expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(1);
    expect(endLiveFollowUpSession).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(jest.getTimerCount()).toBe(0);
  });

  it.each(['during_takeover', 'after_failure'])(
    'resumes all retained successors after exhausted takeover retries (%s)',
    async predecessorCompletes => {
      let completeFirst!: () => void;
      jest.mocked(commitLiveFollowUpTurn).mockReturnValueOnce(
        new Promise(resolve => {
          completeFirst = () => resolve(acknowledgement);
        }),
      );
      jest
        .mocked(finalizeLiveFollowUpSession)
        .mockRejectedValue(new Error('offline'));
      const committed = jest.fn();
      const writer = new LiveFollowUpTurnWriter(
        'session-1',
        committed,
        jest.fn(),
      );
      writer.enqueue([turn(1), turn(2), turn(3)]);
      const finished = writer.finish('ended_by_user');
      await jest.advanceTimersByTimeAsync(5000);
      if (predecessorCompletes === 'during_takeover') completeFirst();
      await jest.advanceTimersByTimeAsync(2000);
      await finished;
      expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(3);
      if (predecessorCompletes === 'after_failure') completeFirst();
      await jest.advanceTimersByTimeAsync(0);
      await writer.finish('ended_by_user');

      expect(
        jest
          .mocked(commitLiveFollowUpTurn)
          .mock.calls.map(([, report]) => report.turn_index),
      ).toEqual(
        predecessorCompletes === 'after_failure' ? [1, 1, 2, 3] : [1, 2, 3],
      );
      expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
        1, 2, 3,
      ]);
      expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
      expect(jest.getTimerCount()).toBe(0);
    },
  );

  it('recovers retained turns without waiting for the original fetch to settle', async () => {
    jest
      .mocked(commitLiveFollowUpTurn)
      .mockReturnValueOnce(new Promise(() => {}));
    jest
      .mocked(finalizeLiveFollowUpSession)
      .mockRejectedValue(new Error('offline'));
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue([turn(1), turn(2), turn(3)]);
    const finished = writer.finish('ended_by_user');
    await jest.advanceTimersByTimeAsync(7000);
    await finished;

    expect(
      jest
        .mocked(commitLiveFollowUpTurn)
        .mock.calls.map(([, report]) => report.turn_index),
    ).toEqual([1, 1, 2, 3]);
    expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
      1, 2, 3,
    ]);
    await writer.finish('ended_by_user');
    expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
    expect(jest.getTimerCount()).toBe(0);
  });

  it.each(['reject', 'stall'])(
    'keeps finish attached until the recovered predecessor succeeds (%s)',
    async failure => {
      jest
        .mocked(commitLiveFollowUpTurn)
        .mockReturnValueOnce(new Promise(() => {}))
        .mockImplementationOnce(() =>
          failure === 'reject'
            ? Promise.reject(new Error('temporary turn failure'))
            : new Promise(() => {}),
        );
      jest
        .mocked(finalizeLiveFollowUpSession)
        .mockRejectedValue(new Error('temporary finalizer failure'));
      const committed = jest.fn();
      const writer = new LiveFollowUpTurnWriter(
        'session-1',
        committed,
        jest.fn(),
      );
      writer.enqueue([turn(1), turn(2)]);
      const finished = writer.finish('ended_by_user');
      const settled = jest.fn();
      void finished.then(settled, settled);
      await jest.advanceTimersByTimeAsync(7000);
      expect(settled).not.toHaveBeenCalled();
      expect(endLiveFollowUpSession).not.toHaveBeenCalled();
      expect(
        jest
          .mocked(commitLiveFollowUpTurn)
          .mock.calls.map(([, report]) => report.turn_index),
      ).toEqual([1, 1]);
      await jest.advanceTimersByTimeAsync(failure === 'reject' ? 1000 : 11_000);
      await finished;

      expect(
        jest
          .mocked(commitLiveFollowUpTurn)
          .mock.calls.map(([, report]) => report.turn_index),
      ).toEqual([1, 1, 1, 2]);
      expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
        1, 2,
      ]);
      expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
      expect(jest.getTimerCount()).toBe(0);
    },
  );

  it.each([false, true])(
    'bounds closing when finalizer requests never settle (clock jump=%s)',
    async clockJump => {
      jest
        .mocked(commitLiveFollowUpTurn)
        .mockReturnValue(new Promise(() => {}));
      jest
        .mocked(finalizeLiveFollowUpSession)
        .mockReturnValue(new Promise(() => {}));
      const writer = new LiveFollowUpTurnWriter(
        'session-1',
        jest.fn(),
        jest.fn(),
      );
      writer.enqueue([turn(1)]);
      const finished = writer.finish('ended_by_user');
      const rejected = jest.fn();
      void finished.catch(rejected);
      if (clockJump) {
        await jest.advanceTimersByTimeAsync(10_000);
        jest.setSystemTime(Date.now() - 60_000);
        await jest.advanceTimersByTimeAsync(15_000);
      } else {
        await jest.advanceTimersByTimeAsync(25_000);
      }
      expect(rejected).toHaveBeenCalledTimes(1);
      await expect(finished).rejects.toThrow('timed out');
      expect(endLiveFollowUpSession).not.toHaveBeenCalled();
      const requests = jest.mocked(finalizeLiveFollowUpSession).mock.calls
        .length;
      await jest.advanceTimersByTimeAsync(45_000);
      expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(requests);
      expect(jest.getTimerCount()).toBe(0);
    },
  );

  it('keeps pagehide handoff available while recovered writes are pending', async () => {
    jest.mocked(commitLiveFollowUpTurn).mockReturnValue(new Promise(() => {}));
    jest
      .mocked(finalizeLiveFollowUpSession)
      .mockRejectedValueOnce(new Error('busy'))
      .mockRejectedValueOnce(new Error('busy'))
      .mockRejectedValueOnce(new Error('busy'));
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue([turn(1), turn(2)]);
    const finished = writer.finish('ended_by_user');
    const settled = jest.fn();
    void finished.then(settled, settled);
    await jest.advanceTimersByTimeAsync(7000);
    expect(settled).not.toHaveBeenCalled();
    const handoff = writer.handOffForUnload([], 'page_hidden');
    expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(4);
    await handoff;
    await jest.advanceTimersByTimeAsync(10_000);
    await finished;
    expect(committed).toHaveBeenCalledTimes(2);
    expect(endLiveFollowUpSession).not.toHaveBeenCalled();
    expect(jest.getTimerCount()).toBe(0);
  });

  it.each(['resolve', 'reject'])(
    'does not run stale successors while the recovered queue is active (%s)',
    async lateResult => {
      let completeOriginal!: () => void;
      let completeRecoveredSecond!: () => void;
      jest
        .mocked(commitLiveFollowUpTurn)
        .mockImplementationOnce(
          () =>
            new Promise((resolve, reject) => {
              completeOriginal = () =>
                lateResult === 'resolve'
                  ? resolve(acknowledgement)
                  : reject(new Error('late predecessor failed'));
            }),
        )
        .mockResolvedValueOnce(acknowledgement)
        .mockImplementationOnce(
          () =>
            new Promise(resolve => {
              completeRecoveredSecond = () => resolve(acknowledgement);
            }),
        );
      jest
        .mocked(finalizeLiveFollowUpSession)
        .mockRejectedValue(new Error('offline'));
      const committed = jest.fn();
      const onError = jest.fn();
      const writer = new LiveFollowUpTurnWriter(
        'session-1',
        committed,
        onError,
      );
      writer.enqueue([turn(1), turn(2), turn(3)]);
      const finished = writer.finish('ended_by_user');
      void finished.catch(() => {});
      await jest.advanceTimersByTimeAsync(7000);
      expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(3);
      completeOriginal();
      await jest.advanceTimersByTimeAsync(0);
      expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(3);

      completeRecoveredSecond();
      await jest.advanceTimersByTimeAsync(0);
      await finished;
      expect(
        jest
          .mocked(commitLiveFollowUpTurn)
          .mock.calls.map(([, report]) => report.turn_index),
      ).toEqual([1, 1, 2, 3]);
      expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
        1, 2, 3,
      ]);
      expect(onError).not.toHaveBeenCalled();
      expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
      expect(jest.getTimerCount()).toBe(0);
    },
  );

  it('does not finalize twice when pagehide overtakes the bounded drain', async () => {
    jest
      .mocked(commitLiveFollowUpTurn)
      .mockReturnValueOnce(new Promise(() => {}));
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue([turn(1), turn(2)]);
    const finished = writer.finish('ended_by_user');
    await jest.advanceTimersByTimeAsync(1000);
    await writer.handOffForUnload([], 'page_hidden');
    await jest.advanceTimersByTimeAsync(5000);
    await finished;
    expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(1);
    expect(endLiveFollowUpSession).not.toHaveBeenCalled();
    expect(committed).toHaveBeenCalledTimes(2);
  });

  it.each(['resolve', 'reject'])(
    'retries an oversized retained backlog without restarting the old queue (%s)',
    async lateResult => {
      let completeFirst!: () => void;
      jest.mocked(commitLiveFollowUpTurn).mockReturnValueOnce(
        new Promise((resolve, reject) => {
          completeFirst = () =>
            lateResult === 'resolve'
              ? resolve(acknowledgement)
              : reject(new Error('late response failure'));
        }),
      );
      const committed = jest.fn();
      const onError = jest.fn();
      const writer = new LiveFollowUpTurnWriter(
        'session-1',
        committed,
        onError,
      );
      writer.enqueue(
        [1, 2, 3].map(index => ({
          ...turn(index),
          userTranscript: 'x'.repeat(25_000),
        })),
      );
      expect(onError).toHaveBeenCalledTimes(1);
      const finished = writer.finish('connection_error');
      await jest.advanceTimersByTimeAsync(5000);
      await finished;
      completeFirst();
      await jest.advanceTimersByTimeAsync(45_000);

      expect(
        jest
          .mocked(commitLiveFollowUpTurn)
          .mock.calls.map(([, report]) => report.turn_index),
      ).toEqual([1, 1, 2, 3]);
      expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
        1, 2, 3,
      ]);
      expect(onError).toHaveBeenCalledTimes(1);
      expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
      expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
      expect(jest.getTimerCount()).toBe(0);
    },
  );

  it('bounds a stalled oversized retry without consuming a partial outbox', async () => {
    jest.mocked(commitLiveFollowUpTurn).mockReturnValue(new Promise(() => {}));
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue(
      [1, 2, 3].map(index => ({
        ...turn(index),
        userTranscript: 'x'.repeat(25_000),
      })),
    );
    const rejected = expect(writer.finish('connection_error')).rejects.toThrow(
      'timed out',
    );
    await jest.advanceTimersByTimeAsync(25_000);
    await rejected;

    expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(3);
    expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
    expect(endLiveFollowUpSession).not.toHaveBeenCalled();
    expect(committed).not.toHaveBeenCalled();
    expect(jest.getTimerCount()).toBe(0);
  });

  it('does not acknowledge or consume unavailable finalization or recovery writes', async () => {
    jest.mocked(commitLiveFollowUpTurn).mockReturnValue(new Promise(() => {}));
    jest
      .mocked(finalizeLiveFollowUpSession)
      .mockRejectedValue(new Error('offline'));
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue([turn(1), turn(2)]);
    const rejected = expect(writer.finish('ended_by_user')).rejects.toThrow(
      'timed out',
    );
    await jest.advanceTimersByTimeAsync(25_000);
    await rejected;
    await jest.advanceTimersByTimeAsync(45_000);
    expect(finalizeLiveFollowUpSession).toHaveBeenCalledTimes(3);
    expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(3);
    expect(committed).not.toHaveBeenCalled();
    expect(endLiveFollowUpSession).not.toHaveBeenCalled();
  });

  it('initiates a single batch before the outstanding normal request completes', async () => {
    let completeFirst!: () => void;
    jest.mocked(commitLiveFollowUpTurn).mockReturnValueOnce(
      new Promise(resolve => {
        completeFirst = () => resolve(acknowledgement);
      }),
    );
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue([turn(1), turn(2)]);
    expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(1);

    const handoff = writer.handOffForUnload([turn(3)], 'page_hidden');
    expect(finalizeLiveFollowUpSession).toHaveBeenCalledWith(
      'session-1',
      [
        expect.objectContaining({ turn_index: 1 }),
        expect.objectContaining({ turn_index: 2 }),
        expect.objectContaining({ turn_index: 3 }),
      ],
      'page_hidden',
    );
    expect(writer.handOffForUnload([], 'page_hidden')).toBe(handoff);
    await handoff;
    completeFirst();
    await writer.finish('page_hidden');
    await Promise.resolve();
    expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
      1, 2, 3,
    ]);
    expect(commitLiveFollowUpTurn).toHaveBeenCalledTimes(1);
    expect(endLiveFollowUpSession).not.toHaveBeenCalled();
  });

  it.each([false, true])(
    'does not publish usage-only turns to local history (unload=%s)',
    async unload => {
      const committed = jest.fn();
      const writer = new LiveFollowUpTurnWriter(
        'session-1',
        committed,
        jest.fn(),
      );
      writer.enqueue([
        {
          ...turn(1),
          userTranscript: '',
          usageMetadata: { totalTokenCount: 10 },
        },
      ]);
      await (unload
        ? writer.handOffForUnload([], 'page_hidden')
        : writer.finish('ended_by_user'));
      expect(committed).not.toHaveBeenCalled();
      expect(commitLiveFollowUpTurn).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({
          user_transcript: '',
          usage_metadata: { totalTokenCount: 10 },
        }),
      );
    },
  );

  it('still publishes a final question with an empty interrupted answer', async () => {
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    const interrupted = {
      ...turn(1),
      playedAnswerTranscript: '',
      interrupted: true,
    };
    writer.enqueue([interrupted]);
    await writer.finish('ended_by_user');
    expect(committed).toHaveBeenCalledWith(interrupted, acknowledgement);
  });

  it('rejects an individual report that cannot fit the API request bound', () => {
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      jest.fn(),
      jest.fn(),
    );
    expect(() =>
      writer.enqueue([{ ...turn(1), userTranscript: 'x'.repeat(60 * 1024) }]),
    ).toThrow('report');
    expect(commitLiveFollowUpTurn).not.toHaveBeenCalled();
  });

  it.each([false, true])(
    'retains and drains valid turns beyond one unload batch (unload=%s)',
    async unload => {
      let completeFirst!: () => void;
      jest.mocked(commitLiveFollowUpTurn).mockReturnValueOnce(
        new Promise(resolve => {
          completeFirst = () => resolve(acknowledgement);
        }),
      );
      const committed = jest.fn();
      const onError = jest.fn();
      const writer = new LiveFollowUpTurnWriter(
        'session-1',
        committed,
        onError,
      );
      const turns = [1, 2, 3].map(index => ({
        ...turn(index),
        userTranscript: 'x'.repeat(25_000),
      }));
      writer.enqueue(turns.slice(0, 2));
      expect(onError).not.toHaveBeenCalled();
      writer.enqueue(turns.slice(2));
      expect(onError).toHaveBeenCalledTimes(1);
      const finished = unload
        ? writer.handOffForUnload([], 'page_hidden')
        : writer.finish('connection_error');
      expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
      completeFirst();
      await finished;

      expect(
        jest
          .mocked(commitLiveFollowUpTurn)
          .mock.calls.map(([, report]) => report.turn_index),
      ).toEqual([1, 2, 3]);
      expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
        1, 2, 3,
      ]);
      expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
      expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
    },
  );

  it('retries all retained reports when a failed backlog exceeds the unload budget', async () => {
    jest
      .mocked(commitLiveFollowUpTurn)
      .mockRejectedValueOnce(new Error('network'))
      .mockRejectedValueOnce(new Error('predecessor pending'))
      .mockRejectedValueOnce(new Error('predecessor pending'));
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue(
      [1, 2, 3].map(index => ({
        ...turn(index),
        userTranscript: 'x'.repeat(25_000),
      })),
    );
    await writer.finish('connection_error');
    expect(
      jest
        .mocked(commitLiveFollowUpTurn)
        .mock.calls.map(([, report]) => report.turn_index),
    ).toEqual([1, 2, 3, 1, 2, 3]);
    expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
      1, 2, 3,
    ]);
    expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
    expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
  });

  it('retains a failed normal report for idempotent finalization instead of discarding it', async () => {
    jest
      .mocked(commitLiveFollowUpTurn)
      .mockRejectedValueOnce(new Error('network'));
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue([turn(1)]);
    await writer.finish('connection_error');
    expect(finalizeLiveFollowUpSession).toHaveBeenCalledWith(
      'session-1',
      [expect.objectContaining({ turn_index: 1 })],
      'connection_error',
    );
    expect(committed).toHaveBeenCalledTimes(1);
    expect(endLiveFollowUpSession).not.toHaveBeenCalled();
  });

  it('drains an oversized backlog after losing an already-durable acknowledgement', async () => {
    const durable = new Set<number>();
    const inserted: number[] = [];
    let calls = 0;
    jest
      .mocked(commitLiveFollowUpTurn)
      .mockImplementation(async (_, report) => {
        calls += 1;
        if (calls === 2 || calls === 3) {
          throw new Error('offline');
        }
        // The server acknowledges durable indices without another write.
        if (!durable.has(report.turn_index)) {
          expect(report.turn_index).toBe(durable.size + 1);
          durable.add(report.turn_index);
          inserted.push(report.turn_index);
        }
        if (calls === 1) {
          throw new Error('response lost after commit');
        }
        return {
          ...acknowledgement,
          turn_index: report.turn_index,
          history_saved: true,
        };
      });
    const committed = jest.fn();
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      committed,
      jest.fn(),
    );
    writer.enqueue(
      [1, 2, 3].map(index => ({
        ...turn(index),
        userTranscript: 'x'.repeat(25_000),
      })),
    );
    await writer.finish('connection_error');
    expect(inserted).toEqual([1, 2, 3]);
    expect(calls).toBe(6);
    expect(committed.mock.calls.map(([value]) => value.turnIndex)).toEqual([
      1, 2, 3,
    ]);
    expect(endLiveFollowUpSession).toHaveBeenCalledTimes(1);
    expect(finalizeLiveFollowUpSession).not.toHaveBeenCalled();
  });
});

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

describe('Live turn report handoff', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    jest.mocked(commitLiveFollowUpTurn).mockResolvedValue({});
    jest.mocked(endLiveFollowUpSession).mockResolvedValue({});
    jest.mocked(finalizeLiveFollowUpSession).mockResolvedValue({});
  });

  it('initiates a single batch before the outstanding normal request completes', async () => {
    let completeFirst!: () => void;
    jest.mocked(commitLiveFollowUpTurn).mockReturnValueOnce(
      new Promise(resolve => {
        completeFirst = () => resolve({});
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

  it('rejects a backlog that cannot fit the bounded keepalive handoff', () => {
    const writer = new LiveFollowUpTurnWriter(
      'session-1',
      jest.fn(),
      jest.fn(),
    );
    expect(() =>
      writer.enqueue([{ ...turn(1), userTranscript: 'x'.repeat(60 * 1024) }]),
    ).toThrow('backlog');
    expect(commitLiveFollowUpTurn).not.toHaveBeenCalled();
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
});

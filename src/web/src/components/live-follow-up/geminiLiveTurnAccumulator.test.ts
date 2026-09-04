import type { GeminiLiveServerEvent } from '@/lib/liveVoiceFollowUp';

import {
  GEMINI_LIVE_RECONCILIATION_MS,
  GeminiLiveTurnAccumulator,
} from './geminiLiveTurnAccumulator';

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  mergeLiveTranscript: (current: string, incoming: string) =>
    incoming.startsWith(current) ? incoming : current + incoming,
}));

const event = (
  overrides: Partial<GeminiLiveServerEvent> = {},
): GeminiLiveServerEvent => ({
  setupComplete: false,
  audioChunks: [],
  interimInputTranscripts: [],
  inputTranscripts: [],
  outputTranscripts: [],
  interrupted: false,
  turnComplete: false,
  generationComplete: false,
  usageMetadata: null,
  resumptionHandle: null,
  resumable: null,
  goAway: false,
  upstreamError: false,
  ...overrides,
});

describe('GeminiLiveTurnAccumulator', () => {
  it('waits for reconciliation and playback before committing a complete turn', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    const audio = new ArrayBuffer(12);

    const result = accumulator.process(
      event({
        inputTranscripts: ['Question'],
        outputTranscripts: ['Answer'],
        audioChunks: [audio],
        usageMetadata: { totalTokenCount: 9 },
        turnComplete: true,
      }),
      1_000,
    );

    expect(result.audioTurnIndex).toBe(1);
    expect(result.terminalTurnIndex).toBe(1);
    expect(accumulator.popReady(1_000 + GEMINI_LIVE_RECONCILIATION_MS)).toEqual(
      [],
    );
    accumulator.markPlaybackComplete(1);
    expect(accumulator.popReady(1_001 + GEMINI_LIVE_RECONCILIATION_MS)).toEqual(
      [
        {
          turnIndex: 1,
          userTranscript: 'Question',
          playedAnswerTranscript: 'Answer',
          fullAnswerTranscript: 'Answer',
          interrupted: false,
          usageMetadata: { totalTokenCount: 9 },
          latencyMs: 501,
        },
      ],
    );
  });

  it.each([
    [1, 'playback'],
    [2, 'playback'],
    [1, 'end'],
    [2, 'end'],
  ] as const)(
    'keeps ready successors behind turn %i until %s settles it',
    (blockedIndex, finish) => {
      const accumulator = new GeminiLiveTurnAccumulator();
      for (const turnIndex of [1, 2, 3]) {
        accumulator.process(
          event({
            inputTranscripts: [`Question ${turnIndex}`],
            outputTranscripts: [`Answer ${turnIndex}`],
            audioChunks: turnIndex === blockedIndex ? [new ArrayBuffer(8)] : [],
            turnComplete: true,
          }),
          turnIndex * 1_000,
        );
      }
      accumulator.recordPlaybackProgress(blockedIndex, 4);
      const preceding = accumulator.popReady(3_501);
      expect(preceding.map(turn => turn.turnIndex)).toEqual(
        blockedIndex === 1 ? [] : [1],
      );
      expect(accumulator.popReady(3_502)).toEqual([]);

      if (finish === 'playback') {
        accumulator.markPlaybackComplete(blockedIndex);
      }
      const remaining =
        finish === 'end'
          ? accumulator.finishSession(3_503)
          : accumulator.popReady(3_503);
      expect(remaining.map(turn => turn.turnIndex)).toEqual(
        blockedIndex === 1 ? [1, 2, 3] : [2, 3],
      );
      expect(remaining[0]).toEqual(
        expect.objectContaining({
          userTranscript: `Question ${blockedIndex}`,
          playedAnswerTranscript:
            finish === 'playback' ? `Answer ${blockedIndex}` : '',
        }),
      );
      expect(accumulator.finishSession(3_504)).toEqual([]);
    },
  );

  it('reconciles a late final input transcript into the just-finished turn', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({ outputTranscripts: ['Answer'], turnComplete: true }),
      1_000,
    );

    const late = accumulator.process(
      event({ inputTranscripts: ['Question'] }),
      1_100,
    );

    expect(late.transcriptUpdates).toContainEqual({
      role: 'user',
      turnIndex: 1,
      text: 'Question',
      final: true,
    });
    expect(accumulator.popReady(1_501)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'Question',
        fullAnswerTranscript: 'Answer',
      }),
    ]);
  });

  it('commits an interrupted answer only through the playback watermark', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({
        inputTranscripts: ['Question'],
        outputTranscripts: ['Partial answer'],
        audioChunks: [new ArrayBuffer(8)],
      }),
      2_000,
    );
    accumulator.recordPlaybackProgress(1, 8);
    accumulator.process(event({ interrupted: true }), 2_100);

    expect(accumulator.popReady(2_601)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'Question',
        playedAnswerTranscript: 'Partial answer',
        interrupted: true,
      }),
    ]);
  });

  it.each(['final_first', 'response_first', 'coalesced_interim'] as const)(
    'keeps new interim speech with its final turn during reconciliation (%s)',
    order => {
      const accumulator = new GeminiLiveTurnAccumulator();
      accumulator.process(
        event({
          inputTranscripts: ['First question'],
          outputTranscripts: ['First answer'],
          turnComplete: true,
        }),
        1_000,
      );
      accumulator.process(
        event({
          interimInputTranscripts: ['Second...'],
          ...(order === 'coalesced_interim'
            ? { outputTranscripts: ['Second answer'] }
            : {}),
        }),
        1_100,
      );
      if (order === 'response_first') {
        accumulator.process(
          event({ outputTranscripts: ['Second answer'] }),
          1_150,
        );
      }
      const final = accumulator.process(
        event({ inputTranscripts: ['Second question'] }),
        1_200,
      );
      expect(final.transcriptUpdates).toContainEqual({
        role: 'user',
        turnIndex: 2,
        text: 'Second question',
        final: false,
      });
      accumulator.process(
        event({
          ...(order === 'final_first'
            ? { outputTranscripts: ['Second answer'] }
            : {}),
          turnComplete: true,
        }),
        1_300,
      );

      expect(accumulator.popReady(1_801)).toEqual([
        expect.objectContaining({
          turnIndex: 1,
          userTranscript: 'First question',
          fullAnswerTranscript: 'First answer',
        }),
        expect.objectContaining({
          turnIndex: 2,
          userTranscript: 'Second question',
          fullAnswerTranscript: 'Second answer',
        }),
      ]);
    },
  );

  it('does not create a durable turn from interim speech alone', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({ interimInputTranscripts: ['Unconfirmed words'] }),
      1_000,
    );
    expect(accumulator.finishSession(1_100)).toEqual([]);
  });

  it('starts a new turn for speech received after an interruption', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({
        inputTranscripts: ['First question'],
        outputTranscripts: ['Partial answer'],
        audioChunks: [new ArrayBuffer(8)],
      }),
      2_000,
    );
    accumulator.process(event({ interrupted: true }), 2_100);

    const nextInput = accumulator.process(
      event({ inputTranscripts: ['Follow-up interruption'] }),
      2_200,
    );

    expect(nextInput.transcriptUpdates).toContainEqual({
      role: 'user',
      turnIndex: 2,
      text: 'Follow-up interruption',
      final: false,
    });
    expect(accumulator.popReady(2_601)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'First question',
      }),
    ]);
  });

  it.each([
    { responseComplete: false, interruptionComplete: false },
    { responseComplete: false, interruptionComplete: true },
    { responseComplete: true, interruptionComplete: true },
  ])(
    'assigns coalesced barge-in speech to the next turn: %j',
    ({ responseComplete, interruptionComplete }) => {
      const accumulator = new GeminiLiveTurnAccumulator();
      accumulator.process(
        event({
          inputTranscripts: ['First question'],
          outputTranscripts: ['First answer'],
          audioChunks: [new ArrayBuffer(8)],
          turnComplete: responseComplete,
        }),
        2_000,
      );
      accumulator.recordPlaybackProgress(1, 8);
      const interrupted = accumulator.process(
        event({
          interrupted: true,
          turnComplete: interruptionComplete,
          inputTranscripts: ['Follow-up question'],
        }),
        2_100,
      );
      expect(interrupted.interruptedTurnIndex).toBe(1);
      expect(interrupted.transcriptUpdates).toContainEqual({
        role: 'user',
        turnIndex: 1,
        text: 'First question',
        final: true,
      });
      expect(interrupted.transcriptUpdates).toContainEqual({
        role: 'user',
        turnIndex: 2,
        text: 'Follow-up question',
        final: false,
      });
      if (!interruptionComplete) {
        accumulator.process(event({ turnComplete: true }), 2_200);
      }
      expect(accumulator.popReady(2_601)).toEqual([
        expect.objectContaining({
          turnIndex: 1,
          userTranscript: 'First question',
          interrupted: true,
        }),
      ]);
      accumulator.process(
        event({
          outputTranscripts: ['Follow-up answer'],
          audioChunks: [new ArrayBuffer(8)],
          turnComplete: true,
        }),
        2_700,
      );
      accumulator.markPlaybackComplete(2);
      expect(accumulator.popReady(3_201)).toEqual([
        expect.objectContaining({
          turnIndex: 2,
          userTranscript: 'Follow-up question',
          playedAnswerTranscript: 'Follow-up answer',
          interrupted: false,
        }),
      ]);
    },
  );

  it('ignores stale playback completion after interruption', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({
        inputTranscripts: ['Question'],
        outputTranscripts: ['Heard'],
        audioChunks: [new ArrayBuffer(4)],
      }),
      2000,
    );
    accumulator.recordPlaybackProgress(1, 4);
    accumulator.process(
      event({
        outputTranscripts: ['Heard and unheard continuation'],
        audioChunks: [new ArrayBuffer(4)],
      }),
      2050,
    );
    accumulator.process(event({ interrupted: true }), 2100);
    accumulator.markPlaybackComplete(1);
    expect(accumulator.popReady(2601)).toEqual([
      expect.objectContaining({
        userTranscript: 'Question',
        playedAnswerTranscript: 'Heard',
        interrupted: true,
      }),
    ]);
  });

  it('does not fabricate a final user transcript when Gemini never supplied one', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({
        interimInputTranscripts: ['maybe question'],
        outputTranscripts: ['Answer'],
        turnComplete: true,
      }),
      3_000,
    );

    expect(accumulator.popReady(3_501)).toEqual([
      expect.objectContaining({
        userTranscript: '',
        fullAnswerTranscript: 'Answer',
      }),
    ]);
  });

  it.each([true, false])(
    'force-finishes only confirmed input when the session ends (confirmed=%s)',
    confirmed => {
      const accumulator = new GeminiLiveTurnAccumulator();
      accumulator.process(
        event({
          inputTranscripts: confirmed ? ['Question'] : [],
          interimInputTranscripts: confirmed ? [] : ['Interim question'],
          outputTranscripts: ['Heard answer'],
          audioChunks: [new ArrayBuffer(4)],
        }),
        4_000,
      );
      accumulator.recordPlaybackProgress(1, 4);
      accumulator.process(
        event({
          outputTranscripts: ['Heard answer and unheard continuation'],
          audioChunks: [new ArrayBuffer(4)],
          usageMetadata: { totalTokenCount: 10 },
        }),
        4_100,
      );

      expect(accumulator.finishSession(4_250)).toEqual([
        expect.objectContaining({
          turnIndex: 1,
          userTranscript: confirmed ? 'Question' : '',
          playedAnswerTranscript: 'Heard answer',
          fullAnswerTranscript: 'Heard answer and unheard continuation',
          usageMetadata: { totalTokenCount: 10 },
          latencyMs: 250,
        }),
      ]);
    },
  );

  it('preserves a confirmed question even when the session ends before any answer', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(event({ inputTranscripts: ['Question'] }), 1_000);
    expect(accumulator.finishSession(1_100)).toEqual([
      expect.objectContaining({
        userTranscript: 'Question',
        playedAnswerTranscript: '',
        fullAnswerTranscript: '',
      }),
    ]);
  });
});

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
  it('discards a paused reply until its real terminal event while retaining played history', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.submitText('Question', 10);
    accumulator.process(
      event({
        outputTranscripts: ['Heard'],
        audioChunks: [new ArrayBuffer(4)],
      }),
      20,
    );
    accumulator.recordPlaybackProgress(1, 4);
    expect(accumulator.pauseOutput(30)).toEqual([1]);
    expect(accumulator.popReady(1_000)).toEqual([]);
    accumulator.resumeOutput();
    const late = accumulator.process(
      event({
        outputTranscripts: ['Heard but discarded'],
        audioChunks: [new ArrayBuffer(8)],
        turnComplete: true,
        usageMetadata: { totalTokenCount: 50 },
      }),
      1_100,
    );
    expect(late.audioTurnIndex).toBe(1);
    expect(accumulator.suppressPlayback(1)).toBe(true);
    accumulator.markPlaybackComplete(1);
    expect(accumulator.popReady(1_599)).toEqual([]);
    expect(accumulator.popReady(1_600)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'Question',
        playedAnswerTranscript: 'Heard',
        fullAnswerTranscript: 'Heard but discarded',
        interrupted: true,
        usageMetadata: { totalTokenCount: 50 },
      }),
    ]);
    expect(
      accumulator.submitText('Next question', 1_700)?.update.turnIndex,
    ).toBe(2);
    const next = accumulator.process(
      event({
        outputTranscripts: ['Next answer'],
        audioChunks: [new ArrayBuffer(4)],
      }),
      1_710,
    );
    expect(next.audioTurnIndex).toBe(2);
    expect(accumulator.suppressPlayback(2)).toBe(false);
  });

  it('suppresses speech and output first arriving during pause without inventing a question', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    expect(accumulator.pauseOutput(10)).toEqual([]);
    expect(accumulator.finishSession(20)).toEqual([]);
    accumulator.process(
      event({ interimInputTranscripts: ['Unfinished speech'] }),
      30,
    );
    accumulator.resumeOutput();
    const late = accumulator.process(
      event({
        outputTranscripts: ['Unheard answer'],
        audioChunks: [new ArrayBuffer(4)],
        turnComplete: true,
      }),
      40,
    );
    expect(accumulator.suppressPlayback(late.audioTurnIndex!)).toBe(true);
    expect(accumulator.popReady(540)).toEqual([
      expect.objectContaining({
        userTranscript: '',
        playedAnswerTranscript: '',
        interrupted: true,
      }),
    ]);
  });

  it('keeps late input, usage and a final playback watermark on the paused terminal turn', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({
        outputTranscripts: ['Heard'],
        audioChunks: [new ArrayBuffer(4)],
        turnComplete: true,
      }),
      20,
    );
    expect(accumulator.pauseOutput(30)).toEqual([1]);
    accumulator.recordPlaybackProgress(1, 4);
    const late = accumulator.process(
      event({
        inputTranscripts: ['Question'],
        usageMetadata: { totalTokenCount: 12 },
      }),
      40,
    );
    expect(late.audioTurnIndex).toBeNull();
    expect(accumulator.suppressPlayback(1)).toBe(true);
    expect(accumulator.popReady(520)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'Question',
        playedAnswerTranscript: 'Heard',
        interrupted: true,
        usageMetadata: { totalTokenCount: 12 },
      }),
    ]);
  });

  it('does not attach a discarded text-only tail to a previously heard audio checkpoint', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.submitText('Question', 10);
    accumulator.process(
      event({
        outputTranscripts: ['Heard'],
        audioChunks: [new ArrayBuffer(4)],
      }),
      20,
    );
    accumulator.pauseOutput(30);
    accumulator.recordPlaybackProgress(1, 4);
    accumulator.process(
      event({ outputTranscripts: ['Heard but not spoken'] }),
      40,
    );
    accumulator.process(event({ turnComplete: true }), 50);
    expect(accumulator.popReady(550)).toEqual([
      expect.objectContaining({
        playedAnswerTranscript: 'Heard',
        fullAnswerTranscript: 'Heard but not spoken',
        interrupted: true,
      }),
    ]);
  });

  it('does not discard a future question when paused before any input', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.pauseOutput(10);
    accumulator.resumeOutput();
    accumulator.submitText('First question', 20);
    const answer = accumulator.process(
      event({
        outputTranscripts: ['Answer'],
        audioChunks: [new ArrayBuffer(4)],
        turnComplete: true,
      }),
      30,
    );
    expect(accumulator.suppressPlayback(answer.audioTurnIndex!)).toBe(false);
    accumulator.markPlaybackComplete(1);
    expect(accumulator.popReady(530)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'First question',
        playedAnswerTranscript: 'Answer',
        interrupted: false,
      }),
    ]);
  });

  it('retains a typed interruption across pause and resume until the old turn closes', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.submitText('First question', 10);
    accumulator.process(
      event({
        outputTranscripts: ['Heard'],
        audioChunks: [new ArrayBuffer(4)],
      }),
      20,
    );
    accumulator.recordPlaybackProgress(1, 4);
    accumulator.pauseOutput(30);
    accumulator.resumeOutput();
    accumulator.submitText('Next question', 40);
    const old = accumulator.process(
      event({ interrupted: true, turnComplete: true }),
      50,
    );
    expect(old.terminalTurnIndex).toBe(1);
    const next = accumulator.process(
      event({
        outputTranscripts: ['New answer'],
        audioChunks: [new ArrayBuffer(4)],
        turnComplete: true,
      }),
      60,
    );
    expect(next.audioTurnIndex).toBe(2);
    expect(accumulator.suppressPlayback(2)).toBe(false);
    accumulator.markPlaybackComplete(2);
    expect(accumulator.popReady(560)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'First question',
        playedAnswerTranscript: 'Heard',
        interrupted: true,
      }),
      expect.objectContaining({
        turnIndex: 2,
        userTranscript: 'Next question',
        playedAnswerTranscript: 'New answer',
        interrupted: false,
      }),
    ]);
  });

  it('retains a typed handoff until the upstream boundary even after reconciliation elapses', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({
        interimInputTranscripts: ['Voice'],
        outputTranscripts: ['Old'],
        audioChunks: [new ArrayBuffer(4)],
      }),
      100,
    );
    accumulator.submitText('Typed next', 110);
    accumulator.process(event({ interrupted: true }), 120);
    expect(accumulator.popReady(700)).toEqual([]);
    const late = accumulator.process(
      event({
        inputTranscripts: ['Final voice question'],
        outputTranscripts: ['Old tail'],
        audioChunks: [new ArrayBuffer(4)],
      }),
      710,
    );
    expect(late.audioTurnIndex).toBe(1);
    expect(accumulator.suppressPlayback(1)).toBe(true);
    accumulator.process(event({ turnComplete: true }), 720);
    expect(accumulator.textHandoffPending).toBe(false);
    expect(accumulator.popReady(721)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'Final voice question',
        interrupted: true,
      }),
    ]);
    expect(
      accumulator.process(
        event({
          outputTranscripts: ['New'],
          audioChunks: [new ArrayBuffer(4)],
        }),
        730,
      ).audioTurnIndex,
    ).toBe(2);
  });

  it('commits typed questions without fabricating an audio transcription', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    expect(accumulator.submitText('Typed question', 100)?.update).toEqual({
      role: 'user',
      turnIndex: 1,
      text: 'Typed question',
      final: true,
    });
    accumulator.process(
      event({
        outputTranscripts: ['Spoken answer'],
        audioChunks: [new ArrayBuffer(4)],
        turnComplete: true,
      }),
      200,
    );
    accumulator.markPlaybackComplete(1);
    expect(accumulator.popReady(701)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: 'Typed question',
        playedAnswerTranscript: 'Spoken answer',
        interrupted: false,
      }),
    ]);
  });

  it.each([true, false])(
    'keeps late old parts out of a typed handoff (interrupted=%s)',
    interrupted => {
      const accumulator = new GeminiLiveTurnAccumulator();
      accumulator.process(
        event({
          inputTranscripts: ['Voice question'],
          outputTranscripts: ['Heard'],
          audioChunks: [new ArrayBuffer(4)],
        }),
        100,
      );
      accumulator.recordPlaybackProgress(1, 4);
      expect(
        accumulator.submitText('Next typed question', 110)
          ?.interruptedTurnIndex,
      ).toBe(1);
      expect(accumulator.submitText('Duplicate', 111)).toBeNull();
      const late = accumulator.process(
        event({
          outputTranscripts: ['Heard but not played'],
          audioChunks: [new ArrayBuffer(4)],
        }),
        120,
      );
      expect(late.audioTurnIndex).toBe(1);
      expect(accumulator.suppressPlayback(1)).toBe(true);
      if (interrupted) accumulator.process(event({ interrupted: true }), 130);
      accumulator.process(event({ turnComplete: true }), 140);
      expect(accumulator.textHandoffPending).toBe(false);
      const next = accumulator.process(
        event({
          outputTranscripts: ['New answer'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
        150,
      );
      expect(next.audioTurnIndex).toBe(2);
      accumulator.markPlaybackComplete(2);
      expect(accumulator.popReady(701)).toEqual([
        expect.objectContaining({
          turnIndex: 1,
          userTranscript: 'Voice question',
          playedAnswerTranscript: 'Heard',
          interrupted: true,
        }),
        expect.objectContaining({
          turnIndex: 2,
          userTranscript: 'Next typed question',
          playedAnswerTranscript: 'New answer',
        }),
      ]);
    },
  );

  it('cuts buffered playback after upstream completion without awaiting an impossible interruption', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.submitText('First', 10);
    accumulator.process(
      event({
        outputTranscripts: ['Unheard'],
        audioChunks: [new ArrayBuffer(8)],
        turnComplete: true,
      }),
      20,
    );
    expect(accumulator.submitText('Second', 30)?.interruptedTurnIndex).toBe(1);
    expect(accumulator.textHandoffPending).toBe(false);
    accumulator.markPlaybackComplete(1);
    expect(accumulator.finishSession(40)).toEqual([
      expect.objectContaining({
        userTranscript: 'First',
        playedAnswerTranscript: '',
        interrupted: true,
      }),
      expect.objectContaining({
        userTranscript: 'Second',
        playedAnswerTranscript: '',
      }),
    ]);
  });

  it('accepts fresh speech after a typed turn instead of assigning it to the typed input', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.submitText('Typed', 10);
    accumulator.process(
      event({ outputTranscripts: ['One'], turnComplete: true }),
      20,
    );
    const next = accumulator.process(
      event({
        inputTranscripts: ['New speech'],
        outputTranscripts: ['Two'],
        turnComplete: true,
      }),
      30,
    );
    expect(next.transcriptUpdates).toContainEqual({
      role: 'user',
      turnIndex: 2,
      text: 'New speech',
      final: true,
    });
    expect(
      accumulator.finishSession(40).map(turn => turn.userTranscript),
    ).toEqual(['Typed', 'New speech']);
  });

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

  it.each([
    'audio_first',
    'transcript_first',
    'coalesced_input',
    'input_after_completion',
  ] as const)(
    'starts a new response after turnComplete before its speech transcription (%s)',
    order => {
      const accumulator = new GeminiLiveTurnAccumulator();
      accumulator.process(
        event({
          inputTranscripts: ['First question'],
          outputTranscripts: ['First answer'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
        1_000,
      );
      accumulator.markPlaybackComplete(1);
      const response = accumulator.process(
        event({
          outputTranscripts: order === 'audio_first' ? [] : ['Second answer'],
          audioChunks: order === 'transcript_first' ? [] : [new ArrayBuffer(4)],
          inputTranscripts:
            order === 'coalesced_input' ? ['Second question'] : [],
          turnComplete: order === 'input_after_completion',
        }),
        1_100,
      );
      if (order === 'transcript_first') {
        expect(response.transcriptUpdates).toContainEqual({
          role: 'assistant',
          turnIndex: 2,
          text: 'Second answer',
          final: false,
        });
      } else expect(response.audioTurnIndex).toBe(2);
      if (order !== 'coalesced_input') {
        const input = accumulator.process(
          event({ inputTranscripts: ['Second question'] }),
          1_200,
        );
        expect(input.transcriptUpdates).toContainEqual({
          role: 'user',
          turnIndex: 2,
          text: 'Second question',
          final: order === 'input_after_completion',
        });
      }
      accumulator.process(
        event({
          outputTranscripts: order === 'audio_first' ? ['Second answer'] : [],
          audioChunks: order === 'transcript_first' ? [new ArrayBuffer(4)] : [],
          turnComplete: true,
        }),
        1_300,
      );
      accumulator.markPlaybackComplete(2);
      expect(accumulator.popReady(1_801)).toEqual([
        expect.objectContaining({
          turnIndex: 1,
          userTranscript: 'First question',
          fullAnswerTranscript: 'First answer',
          playedAnswerTranscript: 'First answer',
        }),
        expect.objectContaining({
          turnIndex: 2,
          userTranscript: 'Second question',
          fullAnswerTranscript: 'Second answer',
          playedAnswerTranscript: 'Second answer',
        }),
      ]);
    },
  );

  it('retains the late input and usage reconciliation window without new model output', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({
        outputTranscripts: ['Answer'],
        audioChunks: [new ArrayBuffer(4)],
        turnComplete: true,
      }),
      1_000,
    );
    accumulator.markPlaybackComplete(1);
    accumulator.process(
      event({ usageMetadata: { totalTokenCount: 12 } }),
      1_100,
    );
    const input = accumulator.process(
      event({ inputTranscripts: ['Question'] }),
      1_200,
    );
    expect(input.transcriptUpdates).toContainEqual({
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
        playedAnswerTranscript: 'Answer',
        usageMetadata: { totalTokenCount: 12 },
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

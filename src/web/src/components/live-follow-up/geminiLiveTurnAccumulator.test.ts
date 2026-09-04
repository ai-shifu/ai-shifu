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

  it('force-finishes active content when the browser session ends', () => {
    const accumulator = new GeminiLiveTurnAccumulator();
    accumulator.process(
      event({ inputTranscripts: ['Question'], outputTranscripts: ['Answer'] }),
      4_000,
    );

    expect(accumulator.finishSession(4_250)).toEqual([
      expect.objectContaining({
        turnIndex: 1,
        userTranscript: '',
        fullAnswerTranscript: 'Answer',
        latencyMs: 250,
      }),
    ]);
  });
});

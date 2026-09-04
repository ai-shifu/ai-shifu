import { TextDecoder, TextEncoder } from 'node:util';

import request from '@/lib/request';

import {
  commitLiveFollowUpTurn,
  createLiveFollowUpSession,
  encodeGeminiLiveAudioMessage,
  endLiveFollowUpSession,
  finalizeLiveFollowUpSession,
  heartbeatLiveFollowUpSession,
  LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE,
  mergeLiveTranscript,
  parseGeminiLiveServerMessage,
  resolveGeminiLiveWebSocketUrl,
} from './liveVoiceFollowUp';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

describe('live voice follow-up direct protocol helpers', () => {
  const mockedPost = jest.mocked(request.post);

  beforeAll(() => {
    Object.defineProperty(global, 'TextDecoder', {
      configurable: true,
      value: TextDecoder,
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('uses the stable server capacity business code', () => {
    expect(LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE).toBe(4018);
  });

  it('uses the authenticated HTTP client for session lifecycle and turn reports', async () => {
    const sessionPayload = {
      anchor_element_bid: 'anchor-1',
      preview_mode: false,
      learning_mode: 'read' as const,
      surface: 'read_content' as const,
    };
    await createLiveFollowUpSession('course/1', 'outline/1', sessionPayload);
    await heartbeatLiveFollowUpSession('session/1');
    await commitLiveFollowUpTurn('session/1', {
      turn_index: 1,
      user_transcript: 'Question',
      played_answer_transcript: 'Answer',
      interrupted: false,
      usage_metadata: { totalTokenCount: 3 },
      latency_ms: 100,
    });
    await endLiveFollowUpSession('session/1', 'ended_by_user');

    expect(mockedPost).toHaveBeenNthCalledWith(
      1,
      '/api/learn/shifu/course%2F1/live-follow-up/outline%2F1/session',
      sessionPayload,
      { skipErrorToast: true, credentials: 'include' },
    );
    expect(mockedPost).toHaveBeenNthCalledWith(
      2,
      '/api/learn/live-follow-up/session/session%2F1/heartbeat',
      {},
      { skipErrorToast: true, credentials: 'include' },
    );
    expect(mockedPost).toHaveBeenNthCalledWith(
      3,
      '/api/learn/live-follow-up/session/session%2F1/turn',
      expect.objectContaining({ turn_index: 1 }),
      { skipErrorToast: true, credentials: 'include' },
    );
    expect(mockedPost).toHaveBeenNthCalledWith(
      4,
      '/api/learn/live-follow-up/session/session%2F1/end',
      { reason: 'ended_by_user' },
      { skipErrorToast: true, credentials: 'include', keepalive: true },
    );
  });

  it('hands all pending turns to one authenticated keepalive request', async () => {
    await finalizeLiveFollowUpSession('session/1', [], 'page_hidden');
    expect(mockedPost).toHaveBeenCalledWith(
      '/api/learn/live-follow-up/session/session%2F1/finalize',
      { turns: [], reason: 'page_hidden' },
      { skipErrorToast: true, credentials: 'include', keepalive: true },
    );
  });

  it('only appends an ephemeral token to the official constrained endpoint', () => {
    const endpoint =
      'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained';
    expect(
      resolveGeminiLiveWebSocketUrl(endpoint, 'auth_tokens/short-lived'),
    ).toBe(`${endpoint}?access_token=auth_tokens%2Fshort-lived`);
    expect(() =>
      resolveGeminiLiveWebSocketUrl(
        'wss://attacker.example/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained',
        'auth_tokens/short-lived',
      ),
    ).toThrow('Invalid Gemini Live session transport');
    expect(() =>
      resolveGeminiLiveWebSocketUrl(endpoint, 'long-lived-api-key'),
    ).toThrow('Invalid Gemini Live session transport');
  });

  it('encodes PCM as Gemini realtime input JSON', () => {
    const payload = JSON.parse(
      encodeGeminiLiveAudioMessage(new Uint8Array([1, 2, 3]).buffer),
    );
    expect(payload).toEqual({
      realtimeInput: {
        audio: { mimeType: 'audio/pcm;rate=16000', data: 'AQID' },
      },
    });
  });

  it('decodes binary UTF-8 setup, audio and transcript messages', () => {
    const payload = {
      setupComplete: {},
      serverContent: {
        inputTranscription: { text: '为什么？' },
        outputTranscription: { text: '你好，世界 🌏' },
        modelTurn: {
          parts: [
            { inlineData: { mimeType: 'audio/pcm;rate=24000', data: 'AQID' } },
            { inlineData: { mimeType: 'audio/pcm;rate=24000', data: 'BAUG' } },
          ],
        },
        turnComplete: true,
      },
    };
    const json = JSON.stringify(payload);
    const binary = Uint8Array.from(new TextEncoder().encode(json)).buffer;

    expect(parseGeminiLiveServerMessage(binary)).toEqual(
      parseGeminiLiveServerMessage(json),
    );
    expect(parseGeminiLiveServerMessage(binary)).toEqual(
      expect.objectContaining({
        setupComplete: true,
        inputTranscripts: ['为什么？'],
        outputTranscripts: ['你好，世界 🌏'],
        audioChunks: [
          new Uint8Array([1, 2, 3]).buffer,
          new Uint8Array([4, 5, 6]).buffer,
        ],
        turnComplete: true,
      }),
    );
  });

  it('rejects malformed binary messages without exposing their contents', () => {
    expect(parseGeminiLiveServerMessage(new ArrayBuffer(0))).toBeNull();
    expect(
      parseGeminiLiveServerMessage(new Uint8Array([0xff, 0xfe]).buffer),
    ).toBeNull();
    const invalidJson = Uint8Array.from(
      new TextEncoder().encode('not json'),
    ).buffer;
    expect(parseGeminiLiveServerMessage(invalidJson)).toBeNull();
  });

  it('parses all relevant Gemini parts without exposing raw errors', () => {
    expect(
      parseGeminiLiveServerMessage(
        JSON.stringify({
          serverContent: {
            modelTurn: {
              parts: [
                {
                  inlineData: {
                    mimeType: 'audio/pcm;rate=24000',
                    data: 'AQID',
                  },
                },
              ],
            },
            inputTranscription: { text: 'Question' },
            outputTranscription: { text: 'Answer' },
            interrupted: true,
            turnComplete: true,
          },
          usageMetadata: { totalTokenCount: 3 },
          sessionResumptionUpdate: {
            newHandle: 'private-handle',
            resumable: true,
          },
        }),
      ),
    ).toEqual({
      setupComplete: false,
      audioChunks: [new Uint8Array([1, 2, 3]).buffer],
      interimInputTranscripts: [],
      inputTranscripts: ['Question'],
      outputTranscripts: ['Answer'],
      interrupted: true,
      turnComplete: true,
      generationComplete: false,
      usageMetadata: { totalTokenCount: 3 },
      resumptionHandle: 'private-handle',
      resumable: true,
      goAway: false,
      upstreamError: false,
    });
  });

  it('rejects malformed JSON and invalid audio while merging transcript deltas', () => {
    expect(parseGeminiLiveServerMessage('not json')).toBeNull();
    expect(
      parseGeminiLiveServerMessage(
        JSON.stringify({
          serverContent: {
            modelTurn: {
              parts: [{ inlineData: { mimeType: 'audio/pcm', data: '$$$' } }],
            },
          },
        }),
      ),
    ).toBeNull();
    expect(mergeLiveTranscript('hello wor', 'world')).toBe('hello world');
    expect(mergeLiveTranscript('hello', 'hello world')).toBe('hello world');
  });
});

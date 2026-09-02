import {
  createLiveFollowUpSession,
  parseLiveFollowUpServerMessage,
  resolveLiveFollowUpWebSocketUrl,
} from './liveVoiceFollowUp';

import request from '@/lib/request';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

jest.mock('@/c-utils/envUtils', () => ({
  getResolvedBaseURL: () => 'https://api.example.test',
}));

describe('live voice follow-up protocol helpers', () => {
  const originalLocation = window.location;
  const mockedPost = jest.mocked(request.post);

  beforeEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { origin: 'https://web.example.test' },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('keeps the ticket POST and websocket on the browser origin', async () => {
    const payload: Parameters<typeof createLiveFollowUpSession>[2] = {
      anchor_element_bid: 'anchor-1',
      preview_mode: false,
      learning_mode: 'read',
      surface: 'read_content',
    };
    mockedPost.mockResolvedValue({
      session_bid: 'session-1',
      ws_path: '/api/learn/live-follow-up/ws/session-1',
      expires_at: '2030-01-01T00:00:00Z',
    });

    await createLiveFollowUpSession('course/1', 'outline/1', payload);

    expect(mockedPost).toHaveBeenCalledWith(
      'https://web.example.test/api/learn/shifu/course%2F1/live-follow-up/outline%2F1/session',
      payload,
      { skipErrorToast: true, credentials: 'include' },
    );
    expect(
      resolveLiveFollowUpWebSocketUrl('/api/learn/live-follow-up/ws/session-1'),
    ).toBe('wss://web.example.test/api/learn/live-follow-up/ws/session-1');
    expect(() =>
      resolveLiveFollowUpWebSocketUrl(
        'https://attacker.example/api/learn/live-follow-up/ws/session-1',
      ),
    ).toThrow('Invalid live follow-up WebSocket path');
  });

  it('uses the configured transport base outside a browser', async () => {
    const browserWindow = window;
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: undefined,
    });

    try {
      await createLiveFollowUpSession('course-1', 'outline-1', {
        anchor_element_bid: 'anchor-1',
        preview_mode: true,
        learning_mode: 'listen',
        surface: 'teacher_preview',
      });

      expect(mockedPost).toHaveBeenCalledWith(
        'https://api.example.test/api/learn/shifu/course-1/live-follow-up/outline-1/session',
        expect.any(Object),
        { skipErrorToast: true, credentials: 'include' },
      );
      expect(
        resolveLiveFollowUpWebSocketUrl(
          '/api/learn/live-follow-up/ws/session-1',
        ),
      ).toBe('wss://api.example.test/api/learn/live-follow-up/ws/session-1');
    } finally {
      Object.defineProperty(globalThis, 'window', {
        configurable: true,
        value: browserWindow,
      });
    }
  });

  it('parses bounded control messages and optional speaking turn identity', () => {
    expect(
      parseLiveFollowUpServerMessage(
        JSON.stringify({
          type: 'state',
          state: 'speaking',
          turn_index: 3,
          private_error: 'must not leak',
        }),
      ),
    ).toEqual({ type: 'state', state: 'speaking', turn_index: 3 });
    expect(
      parseLiveFollowUpServerMessage(
        JSON.stringify({
          type: 'transcript',
          role: 'assistant',
          turn_index: 3,
          text: 'Hello',
          final: true,
          audio: 'ignored',
        }),
      ),
    ).toEqual({
      type: 'transcript',
      role: 'assistant',
      turn_index: 3,
      text: 'Hello',
      final: true,
    });
  });

  it('rejects malformed and unknown messages', () => {
    expect(parseLiveFollowUpServerMessage('not json')).toBeNull();
    expect(
      parseLiveFollowUpServerMessage(
        JSON.stringify({ type: 'state', state: 'private-state' }),
      ),
    ).toBeNull();
    expect(
      parseLiveFollowUpServerMessage(
        JSON.stringify({
          type: 'transcript',
          role: 'assistant',
          turn_index: '3',
          text: 'Hello',
          final: true,
        }),
      ),
    ).toBeNull();
  });
});

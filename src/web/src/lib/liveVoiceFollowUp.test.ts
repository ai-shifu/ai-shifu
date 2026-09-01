import {
  parseLiveFollowUpServerMessage,
  resolveLiveFollowUpWebSocketUrl,
} from './liveVoiceFollowUp';

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
  it('builds a cookie-bearing websocket URL without adding credentials', () => {
    expect(
      resolveLiveFollowUpWebSocketUrl('/api/learn/live-follow-up/ws/session-1'),
    ).toBe('wss://api.example.test/api/learn/live-follow-up/ws/session-1');
    expect(() =>
      resolveLiveFollowUpWebSocketUrl(
        'https://attacker.example/api/learn/live-follow-up/ws/session-1',
      ),
    ).toThrow('Invalid live follow-up WebSocket path');
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

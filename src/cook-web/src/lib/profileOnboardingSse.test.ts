import { SSE } from 'sse.js';
import { attachSseBusinessResponseFallback } from '@/lib/request';
import { streamProfileOnboardingRuntime } from './profileOnboardingSse';

const mockListeners: Record<
  string,
  (event: Event & { data?: string }) => void
> = {};
const mockSource = {
  addEventListener: jest.fn(
    (type: string, listener: (event: Event & { data?: string }) => void) => {
      mockListeners[type] = listener;
    },
  ),
  dispatchEvent: jest.fn((event: Event) => {
    mockListeners[event.type]?.(event as Event & { data?: string });
    return true;
  }),
  stream: jest.fn(),
  close: jest.fn(),
};

jest.mock('sse.js', () => ({
  SSE: jest.fn(() => mockSource),
}));

jest.mock('@/c-utils/envUtils', () => ({
  getResolvedBaseURL: jest.fn(() => 'https://api.example.com'),
}));

jest.mock('@/store/useUserStore', () => ({
  useUserStore: {
    getState: jest.fn(() => ({ getToken: () => 'token-1' })),
  },
}));

jest.mock('@/lib/request', () => ({
  attachSseBusinessResponseFallback: jest.fn(),
  getCurrentLanguageHeaders: (language?: string) =>
    language ? { 'Accept-Language': language } : {},
}));

jest.mock('@/lib/request-trace', () => ({
  buildTraceHeaders: jest.fn(headers => ({
    headers,
    requestId: 'request-id',
    harnessRunId: 'harness-id',
  })),
}));

describe('streamProfileOnboardingRuntime', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.keys(mockListeners).forEach(key => delete mockListeners[key]);
  });

  test('starts an authenticated POST stream with the language snapshot', () => {
    const source = streamProfileOnboardingRuntime({
      path: '/api/user/profile-onboarding/session/session-1/run',
      payload: { expected_block_index: 0, request_id: 'run-1' },
      language: 'fr-FR',
      onMessage: jest.fn(),
      onError: jest.fn(),
    });

    expect(SSE).toHaveBeenCalledWith(
      'https://api.example.com/api/user/profile-onboarding/session/session-1/run',
      {
        headers: {
          'Content-Type': 'application/json',
          'Accept-Language': 'fr-FR',
          Authorization: 'Bearer token-1',
          Token: 'token-1',
        },
        payload: JSON.stringify({
          expected_block_index: 0,
          request_id: 'run-1',
        }),
        method: 'POST',
      },
    );
    expect(source).toBe(mockSource);
    expect(mockSource.stream).toHaveBeenCalledTimes(1);
    expect(attachSseBusinessResponseFallback).toHaveBeenCalledWith(
      mockSource,
      expect.objectContaining({
        meta: expect.objectContaining({ skipErrorToast: true }),
      }),
    );
  });

  test('parses valid message events and ignores malformed frames', () => {
    const onMessage = jest.fn();
    streamProfileOnboardingRuntime({
      path: '/run',
      onMessage,
      onError: jest.fn(),
    });

    mockListeners.message?.(
      Object.assign(new Event('message'), {
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      }),
    );
    mockListeners.message?.(
      Object.assign(new Event('message'), { data: '{not-json' }),
    );

    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith({
      type: 'done',
      is_terminal: true,
    });
  });

  test('forwards network and normalized business errors', () => {
    const onError = jest.fn();
    streamProfileOnboardingRuntime({
      path: '/run',
      onMessage: jest.fn(),
      onError,
    });

    const networkError = new Event('error');
    mockListeners.error?.(networkError);
    expect(onError).toHaveBeenCalledWith(networkError);

    const fallbackOptions = (attachSseBusinessResponseFallback as jest.Mock)
      .mock.calls[0][1];
    fallbackOptions.onHandled({ message: 'busy', code: 409 });

    expect(mockSource.dispatchEvent).toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(2);
    const businessError = onError.mock.calls[1][0] as CustomEvent;
    expect(businessError.detail).toEqual({ message: 'busy', code: 409 });
    expect(
      (businessError as CustomEvent & { responseCode?: number }).responseCode,
    ).toBe(409);
  });

  test('exposes the SSE close operation for aborting an in-flight run', () => {
    const source = streamProfileOnboardingRuntime({
      path: '/run',
      onMessage: jest.fn(),
      onError: jest.fn(),
    });

    source.close();

    expect(mockSource.close).toHaveBeenCalledTimes(1);
  });
});

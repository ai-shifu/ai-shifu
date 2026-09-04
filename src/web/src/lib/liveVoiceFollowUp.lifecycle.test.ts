import type { LiveFollowUpTurnReport } from './liveVoiceFollowUp';

const mockGetToken = jest.fn();
const mockLogout = jest.fn();
const mockToast = jest.fn();

jest.mock('@/store', () => ({
  useUserStore: {
    getState: () => ({ getToken: mockGetToken, logout: mockLogout }),
  },
}));
jest.mock('@/hooks/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
  toastOnce: jest.fn(),
}));
jest.mock('@/c-utils/debugConsole', () => ({
  debugInfo: jest.fn(),
  debugWarn: jest.fn(),
  debugError: jest.fn(),
}));

const turn: LiveFollowUpTurnReport = {
  turn_index: 1,
  user_transcript: 'Final question',
  played_answer_transcript: 'Heard answer',
  interrupted: false,
  usage_metadata: null,
  latency_ms: 100,
};

const response = (body: unknown) => ({
  ok: true,
  status: 200,
  headers: new Headers(),
  json: async () => body,
});

describe('Live lifecycle reports through the shared request transport', () => {
  const originalFetch = global.fetch;
  let live: typeof import('./liveVoiceFollowUp');
  let environment: typeof import('@/config/environment');
  let requestLanguage: typeof import('./request-language');
  let fetchMock: jest.Mock;

  beforeEach(async () => {
    jest.resetModules();
    jest.clearAllMocks();
    mockGetToken.mockReturnValue('initial-token');
    window.location.pathname = '/';
    window.sessionStorage.clear();
    delete window.__HARNESS_RUN_ID__;
    fetchMock = jest.fn();
    global.fetch = fetchMock;
    live = await import('./liveVoiceFollowUp');
    environment = await import('@/config/environment');
    requestLanguage = await import('./request-language');
  });

  afterEach(() => {
    jest.restoreAllMocks();
    requestLanguage.clearPendingRequestLanguage();
    window.sessionStorage.clear();
    global.fetch = originalFetch;
  });

  const createSession = async (apiBaseUrl = '') => {
    fetchMock
      .mockResolvedValueOnce(response({ apiBaseUrl }))
      .mockResolvedValueOnce(
        response({ code: 0, data: { session_bid: 'live/session' } }),
      );
    await expect(
      live.createLiveFollowUpSession('course', 'lesson', {
        preview_mode: false,
        anchor_element_bid: 'anchor',
        learning_mode: 'read',
        surface: 'read_content',
      }),
    ).resolves.toEqual({ session_bid: 'live/session' });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/config');
    expect(environment.getCachedDynamicApiBaseUrl()).toBe(apiBaseUrl);
    fetchMock
      .mockReset()
      .mockResolvedValue(response({ code: 0, data: { ended: true } }));
  };

  it.each(['', 'https://api.example.test'])(
    'initiates native fetch before pagehide returns (base %s)',
    async apiBaseUrl => {
      await createSession(apiBaseUrl);
      mockGetToken.mockReturnValue('rotated-token');
      requestLanguage.setPendingRequestLanguage('fr-FR');
      window.sessionStorage.setItem('harness_run_id', 'lifecycle-test');
      let result: Promise<unknown> | undefined;
      const onPageHide = () => {
        result = live.finalizeLiveFollowUpSession(
          'live/session',
          [turn],
          'hidden',
        );
      };
      window.addEventListener('pagehide', onPageHide, { once: true });

      window.dispatchEvent(new Event('pagehide'));

      // No microtask or await before checking the real native-fetch boundary.
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith(
        `${apiBaseUrl || window.location.origin}/api/learn/live-follow-up/session/live%2Fsession/finalize`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ turns: [turn], reason: 'hidden' }),
          credentials: 'include',
          keepalive: true,
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Authorization: 'Bearer rotated-token',
            Token: 'rotated-token',
            'Accept-Language': 'fr-FR',
            'X-Request-ID': expect.any(String),
            'X-Harness-Run-ID': 'lifecycle-test',
          }),
        }),
      );
      await expect(result).resolves.toEqual({ ended: true });
      expect(mockToast).not.toHaveBeenCalled();
    },
  );

  it('starts end immediately and retains shared business-error handling', async () => {
    await createSession();
    fetchMock.mockResolvedValue(
      response({ code: 4018, message: 'Unavailable' }),
    );
    const result = live.endLiveFollowUpSession('live/session', 'hidden');
    const rejected = expect(result).rejects.toMatchObject({ code: 4018 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]).toEqual([
      `${window.location.origin}/api/learn/live-follow-up/session/live%2Fsession/end`,
      expect.objectContaining({
        body: JSON.stringify({ reason: 'hidden' }),
        keepalive: true,
        credentials: 'include',
      }),
    ]);
    await rejected;
    expect(mockToast).not.toHaveBeenCalled();
  });

  it('retains shared authentication recovery for lifecycle requests', async () => {
    await createSession();
    fetchMock.mockResolvedValue(response({ code: 1001 }));
    await expect(
      live.endLiveFollowUpSession('live/session', 'hidden'),
    ).rejects.toMatchObject({ code: 1001 });
    expect(mockLogout).toHaveBeenCalledWith(false);
  });

  it('rejects a cold relative keepalive without starting asynchronous preparation', async () => {
    await expect(
      live.finalizeLiveFollowUpSession('unknown-session', [turn], 'hidden'),
    ).rejects.toMatchObject({ code: -1, message: 'common.core.requestFailed' });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(mockToast).not.toHaveBeenCalled();
  });

  it.each(['request', 'defaults'])(
    'supports an absolute keepalive URL without runtime configuration (%s)',
    async source => {
      const { Request } = await import('./request');
      fetchMock.mockResolvedValue(response({ code: 0, data: 'saved' }));
      const request = new Request(
        source === 'defaults' ? { keepalive: true } : {},
      );
      const result = request.post(
        'https://api.example.test/end',
        {},
        source === 'request' ? { keepalive: true } : {},
      );
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.test/end');
      await expect(result).resolves.toBe('saved');
    },
  );
});

import { act, renderHook } from '@testing-library/react';
import apiService from '@/api';
import { useGoogleAuth } from './useGoogleAuth';

const mockLogin = jest.fn();
const mockEnsureGuestToken = jest.fn();
const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockCallWithTokenRefresh = jest.fn(
  async (callback: () => Promise<unknown>) => callback(),
);
const mockClearGoogleOAuthSession = jest.fn();
const mockGetGoogleOAuthRedirect = jest.fn();
const mockGetGoogleOAuthState = jest.fn();
const mockSetGoogleOAuthRedirect = jest.fn();
const mockSetGoogleOAuthState = jest.fn();
const mockUserState = {
  login: mockLogin,
  ensureGuestToken: mockEnsureGuestToken,
};

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    googleOauthStart: jest.fn(),
    googleOauthCallback: jest.fn(),
  },
}));

jest.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ callWithTokenRefresh: mockCallWithTokenRefresh }),
}));

jest.mock('@/store', () => ({
  useUserStore: (selector: (state: typeof mockUserState) => unknown) =>
    selector(mockUserState),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/lib/google-oauth-session', () => ({
  clearGoogleOAuthSession: () => mockClearGoogleOAuthSession(),
  getGoogleOAuthRedirect: () => mockGetGoogleOAuthRedirect(),
  getGoogleOAuthState: () => mockGetGoogleOAuthState(),
  setGoogleOAuthRedirect: (value: string) => mockSetGoogleOAuthRedirect(value),
  setGoogleOAuthState: (value: string) => mockSetGoogleOAuthState(value),
}));

const mockGoogleOauthStart = apiService.googleOauthStart as jest.Mock;
const mockGoogleOauthCallback = apiService.googleOauthCallback as jest.Mock;
const successfulGoogleCallbackResponse = {
  code: 0,
  data: {
    token: 'token-private',
    userInfo: { user_id: 'user-private' },
  },
};

describe('useGoogleAuth analytics contract', () => {
  beforeEach(() => {
    mockLogin.mockReset().mockResolvedValue(undefined);
    mockEnsureGuestToken.mockReset().mockResolvedValue(undefined);
    mockToast.mockReset();
    mockTrackEvent.mockReset();
    mockCallWithTokenRefresh.mockClear();
    mockClearGoogleOAuthSession.mockReset();
    mockGetGoogleOAuthRedirect.mockReset().mockReturnValue('/admin');
    mockGetGoogleOAuthState.mockReset().mockReturnValue('expected-state');
    mockSetGoogleOAuthRedirect.mockReset();
    mockSetGoogleOAuthState.mockReset();
    mockGoogleOauthStart.mockReset();
    mockGoogleOauthCallback.mockReset();
  });

  const loginResultCalls = () =>
    mockTrackEvent.mock.calls.filter(
      ([eventName]) => eventName === 'learner_login_result',
    );

  it('records the accepted OAuth start before the request and a bounded start failure', async () => {
    mockGoogleOauthStart.mockRejectedValue(new Error('private OAuth detail'));
    const { result } = renderHook(() => useGoogleAuth());

    await act(async () => {
      await expect(result.current.startGoogleLogin()).rejects.toThrow(
        'private OAuth detail',
      );
    });

    expect(mockTrackEvent).toHaveBeenNthCalledWith(1, 'learner_login_attempt', {
      login_method: 'google',
    });
    expect(mockTrackEvent.mock.invocationCallOrder[0]).toBeLessThan(
      mockGoogleOauthStart.mock.invocationCallOrder[0],
    );
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
      login_method: 'google',
      outcome: 'failed',
      failure_category: 'start_failed',
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private OAuth detail',
    );
  });

  it('records a successful callback without OAuth state, code, token, or identity', async () => {
    mockGoogleOauthCallback.mockResolvedValue(successfulGoogleCallbackResponse);
    const onSuccess = jest.fn();
    const { result } = renderHook(() => useGoogleAuth({ onSuccess }));

    await act(async () => {
      await result.current.finalizeGoogleLogin({
        code: 'oauth-code-private',
        state: 'expected-state',
      });
    });

    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
      login_method: 'google',
      outcome: 'success',
    });
    expect(mockTrackEvent.mock.calls.map(([name]) => name)).not.toContain(
      'learner_login_success',
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
      /oauth-code-private|expected-state|token-private|user-private/,
    );
    expect(onSuccess).toHaveBeenCalledWith(
      { user_id: 'user-private' },
      '/admin',
    );
  });

  it.each([
    'redirect resolution',
    'post-login callback',
    'success toast',
    'session cleanup',
  ] as const)(
    'keeps Google success terminal when %s throws',
    async failureStage => {
      const postLoginError = new Error(`private ${failureStage} error`);
      const onSuccess = jest.fn();
      const onError = jest.fn();
      mockGoogleOauthCallback.mockResolvedValue(
        successfulGoogleCallbackResponse,
      );

      if (failureStage === 'redirect resolution') {
        mockGetGoogleOAuthRedirect.mockImplementationOnce(() => {
          throw postLoginError;
        });
      } else if (failureStage === 'post-login callback') {
        onSuccess.mockImplementationOnce(() => {
          throw postLoginError;
        });
      } else if (failureStage === 'success toast') {
        mockToast.mockImplementationOnce(() => {
          throw postLoginError;
        });
      } else {
        mockClearGoogleOAuthSession.mockImplementationOnce(() => {
          throw postLoginError;
        });
      }

      const { result } = renderHook(() =>
        useGoogleAuth({ onSuccess, onError }),
      );

      await act(async () => {
        await expect(
          result.current.finalizeGoogleLogin({
            code: 'oauth-code-private',
            state: 'expected-state',
          }),
        ).rejects.toBe(postLoginError);
      });

      expect(mockLogin).toHaveBeenCalledTimes(1);
      expect(onError).toHaveBeenCalledWith(postLoginError);
      expect(loginResultCalls()).toEqual([
        [
          'learner_login_result',
          { login_method: 'google', outcome: 'success' },
        ],
      ]);
      const successResultIndex = mockTrackEvent.mock.calls.findIndex(
        ([eventName, payload]) =>
          eventName === 'learner_login_result' && payload.outcome === 'success',
      );
      expect(successResultIndex).toBeGreaterThanOrEqual(0);
      expect(mockLogin.mock.invocationCallOrder[0]).toBeLessThan(
        mockTrackEvent.mock.invocationCallOrder[successResultIndex],
      );
      const failingOperationOrder =
        failureStage === 'redirect resolution'
          ? mockGetGoogleOAuthRedirect.mock.invocationCallOrder[0]
          : failureStage === 'post-login callback'
            ? onSuccess.mock.invocationCallOrder[0]
            : failureStage === 'success toast'
              ? mockToast.mock.invocationCallOrder[0]
              : mockClearGoogleOAuthSession.mock.invocationCallOrder[0];
      expect(
        mockTrackEvent.mock.invocationCallOrder[successResultIndex],
      ).toBeLessThan(failingOperationOrder);
      expect(mockToast).toHaveBeenCalledWith({
        title: 'module.auth.failed',
        description: postLoginError.message,
        variant: 'destructive',
      });
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
        postLoginError.message,
      );
    },
  );

  it('separates invalid callbacks from provider callback failures', async () => {
    const { result } = renderHook(() => useGoogleAuth());

    await act(async () => {
      await expect(
        result.current.finalizeGoogleLogin({ code: null, state: null }),
      ).rejects.toThrow('Missing OAuth code');
    });
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
      login_method: 'google',
      outcome: 'failed',
      failure_category: 'callback_invalid',
    });

    mockTrackEvent.mockReset();
    mockGoogleOauthCallback.mockRejectedValue(
      new Error('private callback response'),
    );
    await act(async () => {
      await expect(
        result.current.finalizeGoogleLogin({
          code: 'private-code',
          state: 'expected-state',
        }),
      ).rejects.toThrow('private callback response');
    });
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
      login_method: 'google',
      outcome: 'failed',
      failure_category: 'callback_failed',
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private callback response',
    );

    mockTrackEvent.mockReset();
    mockGoogleOauthCallback
      .mockReset()
      .mockResolvedValue(successfulGoogleCallbackResponse);
    mockLogin.mockRejectedValueOnce(new Error('private login commit error'));
    await act(async () => {
      await expect(
        result.current.finalizeGoogleLogin({
          code: 'private-code',
          state: 'expected-state',
        }),
      ).rejects.toThrow('private login commit error');
    });
    expect(loginResultCalls()).toEqual([
      [
        'learner_login_result',
        {
          login_method: 'google',
          outcome: 'failed',
          failure_category: 'callback_failed',
        },
      ],
    ]);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private login commit error',
    );
  });
});

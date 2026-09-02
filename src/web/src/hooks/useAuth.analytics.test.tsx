import { act, renderHook } from '@testing-library/react';
import apiService from '@/api';
import { useAuth } from './useAuth';

const mockLogin = jest.fn();
const mockLogout = jest.fn();
const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockGetToken = jest.fn(() => 'token');
const mockBuildReferralLoginPayload = jest.fn();
const mockClearReferralContext = jest.fn();
const mockUserState = {
  login: mockLogin,
  logout: mockLogout,
  getToken: mockGetToken,
};

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    emailLogin: jest.fn(),
    sendEmailCode: jest.fn(),
    sendSmsCode: jest.fn(),
    smsLogin: jest.fn(),
  },
}));

jest.mock('@/store', () => {
  const useUserStore = (selector?: (state: typeof mockUserState) => unknown) =>
    selector ? selector(mockUserState) : mockUserState;
  useUserStore.getState = () => mockUserState;
  return { useUserStore };
});

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: { language: 'zh-CN' },
}));

jest.mock('@/lib/referral-context', () => ({
  buildReferralLoginPayload: (...args: unknown[]) =>
    mockBuildReferralLoginPayload(...args),
  clearReferralContext: () => mockClearReferralContext(),
}));

const mockSmsLogin = apiService.smsLogin as jest.Mock;
const mockEmailLogin = apiService.emailLogin as jest.Mock;
const mockSendEmailCode = apiService.sendEmailCode as jest.Mock;
const mockSendSmsCode = apiService.sendSmsCode as jest.Mock;

describe('useAuth login analytics contract', () => {
  beforeEach(() => {
    mockSmsLogin.mockReset();
    mockEmailLogin.mockReset();
    mockSendEmailCode.mockReset();
    mockSendSmsCode.mockReset();
    mockLogin.mockReset().mockResolvedValue(undefined);
    mockLogout.mockReset().mockResolvedValue(undefined);
    mockToast.mockReset();
    mockTrackEvent.mockReset();
    mockGetToken.mockClear();
    mockBuildReferralLoginPayload.mockReset().mockReturnValue({});
    mockClearReferralContext.mockReset();
  });

  const successfulSmsResponse = {
    code: 0,
    data: {
      userInfo: { user_id: 'user-private' },
      token: 'token-private',
    },
  };

  const loginResultCalls = () =>
    mockTrackEvent.mock.calls.filter(
      ([eventName]) => eventName === 'learner_login_result',
    );

  it('emits attempt before the request and one sanitized success result', async () => {
    mockSmsLogin.mockResolvedValue(successfulSmsResponse);
    const { result } = renderHook(() => useAuth());

    await act(async () => {
      await result.current.loginWithSmsCode('13800138000', '123456', 'zh-CN');
    });

    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_attempt', {
      login_method: 'sms',
    });
    expect(mockTrackEvent.mock.invocationCallOrder[0]).toBeLessThan(
      mockSmsLogin.mock.invocationCallOrder[0],
    );
    expect(mockSmsLogin).toHaveBeenCalledWith(
      expect.objectContaining({
        mobile: '13800138000',
        sms_code: '123456',
      }),
      { skipErrorToast: true },
    );
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
      login_method: 'sms',
      outcome: 'success',
    });
    expect(mockTrackEvent.mock.calls.map(([name]) => name)).not.toContain(
      'learner_login_success',
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
      /13800138000|123456|user-private|token-private/,
    );
  });

  it('keeps SMS success terminal when the post-login callback throws', async () => {
    const callbackError = new Error('private post-login callback error');
    const onSuccess = jest.fn(() => {
      throw callbackError;
    });
    const onError = jest.fn();
    mockSmsLogin.mockResolvedValue(successfulSmsResponse);
    const { result } = renderHook(() => useAuth({ onSuccess, onError }));

    await act(async () => {
      await expect(
        result.current.loginWithSmsCode('13800138000', '123456', 'zh-CN'),
      ).rejects.toBe(callbackError);
    });

    expect(mockLogin).toHaveBeenCalledTimes(1);
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(callbackError);
    expect(loginResultCalls()).toEqual([
      ['learner_login_result', { login_method: 'sms', outcome: 'success' }],
    ]);
    const successResultIndex = mockTrackEvent.mock.calls.findIndex(
      ([eventName, payload]) =>
        eventName === 'learner_login_result' && payload.outcome === 'success',
    );
    expect(successResultIndex).toBeGreaterThanOrEqual(0);
    expect(mockLogin.mock.invocationCallOrder[0]).toBeLessThan(
      mockTrackEvent.mock.invocationCallOrder[successResultIndex],
    );
    expect(
      mockTrackEvent.mock.invocationCallOrder[successResultIndex],
    ).toBeLessThan(onSuccess.mock.invocationCallOrder[0]);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.auth.failed',
      description: callbackError.message,
      variant: 'destructive',
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private post-login callback error',
    );
  });

  it('keeps SMS success terminal when referral cleanup throws', async () => {
    const cleanupError = new Error('private referral cleanup error');
    const onSuccess = jest.fn();
    const onError = jest.fn();
    const referralMetadata = {
      invite_code: 'AB12CD34',
      referral_session_id: 'session-1',
      referral_entry_source: 'invite_link' as const,
    };
    mockBuildReferralLoginPayload.mockReturnValue(referralMetadata);
    mockClearReferralContext.mockImplementation(() => {
      throw cleanupError;
    });
    mockSmsLogin.mockResolvedValue(successfulSmsResponse);
    const { result } = renderHook(() => useAuth({ onSuccess, onError }));

    await act(async () => {
      await expect(
        result.current.loginWithSmsCode(
          '13800138000',
          '123456',
          'zh-CN',
          referralMetadata,
        ),
      ).rejects.toBe(cleanupError);
    });

    expect(mockLogin).toHaveBeenCalledTimes(1);
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(mockClearReferralContext).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(cleanupError);
    expect(onSuccess.mock.invocationCallOrder[0]).toBeLessThan(
      mockClearReferralContext.mock.invocationCallOrder[0],
    );
    expect(loginResultCalls()).toEqual([
      ['learner_login_result', { login_method: 'sms', outcome: 'success' }],
    ]);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.auth.failed',
      description: cleanupError.message,
      variant: 'destructive',
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private referral cleanup error',
    );
  });

  it('maps rejected credentials and request errors to bounded categories', async () => {
    mockSmsLogin.mockResolvedValueOnce({
      code: 1014,
      message: 'private OTP detail',
    });
    const { result } = renderHook(() => useAuth());

    await act(async () => {
      await result.current.loginWithSmsCode(
        '13800138000',
        'wrong-code',
        'zh-CN',
      );
    });
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
      login_method: 'sms',
      outcome: 'failed',
      failure_category: 'credentials_rejected',
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private OTP detail',
    );

    mockTrackEvent.mockReset();
    mockSmsLogin.mockRejectedValueOnce(new Error('private network detail'));
    await act(async () => {
      await expect(
        result.current.loginWithSmsCode('13800138000', '123456', 'zh-CN'),
      ).rejects.toThrow('private network detail');
    });
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
      login_method: 'sms',
      outcome: 'failed',
      failure_category: 'request_failed',
    });
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private network detail',
    );
  });

  it('emits sanitized email login results and forwards referral context', async () => {
    const referralMetadata = {
      invite_code: 'AB12CD34',
      referral_session_id: 'session-1',
      referral_entry_source: 'invite_link' as const,
    };
    mockBuildReferralLoginPayload.mockReturnValue(referralMetadata);
    mockEmailLogin.mockResolvedValue({
      code: 0,
      data: {
        userInfo: { user_id: 'email-user-private' },
        token: 'email-token-private',
      },
    });
    const { result } = renderHook(() => useAuth());

    await act(async () => {
      await result.current.loginWithEmailCode(
        'private@example.com',
        '654321',
        'en-US',
        referralMetadata,
      );
    });

    expect(mockEmailLogin).toHaveBeenCalledWith(
      expect.objectContaining({
        email: 'private@example.com',
        code: '654321',
        language: 'en-US',
        ...referralMetadata,
      }),
      { skipErrorToast: true },
    );
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_attempt', {
      login_method: 'email',
    });
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
      login_method: 'email',
      outcome: 'success',
    });
    expect(mockClearReferralContext).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
      /private@example.com|654321|email-user-private|email-token-private/,
    );
  });

  it.each([1013, 1014])(
    'classifies rejected email verification error %s as rejected credentials',
    async businessCode => {
      const rejectedError = Object.assign(
        new Error('private email verification detail'),
        { code: businessCode },
      );
      mockEmailLogin.mockRejectedValue(rejectedError);
      const { result } = renderHook(() => useAuth());

      await act(async () => {
        await expect(
          result.current.loginWithEmailCode(
            'private@example.com',
            '0000',
            'en-US',
          ),
        ).rejects.toBe(rejectedError);
      });

      expect(mockTrackEvent).toHaveBeenCalledWith('learner_login_result', {
        login_method: 'email',
        outcome: 'failed',
        failure_category: 'credentials_rejected',
      });
      expect(mockEmailLogin).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'private@example.com',
          code: '0000',
        }),
        { skipErrorToast: true },
      );
      expect(mockToast).toHaveBeenCalledTimes(1);
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
        'private email verification detail',
      );
    },
  );

  it('surfaces email rate limiting as a stable result without a generic toast', async () => {
    mockSendEmailCode.mockResolvedValue({
      code: 1033,
      message: 'private localized rate-limit detail',
    });
    const { result } = renderHook(() => useAuth());

    let sendResult: { rateLimited: boolean } | undefined;
    await act(async () => {
      sendResult = await result.current.sendEmailCode('private@example.com');
    });

    expect(sendResult).toEqual({ rateLimited: true });
    expect(mockSendEmailCode).toHaveBeenCalledWith(
      {
        email: 'private@example.com',
        language: 'zh-CN',
      },
      { skipErrorToast: true },
    );
    expect(mockToast).not.toHaveBeenCalled();
  });

  it('surfaces SMS rate limiting as the same stable result', async () => {
    mockSendSmsCode.mockResolvedValue({
      code: 1012,
      message: 'private localized rate-limit detail',
    });
    const { result } = renderHook(() => useAuth());

    let sendResult: { rateLimited: boolean } | undefined;
    await act(async () => {
      sendResult = await result.current.sendSmsCode(
        '13800138000',
        'captcha-ticket',
      );
    });

    expect(sendResult).toEqual({ rateLimited: true });
    expect(mockSendSmsCode).toHaveBeenCalledWith(
      {
        mobile: '13800138000',
        captcha_ticket: 'captcha-ticket',
        language: 'zh-CN',
      },
      { skipErrorToast: true },
    );
    expect(mockToast).not.toHaveBeenCalled();
  });
});

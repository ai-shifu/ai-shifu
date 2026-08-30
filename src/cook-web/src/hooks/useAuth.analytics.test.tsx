import { act, renderHook } from '@testing-library/react';
import apiService from '@/api';
import { useAuth } from './useAuth';

const mockLogin = jest.fn();
const mockLogout = jest.fn();
const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockGetToken = jest.fn(() => 'token');
const mockClearReferralContext = jest.fn();
const mockUserState = {
  login: mockLogin,
  logout: mockLogout,
  getToken: mockGetToken,
};

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
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
  buildReferralLoginPayload: () => ({}),
  clearReferralContext: () => mockClearReferralContext(),
}));

const mockSmsLogin = apiService.smsLogin as jest.Mock;

describe('useAuth SMS analytics contract', () => {
  beforeEach(() => {
    mockSmsLogin.mockReset();
    mockLogin.mockReset().mockResolvedValue(undefined);
    mockLogout.mockReset().mockResolvedValue(undefined);
    mockToast.mockReset();
    mockTrackEvent.mockReset();
    mockGetToken.mockClear();
    mockClearReferralContext.mockReset();
  });

  it('emits attempt before the request and one sanitized success result', async () => {
    mockSmsLogin.mockResolvedValue({
      code: 0,
      data: {
        userInfo: { user_id: 'user-private' },
        token: 'token-private',
      },
    });
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
});

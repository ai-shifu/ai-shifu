import { act, fireEvent, render, screen } from '@testing-library/react';

import apiService from '@/api';
import { useUserStore } from '@/store';
import { EmailLogin } from './EmailLogin';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockClearReferralContext = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    emailLogin: jest.fn(),
    sendEmailCode: jest.fn(),
  },
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: { language: 'en-US' },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values?.count ? `${key}:${values.count}` : key,
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/lib/referral-context', () => ({
  buildReferralLoginPayload: (metadata: object | undefined) => metadata || {},
  clearReferralContext: () => mockClearReferralContext(),
}));

jest.mock('@/store', () => {
  const mockState = {
    login: jest.fn(),
    logout: jest.fn(),
    getToken: jest.fn(() => ''),
  };
  const useUserStoreMock = jest.fn(
    (selector?: (state: typeof mockState) => unknown) =>
      selector ? selector(mockState) : mockState,
  );
  (useUserStoreMock as { getState?: () => typeof mockState }).getState = () =>
    mockState;
  return { useUserStore: useUserStoreMock };
});

jest.mock('@/components/TermsCheckbox', () => ({
  TermsCheckbox: ({
    checked,
    onCheckedChange,
    disabled,
  }: {
    checked: boolean;
    onCheckedChange: (checked: boolean) => void;
    disabled?: boolean;
  }) => (
    <input
      type='checkbox'
      checked={checked}
      disabled={disabled}
      onChange={event => onCheckedChange(event.target.checked)}
    />
  ),
}));

jest.mock('@/components/auth/TermsConfirmDialog', () => ({
  TermsConfirmDialog: () => null,
}));

const mockEmailLogin = apiService.emailLogin as jest.Mock;
const mockSendEmailCode = apiService.sendEmailCode as jest.Mock;
type MockStoreState = {
  login: jest.Mock;
  logout: jest.Mock;
  getToken: jest.Mock;
};

const submitEmail = async () => {
  fireEvent.change(screen.getByLabelText('module.auth.email'), {
    target: { value: 'learner@example.com' },
  });
  fireEvent.click(screen.getByRole('checkbox'));
  await act(async () => {
    fireEvent.click(
      screen.getByRole('button', { name: 'module.auth.sendVerificationCode' }),
    );
  });
  expect(mockSendEmailCode).toHaveBeenCalledTimes(1);
};

describe('EmailLogin', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSendEmailCode.mockResolvedValue({ code: 0, data: { expire_in: 300 } });
    mockEmailLogin.mockResolvedValue({
      code: 0,
      data: {
        userInfo: { user_id: 'user-1', email: 'learner@example.com' },
        token: 'token-1',
      },
    });
    const storeState = (
      useUserStore as unknown as { getState: () => MockStoreState }
    ).getState();
    storeState.login.mockReset().mockResolvedValue(undefined);
    storeState.logout.mockReset().mockResolvedValue(undefined);
    storeState.getToken.mockReset().mockReturnValue('');
  });

  test('cleans up the active countdown when unmounted', async () => {
    jest.useFakeTimers();
    try {
      const { unmount } = render(<EmailLogin onLoginSuccess={jest.fn()} />);
      await submitEmail();

      expect(
        screen.getByRole('button', { name: 'module.auth.secondsLater:60' }),
      ).toBeDisabled();
      expect(jest.getTimerCount()).toBe(1);

      unmount();
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });

  test('uses one tailored toast for a rate-limited resend', async () => {
    mockSendEmailCode.mockResolvedValue({
      code: 1033,
      message: 'private backend detail',
    });
    render(<EmailLogin onLoginSuccess={jest.fn()} />);

    await submitEmail();

    expect(mockToast).toHaveBeenCalledTimes(1);
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.auth.checkYourEmail',
      description: 'server.user.emailSendTooFrequent',
    });
  });

  test('allows correction after cooldown and clears the stale code', async () => {
    jest.useFakeTimers();
    try {
      render(<EmailLogin onLoginSuccess={jest.fn()} />);
      await submitEmail();

      const codeInput = screen.getByPlaceholderText(
        'module.auth.verificationCodePlaceholder',
      );
      fireEvent.change(codeInput, { target: { value: '12341234' } });
      expect(codeInput).toHaveValue('1234');

      for (let second = 0; second < 60; second += 1) {
        await act(async () => {
          jest.advanceTimersByTime(1000);
        });
      }

      const emailInput = screen.getByLabelText('module.auth.email');
      expect(emailInput).toBeEnabled();
      fireEvent.change(emailInput, {
        target: { value: 'corrected@example.com' },
      });

      expect(codeInput).toBeDisabled();
      expect(codeInput).toHaveValue('');
    } finally {
      jest.useRealTimers();
    }
  });
});

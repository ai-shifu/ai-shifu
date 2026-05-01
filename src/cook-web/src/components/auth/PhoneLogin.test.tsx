import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { PhoneLogin } from './PhoneLogin';
import apiService from '@/api';
import { useUserStore } from '@/store';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getCaptcha: jest.fn(),
    verifyCaptcha: jest.fn(),
    sendSmsCode: jest.fn(),
    skillLogin: jest.fn(),
  },
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    language: 'en-US',
  },
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

jest.mock('@/store', () => {
  const mockState = {
    login: jest.fn(),
    logout: jest.fn(),
    getToken: jest.fn(() => ''),
  };
  const useUserStoreMock = jest.fn(
    (selector?: (state: typeof mockState) => any) =>
      selector ? selector(mockState) : mockState,
  );
  (useUserStoreMock as any).getState = () => mockState;
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
      id='terms'
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

describe('PhoneLogin captcha flow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (apiService.getCaptcha as jest.Mock).mockResolvedValue({
      captcha_id: 'captcha-id',
      image: 'data:image/png;base64,abc',
      expires_in: 300,
    });
    (apiService.verifyCaptcha as jest.Mock).mockResolvedValue({
      captcha_ticket: 'captcha-ticket',
      expires_in: 300,
    });
    (apiService.sendSmsCode as jest.Mock).mockResolvedValue({
      code: 0,
      data: { expire_in: 300 },
    });
    (apiService.skillLogin as jest.Mock).mockResolvedValue({
      code: 0,
      data: {
        userInfo: { user_id: 'user-1', mobile: '13800138000' },
        token: 'token-1',
      },
    });
    const mockStoreState = (useUserStore as any).getState();
    mockStoreState.login.mockClear();
    mockStoreState.logout.mockClear();
    mockStoreState.getToken.mockClear();
    (useUserStore as unknown as jest.Mock).mockClear();
  });

  test('exchanges captcha for ticket before sending SMS', async () => {
    render(<PhoneLogin onLoginSuccess={jest.fn()} />);

    await waitFor(() => expect(apiService.getCaptcha).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('module.auth.phone'), {
      target: { value: '13800138000' },
    });
    fireEvent.change(screen.getByTestId('captcha-input'), {
      target: { value: '0000' },
    });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'module.auth.getOtp' }));

    await waitFor(() =>
      expect(apiService.verifyCaptcha).toHaveBeenCalledWith({
        captcha_id: 'captcha-id',
        captcha_code: '0000',
      }),
    );
    expect(apiService.sendSmsCode).toHaveBeenCalledWith({
      mobile: '13800138000',
      captcha_ticket: 'captcha-ticket',
    });
  });

  test('logs in through skill-login after SMS code is entered', async () => {
    const onLoginSuccess = jest.fn();
    render(
      <PhoneLogin
        onLoginSuccess={onLoginSuccess}
        loginContext='admin'
        courseId='course-1'
      />,
    );

    await waitFor(() => expect(apiService.getCaptcha).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('module.auth.phone'), {
      target: { value: '13800138000' },
    });
    fireEvent.change(screen.getByTestId('captcha-input'), {
      target: { value: '0000' },
    });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'module.auth.getOtp' }));

    const otpInput = screen.getByPlaceholderText('module.auth.otpPlaceholder');
    await waitFor(() => expect(otpInput).toBeEnabled());
    fireEvent.change(otpInput, { target: { value: '9999' } });
    fireEvent.keyDown(otpInput, { key: 'Enter' });

    await waitFor(() =>
      expect(apiService.skillLogin).toHaveBeenCalledWith({
        mobile: '13800138000',
        sms_code: '9999',
        language: 'en-US',
        login_context: 'admin',
        course_id: 'course-1',
      }),
    );
    expect((useUserStore as any).getState().login).toHaveBeenCalled();
    expect(onLoginSuccess).toHaveBeenCalled();
  });

  test('does not enable SMS send without captcha code', async () => {
    render(<PhoneLogin onLoginSuccess={jest.fn()} />);

    await waitFor(() => expect(apiService.getCaptcha).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('module.auth.phone'), {
      target: { value: '13800138000' },
    });
    fireEvent.click(screen.getByRole('checkbox'));

    expect(
      screen.getByRole('button', { name: 'module.auth.getOtp' }),
    ).toBeDisabled();
  });
});

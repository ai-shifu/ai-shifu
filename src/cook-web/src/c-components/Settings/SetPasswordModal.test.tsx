import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import SetPasswordModal from './SetPasswordModal';

const mockToast = jest.fn();
const mockSendEmailCode = jest.fn();
const mockSendSmsCode = jest.fn();
const mockSetPassword = jest.fn();
const mockVerifyCaptcha = jest.fn();
const mockSetCaptchaCode = jest.fn();
const mockRefreshCaptcha = jest.fn();

const mockUserStoreState = {
  userInfo: {
    mobile: '',
    email: 'learner@example.com',
  },
};

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values?.count ? `${key}:${values.count}` : key,
  }),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    language: 'en-US',
  },
}));

jest.mock('@/store', () => ({
  useUserStore: (selector: (state: typeof mockUserStoreState) => unknown) =>
    selector(mockUserStoreState),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/hooks/useCaptchaTicket', () => ({
  useCaptchaTicket: (enabled: boolean) => ({
    captchaImage: enabled ? 'captcha-image' : '',
    captchaCode: enabled ? '1234' : '',
    setCaptchaCode: mockSetCaptchaCode,
    isCaptchaLoading: false,
    refreshCaptcha: mockRefreshCaptcha,
    verifyCaptcha: mockVerifyCaptcha,
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    sendEmailCode: (...args: unknown[]) => mockSendEmailCode(...args),
    sendSmsCode: (...args: unknown[]) => mockSendSmsCode(...args),
    setPassword: (...args: unknown[]) => mockSetPassword(...args),
  },
}));

jest.mock('./SettingBaseModal', () => ({
  __esModule: true,
  default: ({
    open,
    children,
    onOk,
    okDisabled,
    title,
    okText,
  }: {
    open: boolean;
    children: React.ReactNode;
    onOk: () => void;
    okDisabled?: boolean;
    title: string;
    okText: string;
  }) =>
    open ? (
      <div>
        <h1>{title}</h1>
        {children}
        <button
          type='button'
          onClick={onOk}
          disabled={okDisabled}
        >
          {okText}
        </button>
      </div>
    ) : null,
}));

jest.mock('@/components/auth/ImageCaptchaInput', () => ({
  ImageCaptchaInput: ({ id, value }: { id: string; value: string }) => (
    <input
      id={id}
      data-testid='captcha-input'
      readOnly
      value={value}
    />
  ),
}));

describe('SetPasswordModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSendEmailCode.mockResolvedValue({ code: 0 });
    mockSendSmsCode.mockResolvedValue({ code: 0 });
    mockSetPassword.mockResolvedValue({ code: 0 });
    mockVerifyCaptcha.mockResolvedValue('captcha-ticket');
    mockUserStoreState.userInfo = {
      mobile: '',
      email: 'learner@example.com',
    };
  });

  it('uses email verification without image captcha for an email-only user', async () => {
    render(
      <SetPasswordModal
        open
        onClose={jest.fn()}
      />,
    );

    expect(screen.getByLabelText('module.settings.email')).toHaveValue(
      'learner@example.com',
    );
    expect(screen.queryByTestId('captcha-input')).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.sendCode' }),
    );

    await waitFor(() => {
      expect(mockSendEmailCode).toHaveBeenCalledWith({
        email: 'learner@example.com',
        language: 'en-US',
      });
    });
    expect(mockSendSmsCode).not.toHaveBeenCalled();
    expect(mockVerifyCaptcha).not.toHaveBeenCalled();
  });

  it('submits the email identifier and verification code when setting a password', async () => {
    const onClose = jest.fn();
    const onSuccess = jest.fn();

    render(
      <SetPasswordModal
        open
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    fireEvent.change(
      screen.getByLabelText('module.settings.verificationCode'),
      {
        target: { value: '2468' },
      },
    );
    fireEvent.change(screen.getByLabelText('module.settings.newPassword'), {
      target: { value: 'Password1' },
    });
    fireEvent.change(screen.getByLabelText('module.settings.confirmPassword'), {
      target: { value: 'Password1' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.setPassword' }),
    );

    await waitFor(() => {
      expect(mockSetPassword).toHaveBeenCalledWith({
        identifier: 'learner@example.com',
        code: '2468',
        new_password: 'Password1',
      });
    });
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps the existing phone captcha and SMS flow for phone users', async () => {
    mockUserStoreState.userInfo = {
      mobile: '13800000000',
      email: '',
    };

    render(
      <SetPasswordModal
        open
        onClose={jest.fn()}
      />,
    );

    expect(screen.getByLabelText('module.settings.phone')).toHaveValue(
      '13800000000',
    );
    expect(screen.getByTestId('captcha-input')).toHaveValue('1234');

    fireEvent.click(
      screen.getByRole('button', { name: 'module.settings.sendCode' }),
    );

    await waitFor(() => {
      expect(mockVerifyCaptcha).toHaveBeenCalledTimes(1);
      expect(mockSendSmsCode).toHaveBeenCalledWith({
        mobile: '13800000000',
        captcha_ticket: 'captcha-ticket',
        language: 'en-US',
      });
    });
    expect(mockSendEmailCode).not.toHaveBeenCalled();
  });
});

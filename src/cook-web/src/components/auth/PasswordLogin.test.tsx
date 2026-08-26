import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { PasswordLogin } from './PasswordLogin';

const mockToast = jest.fn();
const mockLogin = jest.fn();
const mockLoginPassword = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    language: 'en-US',
  },
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/store', () => ({
  useUserStore: () => ({
    login: mockLogin,
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    loginPassword: (...args: unknown[]) => mockLoginPassword(...args),
  },
}));

jest.mock('@/components/TermsCheckbox', () => ({
  TermsCheckbox: ({
    checked,
    onCheckedChange,
  }: {
    checked: boolean;
    onCheckedChange: (checked: boolean) => void;
  }) => (
    <label>
      <input
        type='checkbox'
        checked={checked}
        onChange={event => onCheckedChange(event.target.checked)}
      />
      module.auth.terms
    </label>
  ),
}));

jest.mock('@/components/auth/TermsConfirmDialog', () => ({
  TermsConfirmDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid='terms-confirm-dialog' /> : null,
}));

describe('PasswordLogin', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('isolates both credentials when revealing and hiding the password in RTL', () => {
    render(
      <div dir='rtl'>
        <PasswordLogin onLoginSuccess={jest.fn()} />
      </div>,
    );

    const identifier = screen.getByLabelText('module.auth.identifier');
    const password = screen.getByLabelText('module.auth.password');
    expect(identifier).toHaveAttribute('type', 'text');
    expect(identifier).toHaveAttribute('data-bidi', 'ltr');
    expect(password).toHaveAttribute('type', 'password');
    expect(password).toHaveAttribute('data-bidi', 'ltr');

    fireEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(password).toHaveAttribute('type', 'text');
    expect(password).toHaveAttribute('data-bidi', 'ltr');

    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(password).toHaveAttribute('type', 'password');
    expect(password).toHaveAttribute('data-bidi', 'ltr');
  });

  it('validates email-only identifiers after trimming surrounding whitespace', async () => {
    mockLoginPassword.mockResolvedValue({
      code: 0,
      data: {
        userInfo: { user_id: 'learner' },
        token: 'token',
      },
    });

    render(
      <PasswordLogin
        onLoginSuccess={jest.fn()}
        forceEmailIdentifier
      />,
    );

    fireEvent.change(screen.getByLabelText('module.auth.email'), {
      target: { value: ' learner@example.com ' },
    });
    fireEvent.change(screen.getByLabelText('module.auth.password'), {
      target: { value: 'Password1' },
    });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'module.auth.login' }));

    expect(
      screen.queryByText('module.auth.emailError'),
    ).not.toBeInTheDocument();
    await waitFor(() => {
      expect(mockLoginPassword).toHaveBeenCalledWith({
        identifier: 'learner@example.com',
        password: 'Password1',
        language: 'en-US',
      });
    });
  });
});

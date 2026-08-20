import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

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
  TermsCheckbox: () => React.createElement('label', null, 'module.auth.terms'),
}));

jest.mock('@/components/auth/TermsConfirmDialog', () => ({
  TermsConfirmDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid='terms-confirm-dialog' /> : null,
}));

describe('PasswordLogin', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('validates email-only identifiers after trimming surrounding whitespace', () => {
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
    fireEvent.click(screen.getByRole('button', { name: 'module.auth.login' }));

    expect(
      screen.queryByText('module.auth.emailError'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('terms-confirm-dialog')).toBeInTheDocument();
  });
});

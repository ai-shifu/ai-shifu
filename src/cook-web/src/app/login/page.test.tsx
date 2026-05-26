import React from 'react';
import { render, waitFor } from '@testing-library/react';
import AuthPage from './page';

const replaceMock = jest.fn();
const logoutMock = jest.fn(() => Promise.resolve());

const mockUserState = {
  userInfo: null as { language?: string } | null,
  isLoggedIn: false,
  isInitialized: true,
  logout: logoutMock,
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
  useSearchParams: () => ({
    get: jest.fn(() => null),
  }),
}));

jest.mock('next/image', () => ({
  __esModule: true,
  default: ({ alt, src }: { alt?: string; src?: string }) => (
    <img
      alt={alt || ''}
      src={src || ''}
    />
  ),
}));

jest.mock('@/store', () => ({
  useUserStore: (selector: (state: typeof mockUserState) => unknown) =>
    selector(mockUserState),
}));

const mockEnvState = {
  logoWideUrl: '',
  loginMethodsEnabled: ['phone'],
  defaultLoginMethod: 'phone',
};

jest.mock('@/c-store', () => ({
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/config/environment', () => ({
  environment: {
    logoWideUrl: '',
    loginMethodsEnabled: ['phone'],
    defaultLoginMethod: 'phone',
  },
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  browserLanguage: 'zh-CN',
  normalizeLanguage: (value: string | null | undefined) => value || '',
  default: {
    changeLanguage: jest.fn(() => Promise.resolve()),
    hasResourceBundle: jest.fn(() => true),
    resolvedLanguage: 'zh-CN',
    language: 'zh-CN',
    options: { defaultNS: 'common' },
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    ready: true,
  }),
  Trans: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

jest.mock('@/components/auth/PhoneLogin', () => ({
  PhoneLogin: () => <div data-testid='phone-login' />,
}));

jest.mock('@/components/auth/EmailLogin', () => ({
  EmailLogin: () => <div data-testid='email-login' />,
}));

jest.mock('@/components/auth/FeedbackForm', () => ({
  FeedbackForm: () => <div data-testid='feedback-form' />,
}));

jest.mock('@/components/auth/GoogleLoginButton', () => ({
  GoogleLoginButton: () => <button type='button'>google</button>,
}));

jest.mock('@/components/auth/PasswordLogin', () => ({
  PasswordLogin: () => <div data-testid='password-login' />,
}));

jest.mock('@/components/language-select', () => ({
  __esModule: true,
  default: () => <div data-testid='language-select' />,
}));

jest.mock('@/components/TermsCheckbox', () => ({
  TermsCheckbox: () => <label>terms</label>,
}));

jest.mock('@/components/auth/TermsConfirmDialog', () => ({
  TermsConfirmDialog: () => <div data-testid='terms-dialog' />,
}));

jest.mock('@/hooks/useGoogleAuth', () => ({
  useGoogleAuth: () => ({
    startGoogleLogin: jest.fn(),
  }),
}));

jest.mock('@/components/ui/Tabs', () => ({
  Tabs: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  TabsContent: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
  TabsList: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
  TabsTrigger: ({ children }: { children?: React.ReactNode }) => (
    <button type='button'>{children}</button>
  ),
}));

jest.mock('@/components/ui/Card', () => ({
  Card: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
  CardDescription: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
  CardFooter: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
  CardHeader: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
  CardTitle: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

describe('AuthPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUserState.userInfo = null;
    mockUserState.isLoggedIn = false;
    mockUserState.isInitialized = true;
  });

  it('switches an authenticated browser session to a guest session on the login page', async () => {
    mockUserState.isLoggedIn = true;

    render(<AuthPage />);

    await waitFor(() => {
      expect(logoutMock).toHaveBeenCalledWith(false);
    });
  });

  it('does not reset an already-guest login page session', async () => {
    render(<AuthPage />);

    await waitFor(() => {
      expect(logoutMock).not.toHaveBeenCalled();
    });
  });

  it('does not reset the session created by a successful login on the login page', async () => {
    const { rerender } = render(<AuthPage />);

    await waitFor(() => {
      expect(logoutMock).not.toHaveBeenCalled();
    });

    mockUserState.isLoggedIn = true;
    rerender(<AuthPage />);

    await new Promise(resolve => setTimeout(resolve, 0));

    expect(logoutMock).not.toHaveBeenCalled();
  });
});

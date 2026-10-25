import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {
  getInstallationStatus,
  initializeAdministrator,
  loginLocalAdministrator,
} from '@/api/installation';
import { InstallationAuth } from './InstallationAuth';

const mockReplace = jest.fn();
const mockLogin = jest.fn();
const mockTrackEvent = jest.fn();
const mockRouter = { replace: mockReplace };
const session = {
  userInfo: { user_id: 'local-owner', is_operator: true },
  token: 'session-token',
};

jest.mock('next/navigation', () => ({ useRouter: () => mockRouter }));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en-US', resolvedLanguage: 'en-US' },
  }),
}));
jest.mock('@/api/installation', () => ({
  getInstallationStatus: jest.fn(),
  initializeAdministrator: jest.fn(),
  loginLocalAdministrator: jest.fn(),
}));
jest.mock('@/store/useUserStore', () => ({
  useUserStore: (selector: (state: { login: typeof mockLogin }) => unknown) =>
    selector({ login: mockLogin }),
}));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

const mockStatus = getInstallationStatus as jest.Mock;
const mockInitialize = initializeAdministrator as jest.Mock;
const mockLocalLogin = loginLocalAdministrator as jest.Mock;
const setupStatus = { setup_required: true, local_admin_login_enabled: false };
const readyStatus = { setup_required: false, local_admin_login_enabled: true };

const fillSetup = async (
  password = 'GoodPassword1',
  confirmation = password,
) => {
  await screen.findByLabelText('module.installation.codeLabel');
  fireEvent.change(screen.getByLabelText('module.installation.codeLabel'), {
    target: { value: 'single-use-test-claim' },
  });
  fireEvent.change(screen.getByLabelText('module.installation.usernameLabel'), {
    target: { value: 'Owner' },
  });
  fireEvent.change(screen.getByLabelText('module.installation.passwordLabel'), {
    target: { value: password },
  });
  fireEvent.change(
    screen.getByLabelText('module.installation.confirmPasswordLabel'),
    { target: { value: confirmation } },
  );
};

beforeEach(() => {
  jest.clearAllMocks();
  mockStatus.mockResolvedValue(setupStatus);
  mockInitialize.mockResolvedValue(session);
  mockLocalLogin.mockResolvedValue(session);
  mockLogin.mockResolvedValue(undefined);
  mockTrackEvent.mockResolvedValue(undefined);
  Object.assign(window.location, {
    protocol: 'http:',
    hostname: 'localhost',
    search: '',
  });
});

it('creates the administrator, stores the normal session and navigates without contact fields', async () => {
  render(<InstallationAuth surface='setup' />);
  await fillSetup();
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.createAdmin' }),
  );
  await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/admin'));
  expect(mockInitialize).toHaveBeenCalledWith({
    setup_token: 'single-use-test-claim',
    username: 'owner',
    password: 'GoodPassword1',
    language: 'en-US',
  });
  expect(mockLogin).toHaveBeenCalledWith(session.userInfo, session.token);
  expect(
    screen.getByLabelText('module.installation.passwordLabel'),
  ).toHaveValue('');
  expect(screen.getByLabelText('module.installation.codeLabel')).toHaveValue(
    '',
  );
  expect(mockTrackEvent.mock.calls).toEqual([
    ['installation_auth_exposure', { surface: 'setup' }],
    ['installation_auth_attempt', { surface: 'setup' }],
    [
      'installation_auth_result',
      { surface: 'setup', outcome: 'success', failure_category: 'none' },
    ],
  ]);
  expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
    /single-use|GoodPassword|owner|username|token|email|phone/,
  );
});

it('exposes the form once across re-renders and accepts only one pending request', async () => {
  let resolve!: (value: typeof session) => void;
  mockInitialize.mockReturnValue(
    new Promise(done => {
      resolve = done;
    }),
  );
  const { rerender } = render(<InstallationAuth surface='setup' />);
  await fillSetup();
  rerender(<InstallationAuth surface='setup' />);
  const button = screen.getByRole('button', {
    name: 'module.installation.createAdmin',
  });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(mockInitialize).toHaveBeenCalledTimes(1);
  expect(
    mockTrackEvent.mock.calls.filter(
      ([name]) => name === 'installation_auth_exposure',
    ),
  ).toHaveLength(1);
  await act(async () => resolve(session));
  expect(
    mockTrackEvent.mock.calls.filter(
      ([name]) => name === 'installation_auth_result',
    ),
  ).toHaveLength(1);
});

it.each([
  ['short1', 'short1', 'module.installation.passwordInvalid'],
  ['😀😀😀a1', '😀😀😀a1', 'module.installation.passwordInvalid'],
  ['GoodPassword1', 'different1', 'module.installation.passwordMismatch'],
  [
    '界'.repeat(24) + 'a1',
    '界'.repeat(24) + 'a1',
    'server.installation.passwordTooLong',
  ],
])(
  'rejects invalid setup passwords before an attempt',
  async (password, confirmation, message) => {
    render(<InstallationAuth surface='setup' />);
    await fillSetup(password, confirmation);
    fireEvent.click(
      screen.getByRole('button', { name: 'module.installation.createAdmin' }),
    );
    expect(screen.getByRole('alert')).toHaveTextContent(message);
    expect(mockInitialize).not.toHaveBeenCalled();
    expect(
      mockTrackEvent.mock.calls.some(
        ([name]) => name === 'installation_auth_attempt',
      ),
    ).toBe(false);
  },
);

it('does not accept a phone or email as a local username', async () => {
  render(<InstallationAuth surface='setup' />);
  await fillSetup();
  fireEvent.change(screen.getByLabelText('module.installation.usernameLabel'), {
    target: { value: 'owner@example.com' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.createAdmin' }),
  );
  expect(screen.getByRole('alert')).toHaveTextContent(
    'module.installation.usernameInvalid',
  );
  expect(mockInitialize).not.toHaveBeenCalled();
});

it('reports an expired or wrong code through a bounded business error', async () => {
  mockInitialize.mockRejectedValue({
    code: 12002,
    message: 'Do not expose raw provider errors',
  });
  render(<InstallationAuth surface='setup' />);
  await fillSetup();
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.createAdmin' }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'server.installation.invalidSetupToken',
  );
  expect(
    screen.queryByText('Do not expose raw provider errors'),
  ).not.toBeInTheDocument();
  expect(mockTrackEvent).toHaveBeenLastCalledWith('installation_auth_result', {
    surface: 'setup',
    outcome: 'failed',
    failure_category: 'credentials_rejected',
  });
  expect(mockLogin).not.toHaveBeenCalled();
});

it('offers normal login when a setup response may have been lost after commit', async () => {
  mockInitialize.mockRejectedValue(
    new Error('network lost after server commit'),
  );
  render(<InstallationAuth surface='setup' />);
  await fillSetup();
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.createAdmin' }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'module.installation.sessionFailed',
  );
  expect(
    screen.getByRole('link', { name: 'module.installation.loginAfterSetup' }),
  ).toHaveAttribute('href', '/admin-login');
  expect(mockTrackEvent).toHaveBeenLastCalledWith('installation_auth_result', {
    surface: 'setup',
    outcome: 'failed',
    failure_category: 'transport_or_service',
  });
});

it.each([12001, 12003])(
  'offers local login when setup is already unavailable (%s)',
  async code => {
    mockInitialize.mockRejectedValue({ code });
    render(<InstallationAuth surface='setup' />);
    await fillSetup();
    fireEvent.click(
      screen.getByRole('button', { name: 'module.installation.createAdmin' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'module.installation.sessionFailed',
    );
    expect(
      screen.getByRole('link', { name: 'module.installation.loginAfterSetup' }),
    ).toHaveAttribute('href', '/admin-login');
    expect(mockLogin).not.toHaveBeenCalled();
  },
);

it('offers login if session persistence fails after successful initialization', async () => {
  mockLogin.mockRejectedValue(new Error('storage unavailable'));
  render(<InstallationAuth surface='setup' />);
  await fillSetup();
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.createAdmin' }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'module.installation.sessionFailed',
  );
  expect(mockReplace).not.toHaveBeenCalled();
  expect(mockTrackEvent).toHaveBeenLastCalledWith('installation_auth_result', {
    surface: 'setup',
    outcome: 'failed',
    failure_category: 'session_unavailable',
  });
});

it('keeps authentication working when analytics throws', async () => {
  mockTrackEvent.mockImplementation(() => {
    throw new Error('analytics unavailable');
  });
  render(<InstallationAuth surface='setup' />);
  await fillSetup();
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.createAdmin' }),
  );
  await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/admin'));
  expect(mockLogin).toHaveBeenCalledTimes(1);
});

it('keeps authentication working when analytics rejects asynchronously', async () => {
  mockTrackEvent.mockRejectedValue(new Error('analytics unavailable'));
  render(<InstallationAuth surface='setup' />);
  await fillSetup();
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.createAdmin' }),
  );
  await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/admin'));
  expect(mockLogin).toHaveBeenCalledTimes(1);
});

it('blocks secret entry on public HTTP without emitting form exposure', async () => {
  Object.assign(window.location, {
    protocol: 'http:',
    hostname: 'app.example.com',
  });
  render(<InstallationAuth surface='setup' />);
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'module.installation.secureTransportRequired',
  );
  expect(
    screen.queryByLabelText('module.installation.codeLabel'),
  ).not.toBeInTheDocument();
  expect(mockTrackEvent).not.toHaveBeenCalled();
});

it('shows a retryable status failure and never guesses a form', async () => {
  mockStatus.mockRejectedValueOnce(new Error('status unavailable'));
  render(<InstallationAuth surface='setup' />);
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'module.installation.statusFailed',
  );
  expect(mockTrackEvent).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.retry' }),
  );
  expect(
    await screen.findByLabelText('module.installation.codeLabel'),
  ).toBeInTheDocument();
});

it('keeps setup closed after completion and provides local login', async () => {
  mockStatus.mockResolvedValue(readyStatus);
  render(<InstallationAuth surface='setup' />);
  expect(await screen.findByRole('status')).toHaveTextContent(
    'module.installation.setupClosed',
  );
  expect(
    screen.getByRole('link', { name: 'module.installation.loginAfterSetup' }),
  ).toHaveAttribute('href', '/admin-login');
  expect(
    screen.queryByLabelText('module.installation.codeLabel'),
  ).not.toBeInTheDocument();
  expect(mockTrackEvent).not.toHaveBeenCalled();
});

it('supports local login independently of learner login settings and preserves admin return paths', async () => {
  mockStatus.mockResolvedValue(readyStatus);
  Object.assign(window.location, {
    search: '?redirect=%2Fadmin%2Fbilling%3Ftab%3Ddetails',
  });
  render(<InstallationAuth surface='local_login' />);
  await screen.findByLabelText('module.installation.usernameLabel');
  fireEvent.change(screen.getByLabelText('module.installation.usernameLabel'), {
    target: { value: 'Owner' },
  });
  fireEvent.change(screen.getByLabelText('module.installation.passwordLabel'), {
    target: { value: 'GoodPassword1' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.login' }),
  );
  await waitFor(() =>
    expect(mockReplace).toHaveBeenCalledWith('/admin/billing?tab=details'),
  );
  expect(mockLocalLogin).toHaveBeenCalledWith({
    username: 'owner',
    password: 'GoodPassword1',
    language: 'en-US',
  });
  expect(mockInitialize).not.toHaveBeenCalled();
  expect(mockTrackEvent).toHaveBeenLastCalledWith('installation_auth_result', {
    surface: 'local_login',
    outcome: 'success',
    failure_category: 'none',
  });
  expect(
    screen.getByRole('link', { name: 'module.installation.otherLogin' }),
  ).toHaveAttribute('href', '/login?redirect=%2Fadmin');
});

it('keeps legacy installations on existing login and exposes no local password form', async () => {
  mockStatus.mockResolvedValue({
    setup_required: false,
    local_admin_login_enabled: false,
  });
  render(<InstallationAuth surface='local_login' />);
  expect(await screen.findByRole('status')).toHaveTextContent(
    'module.installation.localUnavailable',
  );
  expect(
    screen.queryByLabelText('module.installation.passwordLabel'),
  ).not.toBeInTheDocument();
  expect(mockTrackEvent).not.toHaveBeenCalled();
});

it('reports a rejected local password without returning to setup or leaking errors', async () => {
  mockStatus.mockResolvedValue(readyStatus);
  mockLocalLogin.mockRejectedValue({
    code: 1038,
    message: 'private backend detail',
  });
  render(<InstallationAuth surface='local_login' />);
  await screen.findByLabelText('module.installation.usernameLabel');
  fireEvent.change(screen.getByLabelText('module.installation.usernameLabel'), {
    target: { value: 'Owner' },
  });
  fireEvent.change(screen.getByLabelText('module.installation.passwordLabel'), {
    target: { value: 'WrongPassword1' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'module.installation.login' }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'module.installation.requestFailed',
  );
  expect(mockLogin).not.toHaveBeenCalled();
  expect(mockReplace).not.toHaveBeenCalled();
  expect(
    screen.queryByRole('link', { name: 'module.installation.setupLink' }),
  ).not.toBeInTheDocument();
  expect(mockTrackEvent).toHaveBeenLastCalledWith('installation_auth_result', {
    surface: 'local_login',
    outcome: 'failed',
    failure_category: 'credentials_rejected',
  });
  expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
    /WrongPassword|owner|private backend/,
  );
});

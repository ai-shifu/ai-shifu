import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import api from '@/api';
import ChangePasswordModal from './ChangePasswordModal';

const mockTrackEvent = jest.fn();
const mockToast = jest.fn();
const mockClose = jest.fn();
const mockSuccess = jest.fn();
const mockSubmitLabel = 'submit';
const mockCloseLabel = 'close';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock('@/api', () => ({
  __esModule: true,
  default: { changePassword: jest.fn() },
}));
jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));
jest.mock('./SettingBaseModal', () => {
  const { Dialog } = jest.requireActual('@/components/ui/Dialog');
  return {
    __esModule: true,
    default: ({
      open,
      children,
      onOk,
      onClose,
      okDisabled,
    }: {
      open: boolean;
      children: React.ReactNode;
      onOk: () => void;
      onClose: () => void;
      okDisabled: boolean;
    }) =>
      open ? (
        <Dialog open>
          {children}
          <button
            type='button'
            disabled={okDisabled}
            onClick={onOk}
          >
            {mockSubmitLabel}
          </button>
          <button
            type='button'
            onClick={onClose}
          >
            {mockCloseLabel}
          </button>
        </Dialog>
      ) : null,
  };
});

const mockChange = api.changePassword as jest.Mock;
const fillPasswords = (next = 'NewPassword2', confirmation = next) => {
  fireEvent.change(
    screen.getByLabelText('module.installation.currentPassword'),
    { target: { value: 'OldPassword1' } },
  );
  fireEvent.change(screen.getByLabelText('module.settings.newPassword'), {
    target: { value: next },
  });
  fireEvent.change(screen.getByLabelText('module.settings.confirmPassword'), {
    target: { value: confirmation },
  });
};

beforeEach(() => {
  jest.clearAllMocks();
  mockChange.mockResolvedValue(undefined);
  mockTrackEvent.mockResolvedValue(undefined);
  mockSuccess.mockResolvedValue(undefined);
  Object.assign(window.location, { protocol: 'http:', hostname: 'localhost' });
});

it('changes the local password without requesting a phone/email code', async () => {
  render(
    <ChangePasswordModal
      open
      onClose={mockClose}
      onSuccess={mockSuccess}
    />,
  );
  fillPasswords();
  fireEvent.click(screen.getByRole('button', { name: 'submit' }));
  await waitFor(() => expect(mockClose).toHaveBeenCalledTimes(1));
  expect(mockChange).toHaveBeenCalledWith({
    old_password: 'OldPassword1',
    new_password: 'NewPassword2',
  });
  expect(mockSuccess).toHaveBeenCalledTimes(1);
  expect(
    screen.getByLabelText('module.installation.currentPassword'),
  ).toHaveValue('');
  expect(mockTrackEvent.mock.calls).toEqual([
    ['installation_auth_exposure', { surface: 'local_password_change' }],
    ['installation_auth_attempt', { surface: 'local_password_change' }],
    [
      'installation_auth_result',
      {
        surface: 'local_password_change',
        outcome: 'success',
        failure_category: 'none',
      },
    ],
  ]);
  expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
    /OldPassword|NewPassword|old_password|new_password|email|phone/,
  );
});

it('allows password changes on another IPv4 loopback address', async () => {
  Object.assign(window.location, { hostname: '127.0.0.2' });
  render(
    <ChangePasswordModal
      open
      onClose={mockClose}
    />,
  );
  fillPasswords();
  fireEvent.click(screen.getByRole('button', { name: 'submit' }));
  await waitFor(() => expect(mockClose).toHaveBeenCalledTimes(1));
  expect(mockChange).toHaveBeenCalledWith({
    old_password: 'OldPassword1',
    new_password: 'NewPassword2',
  });
});

it('submits from the password field on Enter with the same attempt guard', async () => {
  render(
    <ChangePasswordModal
      open
      onClose={mockClose}
    />,
  );
  fillPasswords();
  fireEvent.keyDown(screen.getByLabelText('module.settings.confirmPassword'), {
    key: 'Enter',
  });
  await waitFor(() => expect(mockClose).toHaveBeenCalledTimes(1));
  expect(mockChange).toHaveBeenCalledTimes(1);
});

it('deduplicates double submission and does not close a pending operation', async () => {
  let resolve!: () => void;
  mockChange.mockReturnValue(
    new Promise<void>(done => {
      resolve = done;
    }),
  );
  render(
    <ChangePasswordModal
      open
      onClose={mockClose}
    />,
  );
  fillPasswords();
  const submit = screen.getByRole('button', { name: 'submit' });
  fireEvent.click(submit);
  fireEvent.click(submit);
  fireEvent.click(screen.getByRole('button', { name: 'close' }));
  expect(mockChange).toHaveBeenCalledTimes(1);
  expect(mockClose).not.toHaveBeenCalled();
  await act(async () => resolve());
  expect(mockClose).toHaveBeenCalledTimes(1);
  expect(
    mockTrackEvent.mock.calls.filter(
      ([name]) => name === 'installation_auth_result',
    ),
  ).toHaveLength(1);
});

it.each([
  ['short1', 'short1', 'module.installation.passwordInvalid'],
  ['NewPassword2', 'different2', 'module.installation.passwordMismatch'],
  [
    '界'.repeat(24) + 'a1',
    '界'.repeat(24) + 'a1',
    'server.installation.passwordTooLong',
  ],
])(
  'rejects invalid replacement credentials before an attempt',
  async (next, confirmation, error) => {
    render(
      <ChangePasswordModal
        open
        onClose={mockClose}
      />,
    );
    fillPasswords(next, confirmation);
    fireEvent.click(screen.getByRole('button', { name: 'submit' }));
    expect(screen.getByRole('alert')).toHaveTextContent(error);
    expect(mockChange).not.toHaveBeenCalled();
    expect(
      mockTrackEvent.mock.calls.some(
        ([name]) => name === 'installation_auth_attempt',
      ),
    ).toBe(false);
  },
);

it('reports an incorrect current password without leaking server details', async () => {
  mockChange.mockRejectedValue({
    code: 1038,
    message: 'private server response',
  });
  render(
    <ChangePasswordModal
      open
      onClose={mockClose}
    />,
  );
  fillPasswords();
  fireEvent.click(screen.getByRole('button', { name: 'submit' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'module.installation.requestFailed',
  );
  expect(mockClose).not.toHaveBeenCalled();
  expect(mockTrackEvent).toHaveBeenLastCalledWith('installation_auth_result', {
    surface: 'local_password_change',
    outcome: 'failed',
    failure_category: 'credentials_rejected',
  });
});

it('preserves a real password update when tracking or refresh fails', async () => {
  mockTrackEvent.mockImplementation(() => {
    throw new Error('tracking unavailable');
  });
  mockSuccess.mockRejectedValue(new Error('profile refresh unavailable'));
  render(
    <ChangePasswordModal
      open
      onClose={mockClose}
      onSuccess={mockSuccess}
    />,
  );
  fillPasswords();
  fireEvent.click(screen.getByRole('button', { name: 'submit' }));
  await waitFor(() => expect(mockClose).toHaveBeenCalledTimes(1));
  expect(mockChange).toHaveBeenCalledTimes(1);
});

it('counts exposure once per open and clears secrets between opens', () => {
  const { rerender } = render(
    <ChangePasswordModal
      open
      onClose={mockClose}
    />,
  );
  fillPasswords();
  rerender(
    <ChangePasswordModal
      open
      onClose={mockClose}
    />,
  );
  expect(
    mockTrackEvent.mock.calls.filter(
      ([name]) => name === 'installation_auth_exposure',
    ),
  ).toHaveLength(1);
  rerender(
    <ChangePasswordModal
      open={false}
      onClose={mockClose}
    />,
  );
  rerender(
    <ChangePasswordModal
      open
      onClose={mockClose}
    />,
  );
  expect(
    screen.getByLabelText('module.installation.currentPassword'),
  ).toHaveValue('');
  expect(
    mockTrackEvent.mock.calls.filter(
      ([name]) => name === 'installation_auth_exposure',
    ),
  ).toHaveLength(2);
});

it('refuses to collect passwords over public HTTP', () => {
  Object.assign(window.location, {
    protocol: 'http:',
    hostname: 'app.example.com',
  });
  render(
    <ChangePasswordModal
      open
      onClose={mockClose}
    />,
  );
  expect(screen.getByRole('alert')).toHaveTextContent(
    'module.installation.secureTransportRequired',
  );
  expect(
    screen.queryByLabelText('module.installation.currentPassword'),
  ).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'submit' })).toBeDisabled();
  expect(mockTrackEvent).not.toHaveBeenCalled();
});

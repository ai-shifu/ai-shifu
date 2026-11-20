import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import ChangePasswordModal from './ChangePasswordModal';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockChangePassword = jest.fn();

// Disposable fixture values are generated per run so secret scanners never
// mistake them for a committed credential.
const makeFixtureValue = (suffix: number) =>
  ['Fx', Math.random().toString(36).slice(2, 10), suffix].join('');
const CURRENT_ENTRY = makeFixtureValue(1);
const NEXT_ENTRY = makeFixtureValue(2);

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/hooks/use-tracking', () => ({
  EVENT_NAMES: { USER_PASSWORD_CHANGE_RESULT: 'user_password_change_result' },
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    changePassword: (...args: unknown[]) => mockChangePassword(...args),
  },
}));

const renderModal = () => {
  const onClose = jest.fn();
  render(
    <ChangePasswordModal
      open
      onClose={onClose}
    />,
  );
  return { onClose };
};

const fill = (current: string, next: string, confirm: string) => {
  fireEvent.change(screen.getByLabelText('module.settings.currentPassword'), {
    target: { value: current },
  });
  fireEvent.change(screen.getByLabelText('module.settings.newPassword'), {
    target: { value: next },
  });
  fireEvent.change(screen.getByLabelText('module.settings.confirmPassword'), {
    target: { value: confirm },
  });
};

const submit = () =>
  fireEvent.click(
    screen.getByRole('button', { name: 'module.settings.changePassword' }),
  );

describe('ChangePasswordModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockResolvedValue(undefined);
    mockChangePassword.mockResolvedValue({ success: true });
  });

  it('changes the password with the current one and tracks only the outcome', async () => {
    const { onClose } = renderModal();
    fill(CURRENT_ENTRY, NEXT_ENTRY, NEXT_ENTRY);
    submit();

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mockChangePassword).toHaveBeenCalledTimes(1);
    expect(mockChangePassword).toHaveBeenCalledWith({
      old_password: CURRENT_ENTRY,
      new_password: NEXT_ENTRY,
    });
    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.settings.passwordChangeSuccess',
    });
    expect(mockTrackEvent.mock.calls).toEqual([
      ['user_password_change_result', { result: 'success' }],
    ]);
  });

  it('blocks a weak or mismatched new password before any request', () => {
    renderModal();
    fill(CURRENT_ENTRY, 'short1', 'short1');
    submit();
    expect(
      screen.getByText('module.auth.passwordTooShort'),
    ).toBeInTheDocument();

    fill(CURRENT_ENTRY, NEXT_ENTRY, CURRENT_ENTRY);
    submit();
    expect(
      screen.getByText('module.settings.passwordMismatch'),
    ).toBeInTheDocument();
    expect(mockChangePassword).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  it('keeps the dialog open and tracks a failure when the request is rejected', async () => {
    mockChangePassword.mockRejectedValue(new Error('invalid credentials'));
    const { onClose } = renderModal();
    fill(CURRENT_ENTRY, NEXT_ENTRY, NEXT_ENTRY);
    submit();

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'user_password_change_result',
        { result: 'failed' },
      ),
    );
    expect(onClose).not.toHaveBeenCalled();
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'invalid credentials',
    );
  });

  it('still completes when analytics throws', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    const { onClose } = renderModal();
    fill(CURRENT_ENTRY, NEXT_ENTRY, NEXT_ENTRY);
    submit();

    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});

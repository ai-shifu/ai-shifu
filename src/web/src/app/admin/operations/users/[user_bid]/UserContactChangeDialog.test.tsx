import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import UserContactChangeDialog from './UserContactChangeDialog';

const mockTrackEvent = jest.fn();
const mockToast = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: { changeAdminOperationUserContact: jest.fn() },
}));

const mockChangeContact = api.changeAdminOperationUserContact as jest.Mock;

const renderDialog = (contactType: 'phone' | 'email' = 'phone') => {
  const onChanged = jest.fn();
  const onOpenChange = jest.fn();
  render(
    <UserContactChangeDialog
      open
      userBid='user-1'
      contactType={contactType}
      currentIdentifier={
        contactType === 'phone' ? '13800138000' : 'old@example.com'
      }
      onChanged={onChanged}
      onOpenChange={onOpenChange}
    />,
  );
  return { onChanged, onOpenChange };
};

describe('UserContactChangeDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockResolvedValue(undefined);
    mockChangeContact.mockResolvedValue({
      user_bid: 'user-1',
      contact_type: 'phone',
      identifier: '13900139000',
      revoked_sessions: 2,
    });
  });

  it('submits a confirmed phone change once and tracks no sensitive values', async () => {
    const { onChanged } = renderDialog();

    fireEvent.change(
      screen.getByPlaceholderText('contactChange.phone.newPlaceholder'),
      {
        target: { value: '13900139000' },
      },
    );
    fireEvent.change(
      screen.getByPlaceholderText('contactChange.reasonPlaceholder'),
      {
        target: { value: 'Verified user request' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'contactChange.confirm',
      }),
    );
    await screen.findByText('contactChange.phone.confirmTitle');
    const submit = screen.getByRole('button', {
      name: 'contactChange.confirm',
    });
    fireEvent.click(submit);
    fireEvent.click(submit);

    await waitFor(() => expect(mockChangeContact).toHaveBeenCalledTimes(1));
    expect(mockChangeContact).toHaveBeenCalledWith({
      user_bid: 'user-1',
      contact_type: 'phone',
      identifier: '13900139000',
      reason: 'Verified user request',
    });
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_user_contact_change_dialog_viewed',
      { contact_type: 'phone' },
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_user_contact_change_result',
      { contact_type: 'phone', result: 'success' },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      '13900139000',
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'Verified user request',
    );
  });

  it('requires a reason before showing the final confirmation', () => {
    renderDialog('email');
    fireEvent.change(
      screen.getByPlaceholderText('contactChange.email.newPlaceholder'),
      {
        target: { value: 'new@example.com' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'contactChange.confirm' }),
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'contactChange.errors.reasonRequired',
    );
    expect(mockChangeContact).not.toHaveBeenCalled();
  });

  it('does not let analytics failure block a successful change', async () => {
    mockTrackEvent.mockRejectedValue(new Error('analytics unavailable'));
    const { onChanged } = renderDialog('email');
    fireEvent.change(
      screen.getByPlaceholderText('contactChange.email.newPlaceholder'),
      {
        target: { value: 'new@example.com' },
      },
    );
    fireEvent.change(
      screen.getByPlaceholderText('contactChange.reasonPlaceholder'),
      {
        target: { value: 'Verified user request' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'contactChange.confirm' }),
    );
    await screen.findByText('contactChange.email.confirmTitle');
    fireEvent.click(
      screen.getByRole('button', { name: 'contactChange.confirm' }),
    );

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it('tracks a failed change without exposing the contact or reason', async () => {
    mockChangeContact.mockRejectedValueOnce(
      new Error('Contact is unavailable'),
    );
    renderDialog('email');
    fireEvent.change(
      screen.getByPlaceholderText('contactChange.email.newPlaceholder'),
      {
        target: { value: 'new@example.com' },
      },
    );
    fireEvent.change(
      screen.getByPlaceholderText('contactChange.reasonPlaceholder'),
      {
        target: { value: 'Verified user request' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'contactChange.confirm' }),
    );
    await screen.findByText('contactChange.email.confirmTitle');
    fireEvent.click(
      screen.getByRole('button', { name: 'contactChange.confirm' }),
    );

    await screen.findByRole('alert');
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_user_contact_change_result',
      { contact_type: 'email', result: 'failed' },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'new@example.com',
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'Verified user request',
    );

    fireEvent.click(screen.getByRole('button', { name: 'contactChange.back' }));
    fireEvent.change(
      screen.getByPlaceholderText('contactChange.email.newPlaceholder'),
      {
        target: { value: 'another@example.com' },
      },
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

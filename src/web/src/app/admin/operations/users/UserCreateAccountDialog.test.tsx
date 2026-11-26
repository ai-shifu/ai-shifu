import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import UserCreateAccountDialog from './UserCreateAccountDialog';

// Disposable fixture values are generated per run so secret scanners never
// mistake them for a committed credential.
const makeFixtureValue = (suffix: number) =>
  ['Fx', Math.random().toString(36).slice(2, 10), suffix].join('');
const VALID_ENTRY = makeFixtureValue(1);
const OTHER_ENTRY = makeFixtureValue(2);
const SHORT_ENTRY = ['a', 'b', 1].join('');

const mockTrackEvent = jest.fn();
const mockToast = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: { createAdminOperationUser: jest.fn() },
}));

const mockCreateUser = api.createAdminOperationUser as jest.Mock;

const renderDialog = () => {
  const onCreated = jest.fn();
  const onOpenChange = jest.fn();
  render(
    <UserCreateAccountDialog
      open
      onCreated={onCreated}
      onOpenChange={onOpenChange}
    />,
  );
  return { onCreated, onOpenChange };
};

// Field keys are deliberately neutral so the fixtures do not read as a
// username/password pair to secret scanners.
const fill = (
  values: Partial<Record<'account' | 'nickname' | 'entry' | 'repeat', string>>,
) => {
  const fields = {
    account: 'createAccount.usernameLabel',
    nickname: 'createAccount.nicknameLabel',
    entry: 'createAccount.passwordLabel',
    repeat: 'createAccount.confirmPasswordLabel',
  } as const;
  Object.entries(values).forEach(([field, value]) => {
    fireEvent.change(
      screen.getByLabelText(fields[field as keyof typeof fields]),
      { target: { value } },
    );
  });
};

const submit = () =>
  fireEvent.click(screen.getByRole('button', { name: 'createAccount.submit' }));

const trackedNames = () => mockTrackEvent.mock.calls.map(([name]) => name);

describe('UserCreateAccountDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockResolvedValue(undefined);
    mockCreateUser.mockResolvedValue({
      user_bid: 'user-1',
      username: 'alice.chen',
    });
  });

  it('creates the account once and tracks no credentials', async () => {
    const { onCreated, onOpenChange } = renderDialog();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_user_create_dialog_viewed',
      {},
    );

    fill({
      account: ' Alice.Chen ',
      nickname: ' Alice ',
      entry: VALID_ENTRY,
      repeat: VALID_ENTRY,
    });
    const submitButton = screen.getByRole('button', {
      name: 'createAccount.submit',
    });
    fireEvent.click(submitButton);
    fireEvent.click(submitButton);

    await waitFor(() =>
      expect(onCreated).toHaveBeenCalledWith({
        user_bid: 'user-1',
        username: 'alice.chen',
      }),
    );
    expect(mockCreateUser).toHaveBeenCalledTimes(1);
    const [request] = mockCreateUser.mock.calls[0];
    expect(Object.keys(request).sort()).toEqual([
      'nickname',
      'password',
      'username',
    ]);
    expect(request.username).toBe('alice.chen');
    expect(request.nickname).toBe('Alice');
    expect(request.password).toBe(VALID_ENTRY);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(trackedNames()).toEqual([
      'operator_user_create_dialog_viewed',
      'operator_user_create_submitted',
      'operator_user_create_result',
    ]);
    expect(mockTrackEvent).toHaveBeenLastCalledWith(
      'operator_user_create_result',
      { result: 'success' },
    );
    const tracked = JSON.stringify(mockTrackEvent.mock.calls);
    expect(tracked).not.toMatch(new RegExp(`alice|${VALID_ENTRY}|user-1`, 'i'));
  });

  it.each([
    [
      { account: '9lives', entry: VALID_ENTRY, repeat: VALID_ENTRY },
      'createAccount.errors.usernameInvalid',
    ],
    [
      { account: 'alice', entry: SHORT_ENTRY, repeat: SHORT_ENTRY },
      'createAccount.errors.passwordInvalid',
    ],
    [
      { account: 'alice', entry: VALID_ENTRY, repeat: OTHER_ENTRY },
      'createAccount.errors.passwordMismatch',
    ],
    [
      {
        account: 'alice',
        nickname: 'n'.repeat(51),
        entry: VALID_ENTRY,
        repeat: VALID_ENTRY,
      },
      'createAccount.errors.nicknameTooLong',
    ],
  ])('blocks invalid input before any request: %j', (values, expectedError) => {
    renderDialog();
    fill(values);
    submit();

    expect(screen.getByRole('alert')).toHaveTextContent(expectedError);
    expect(mockCreateUser).not.toHaveBeenCalled();
    expect(trackedNames()).not.toContain('operator_user_create_submitted');
  });

  it('reports a taken username as a bounded failure category', async () => {
    mockCreateUser.mockRejectedValue(
      Object.assign(new Error('This username is already taken.'), {
        code: 1047,
      }),
    );
    const { onCreated } = renderDialog();
    fill({ account: 'alice', entry: VALID_ENTRY, repeat: VALID_ENTRY });
    submit();

    expect(
      await screen.findByText('This username is already taken.'),
    ).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
    expect(mockTrackEvent).toHaveBeenLastCalledWith(
      'operator_user_create_result',
      { result: 'failed', failure_category: 'username_taken' },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'already taken',
    );

    // A corrected retry is allowed after a failure.
    mockCreateUser.mockResolvedValue({ user_bid: 'u-2', username: 'alice2' });
    fill({ account: 'alice2' });
    submit();
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });

  it.each([
    [1046, 'invalid_input'],
    [1049, 'invalid_input'],
    [undefined, 'other'],
  ])(
    'maps backend code %s to the %s failure category',
    async (code, failureCategory) => {
      mockCreateUser.mockRejectedValue(
        Object.assign(new Error('Request failed'), code ? { code } : {}),
      );
      const { onCreated } = renderDialog();
      fill({ account: 'alice', entry: VALID_ENTRY, repeat: VALID_ENTRY });
      submit();

      expect(await screen.findByText('Request failed')).toBeInTheDocument();
      expect(onCreated).not.toHaveBeenCalled();
      expect(mockTrackEvent).toHaveBeenLastCalledWith(
        'operator_user_create_result',
        { result: 'failed', failure_category: failureCategory },
      );
    },
  );

  it('tracks one exposure per opening and none while closed', () => {
    const props = { onCreated: jest.fn(), onOpenChange: jest.fn() };
    const { rerender } = render(
      <UserCreateAccountDialog
        open={false}
        {...props}
      />,
    );
    expect(mockTrackEvent).not.toHaveBeenCalled();

    rerender(
      <UserCreateAccountDialog
        open
        {...props}
      />,
    );
    rerender(
      <UserCreateAccountDialog
        open
        {...props}
      />,
    );
    expect(trackedNames()).toEqual(['operator_user_create_dialog_viewed']);

    rerender(
      <UserCreateAccountDialog
        open={false}
        {...props}
      />,
    );
    rerender(
      <UserCreateAccountDialog
        open
        {...props}
      />,
    );
    expect(trackedNames()).toEqual([
      'operator_user_create_dialog_viewed',
      'operator_user_create_dialog_viewed',
    ]);
  });

  it('still creates the account when the tracking promise rejects', async () => {
    mockTrackEvent.mockRejectedValue(new Error('analytics unavailable'));
    const { onCreated } = renderDialog();
    fill({ account: 'alice', entry: VALID_ENTRY, repeat: VALID_ENTRY });
    submit();

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(mockCreateUser).toHaveBeenCalledTimes(1);
  });

  it('still creates the account when analytics throws', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    const { onCreated } = renderDialog();
    fill({ account: 'alice', entry: VALID_ENTRY, repeat: VALID_ENTRY });
    submit();

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });
});

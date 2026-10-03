import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import type { AdminOperationUserItem } from '../operation-user-types';
import UserSubscriptionTerminationDialog from './UserSubscriptionTerminationDialog';

const mockTerminate = api.terminateAdminOperationUserSubscription as jest.Mock;
const mockTrackEvent = jest.fn();
const mockToast = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: { terminateAdminOperationUserSubscription: jest.fn() },
}));
jest.mock('uuid', () => ({ v4: () => 'termination-request-id' }));
jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));
jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const user: AdminOperationUserItem = {
  user_bid: 'user-1',
  mobile: '15500000000',
  email: '',
  nickname: '',
  user_status: 'paid',
  user_role: 'regular',
  user_roles: [],
  login_methods: [],
  registration_source: 'phone',
  language: 'zh-CN',
  learning_courses: [],
  learning_course_count: 0,
  created_courses: [],
  created_course_count: 0,
  total_paid_amount: '100',
  available_credits: '10',
  subscription_credits: '10',
  topup_credits: '0',
  credits_expire_at: '',
  has_active_subscription: true,
  can_terminate_paid_subscription: true,
  termination_subscription_bid: 'subscription-1',
  last_login_at: '',
  last_learning_at: '',
  created_at: '',
  updated_at: '',
};

describe('UserSubscriptionTerminationDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('requires a reason and terminates the paid plan once', async () => {
    const onTerminated = jest.fn();
    mockTerminate.mockResolvedValue({
      status: 'terminated',
      user_bid: 'user-1',
      subscription_bid: 'subscription-1',
      provider: 'stripe',
      forfeited_credits: '10',
      replayed: false,
    });
    render(
      <UserSubscriptionTerminationDialog
        open
        user={user}
        onOpenChange={jest.fn()}
        onTerminated={onTerminated}
      />,
    );
    expect(screen.getByText('subscription-1')).toBeInTheDocument();

    fireEvent.click(screen.getByText('terminationDialog.confirm'));
    expect(
      screen.getByText('terminationDialog.errors.reason'),
    ).toBeInTheDocument();
    expect(mockTerminate).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('terminationDialog.reason'), {
      target: { value: 'customer request' },
    });
    fireEvent.click(screen.getByText('terminationDialog.confirm'));

    await waitFor(() =>
      expect(mockTerminate).toHaveBeenCalledWith({
        user_bid: 'user-1',
        subscription_bid: 'subscription-1',
        request_id: 'termination-request-id',
        reason: 'customer request',
      }),
    );
    expect(onTerminated).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_subscription_termination_attempt',
      { surface: 'operator_user_management' },
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_subscription_termination_result',
      { surface: 'operator_user_management', outcome: 'success' },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      '15500000000',
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain('user-1');
  });

  test('keeps submission single-flight and tracking failures do not block it', async () => {
    let resolveRequest: (value: object) => void = () => {};
    mockTerminate.mockReturnValue(
      new Promise(resolve => {
        resolveRequest = resolve;
      }),
    );
    mockTrackEvent.mockImplementation(() => {
      throw new Error('tracking unavailable');
    });
    const onTerminated = jest.fn();
    render(
      <UserSubscriptionTerminationDialog
        open
        user={user}
        onOpenChange={jest.fn()}
        onTerminated={onTerminated}
      />,
    );

    fireEvent.change(screen.getByLabelText('terminationDialog.reason'), {
      target: { value: 'customer request' },
    });
    const confirm = screen.getByText('terminationDialog.confirm');
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(mockTerminate).toHaveBeenCalledTimes(1);

    resolveRequest({
      status: 'terminated',
      user_bid: 'user-1',
      subscription_bid: 'subscription-1',
      provider: 'stripe',
      forfeited_credits: '10',
      replayed: false,
    });
    await waitFor(() => expect(onTerminated).toHaveBeenCalledTimes(1));
    expect(screen.getByText('terminationDialog.confirm')).toBeEnabled();
  });

  test('tracks a failed terminal outcome without exposing request data', async () => {
    mockTerminate.mockRejectedValue(new Error('provider unavailable'));
    render(
      <UserSubscriptionTerminationDialog
        open
        user={user}
        onOpenChange={jest.fn()}
        onTerminated={jest.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText('terminationDialog.reason'), {
      target: { value: 'private operator note' },
    });
    fireEvent.click(screen.getByText('terminationDialog.confirm'));

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'operator_subscription_termination_result',
        { surface: 'operator_user_management', outcome: 'failed' },
      ),
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private operator note',
    );
  });
});

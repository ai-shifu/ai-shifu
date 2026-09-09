import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import UserCancellationDialog from './UserCancellationDialog';
import type {
  AdminOperationUserCancellationPreview,
  AdminOperationUserItem,
} from '../operation-user-types';

const mockTrackEvent = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationUserCancellationPreview: jest.fn(),
    transferAdminOperationUserPublishedCourses: jest.fn(),
    cancelAdminOperationUserSubscriptionRenewals: jest.fn(),
    cancelAdminOperationUser: jest.fn(),
    getAdminOperationUserCancellationStatus: jest.fn(),
  },
}));

const user = {
  user_bid: 'user-1',
  mobile: '138****0000',
  email: '',
  nickname: 'Learner',
  user_status: 'registered',
  user_role: 'learner',
  user_roles: ['learner'],
  login_methods: ['phone'],
  registration_source: 'phone',
  language: 'zh-CN',
  learning_courses: [],
  learning_course_count: 0,
  created_courses: [],
  created_course_count: 0,
  total_paid_amount: '0',
  available_credits: '20',
  subscription_credits: '0',
  topup_credits: '20',
  credits_expire_at: '',
  has_active_subscription: false,
  last_login_at: '',
  last_learning_at: '',
  created_at: '',
  updated_at: '',
} satisfies AdminOperationUserItem;

const preview = (
  overrides: Partial<AdminOperationUserCancellationPreview> = {},
): AdminOperationUserCancellationPreview => ({
  user: {
    user_bid: user.user_bid,
    identifier: '13800000000',
    masked_identifier: user.mobile,
    nickname: user.nickname,
    is_creator: false,
    is_operator: false,
  },
  can_cancel: true,
  blockers: [],
  warnings: [],
  draft_course_count: 0,
  published_courses: [],
  subscription_renewal_count: 0,
  paid_packages: [],
  paid_preorder_count: 0,
  preorder_packages: [],
  renewing_packages: [],
  unsettled_order_count: 0,
  available_credits: 20,
  reserved_credits: 0,
  active_session_count: 1,
  preview_version: 'preview-1',
  ...overrides,
});

const mockPreview = api.getAdminOperationUserCancellationPreview as jest.Mock;
const mockTransfer =
  api.transferAdminOperationUserPublishedCourses as jest.Mock;
const mockCancelRenewals =
  api.cancelAdminOperationUserSubscriptionRenewals as jest.Mock;
const mockCancel = api.cancelAdminOperationUser as jest.Mock;
const mockCancellationStatus =
  api.getAdminOperationUserCancellationStatus as jest.Mock;

const renderDialog = (onCancelled = jest.fn()) => {
  render(
    <UserCancellationDialog
      open
      user={user}
      contactType='phone'
      onOpenChange={jest.fn()}
      onCancelled={onCancelled}
    />,
  );
  return { onCancelled };
};

describe('UserCancellationDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockResolvedValue(undefined);
    mockPreview.mockResolvedValue(preview());
    mockCancel.mockResolvedValue({
      cancellation_bid: 'case-1',
      status: 'completed',
    });
    mockCancellationStatus.mockResolvedValue({
      cancellation_bid: 'case-1',
      status: 'completed',
    });
  });

  it('confirms cancellation and tracks only allowlisted properties', async () => {
    const { onCancelled } = renderDialog();
    await screen.findByPlaceholderText('cancellation.reasonPlaceholder');

    fireEvent.change(
      screen.getByPlaceholderText('cancellation.reasonPlaceholder'),
      { target: { value: 'Requested by support after verification' } },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'cancellation.continue' }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'cancellation.confirm' }),
    );

    await waitFor(() => expect(mockCancel).toHaveBeenCalledTimes(1));
    expect(mockCancel).toHaveBeenCalledWith(
      expect.objectContaining({
        user_bid: user.user_bid,
        preview_version: 'preview-1',
        reason: 'Requested by support after verification',
      }),
    );
    expect(onCancelled).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_user_cancellation_attempt',
      { surface: 'user_list' },
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'operator_user_cancellation_result',
      { surface: 'user_list', outcome: 'success' },
    );
    for (const [, properties] of mockTrackEvent.mock.calls) {
      expect(properties).not.toHaveProperty('user_bid');
      expect(properties).not.toHaveProperty('reason');
      expect(properties).not.toHaveProperty('identifier');
    }
  });

  it('shows the full account identifier and explains short reasons', async () => {
    renderDialog();
    expect(await screen.findByText('13800000000')).toBeInTheDocument();

    fireEvent.change(
      screen.getByPlaceholderText('cancellation.reasonPlaceholder'),
      { target: { value: 'no' } },
    );

    expect(screen.getByText('cancellation.reasonTooShort')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'cancellation.continue' }),
    ).toBeDisabled();
  });

  it('cancels renewals before showing final confirmation', async () => {
    mockPreview.mockResolvedValue(
      preview({
        can_cancel: false,
        blockers: [{ code: 'subscription_cancellation_required', count: 1 }],
        subscription_renewal_count: 1,
      }),
    );
    mockCancelRenewals.mockResolvedValue({ preview: preview() });
    renderDialog();
    await screen.findByPlaceholderText('cancellation.reasonPlaceholder');

    fireEvent.change(
      screen.getByPlaceholderText('cancellation.reasonPlaceholder'),
      { target: { value: 'Customer confirmed cancellation' } },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'cancellation.continue' }),
    );

    expect(
      await screen.findByRole('button', { name: 'cancellation.confirm' }),
    ).toBeInTheDocument();
    expect(mockCancelRenewals).toHaveBeenCalledWith({
      user_bid: user.user_bid,
    });
  });

  it('keeps cancellation blocked until published courses are transferred', async () => {
    mockPreview.mockResolvedValue(
      preview({
        can_cancel: false,
        blockers: [
          { code: 'published_course_transfer_required', count: 1 },
          { code: 'subscription_cancellation_required', count: 1 },
        ],
        published_courses: [{ shifu_bid: 'course-1', course_name: 'Course' }],
        subscription_renewal_count: 1,
      }),
    );
    renderDialog();
    await screen.findByPlaceholderText('cancellation.reasonPlaceholder');
    fireEvent.change(
      screen.getByPlaceholderText('cancellation.reasonPlaceholder'),
      { target: { value: 'Customer confirmed cancellation' } },
    );

    expect(
      screen.getByRole('button', { name: 'cancellation.continue' }),
    ).toBeDisabled();
    expect(
      screen.getByText('cancellation.transferRequired'),
    ).toBeInTheDocument();
    expect(mockCancelRenewals).not.toHaveBeenCalled();
  });

  it('transfers published courses and refreshes the preview in place', async () => {
    mockPreview
      .mockResolvedValueOnce(
        preview({
          can_cancel: false,
          blockers: [{ code: 'published_course_transfer_required', count: 1 }],
          published_courses: [{ shifu_bid: 'course-1', course_name: 'Course' }],
        }),
      )
      .mockResolvedValueOnce(preview());
    mockTransfer.mockResolvedValue({ transferred_count: 1 });
    renderDialog();

    fireEvent.change(
      await screen.findByPlaceholderText(
        'cancellation.transferPhonePlaceholder',
      ),
      { target: { value: '13900000000' } },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'cancellation.transfer' }),
    );

    await waitFor(() =>
      expect(mockTransfer).toHaveBeenCalledWith({
        user_bid: user.user_bid,
        contact_type: 'phone',
        identifier: '13900000000',
      }),
    );
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));
  });

  it('does not let analytics failures block cancellation', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    const { onCancelled } = renderDialog();
    await screen.findByPlaceholderText('cancellation.reasonPlaceholder');
    fireEvent.change(
      screen.getByPlaceholderText('cancellation.reasonPlaceholder'),
      { target: { value: 'Customer confirmed cancellation' } },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'cancellation.continue' }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'cancellation.confirm' }),
    );

    await waitFor(() => expect(onCancelled).toHaveBeenCalledTimes(1));
  });

  it('waits for an accepted background cancellation to complete', async () => {
    mockCancel.mockResolvedValue({
      cancellation_bid: 'case-1',
      status: 'pending',
    });
    mockCancellationStatus
      .mockResolvedValueOnce({
        cancellation_bid: 'case-1',
        status: 'retrying',
      })
      .mockResolvedValueOnce({
        cancellation_bid: 'case-1',
        status: 'completed',
      });
    const { onCancelled } = renderDialog();
    await screen.findByPlaceholderText('cancellation.reasonPlaceholder');
    fireEvent.change(
      screen.getByPlaceholderText('cancellation.reasonPlaceholder'),
      { target: { value: 'Customer confirmed cancellation' } },
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'cancellation.continue' }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'cancellation.confirm' }),
    );

    await waitFor(() =>
      expect(mockCancellationStatus).toHaveBeenCalledWith({
        user_bid: user.user_bid,
        cancellation_bid: 'case-1',
      }),
    );
    await waitFor(() => expect(onCancelled).toHaveBeenCalledTimes(1));
    expect(mockCancellationStatus).toHaveBeenCalledTimes(2);
  });
});

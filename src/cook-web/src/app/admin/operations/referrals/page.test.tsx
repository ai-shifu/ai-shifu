import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import AdminOperationReferralsPage from './page';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationReferrals: jest.fn(),
    getAdminOperationReferralsOverview: jest.fn(),
    getAdminOperationReferralDetail: jest.fn(),
    updateAdminOperationReferralStatus: jest.fn(),
  },
}));

jest.mock('@/app/admin/operations/useOperatorGuard', () => ({
  __esModule: true,
  default: () => ({ isReady: true }),
}));

jest.mock('react-i18next', () => {
  const t = (key: string, values?: Record<string, unknown>) =>
    values
      ? `module.referral.${key}:${JSON.stringify(values)}`
      : `module.referral.${key}`;

  return {
    useTranslation: () => ({
      t,
    }),
  };
});

const relation = {
  relation_bid: 'relation-1',
  campaign_bid: 'campaign-1',
  campaign_code: 'domestic_creator_invite_202606',
  campaign_name: 'Referral',
  reward_rule_bid: 'rule-1',
  invite_code: 'AB12CD34',
  inviter_user_bid: 'user-inviter',
  inviter: { identifier: '13800000000' },
  invitee_user_bid: 'user-invitee',
  invitee: { identifier: '13900000000' },
  invitee_mobile_snapshot: '13900000000',
  bound_at: '2026-06-09T12:00:00',
  registration_source: 'phone',
  reward_eligible: true,
  relation_status: 7832,
  abnormal_status: 7841,
  metadata: {},
  reward: {
    reward_bid: 'reward-1',
    reward_status: 7852,
    reward_target: 'inviter',
    reward_type: 'billing_plan_cycle',
    reward_product_code: 'creator-plan-monthly-pro',
    reward_cycle_count: 1,
    reward_credit_amount: '1000',
    reward_credit_validity_days: 30,
    reward_cap_scope: 'per_inviter',
    reward_cap_count: 12,
    reward_timing_policy: 'immediate_extend_or_defer',
    rule_snapshot: {},
    billing_artifacts: {
      bill_order_bid: 'order-1',
    },
    operator_note: '',
    effective_at: null,
    expires_at: null,
    created_at: '2026-06-09T12:00:00',
    updated_at: '2026-06-09T12:00:00',
  },
  reward_queue: [
    {
      queue_index: 1,
      reward_bid: 'reward-queue-1',
      relation_bid: 'relation-queue-1',
      invitee_user_bid: 'invitee-queue-1',
      invitee_mobile_snapshot: '13900000001',
      reward_status: 7852,
      reward_credit_amount: '1000.0000000000',
      reward_product_code: 'creator-plan-monthly-pro',
      bill_order_bid: 'order-queue-1',
      subscription_bid: 'sub-queue-1',
      wallet_bucket_bid: 'bucket-queue-1',
      ledger_bid: 'ledger-queue-1',
      ledger_credit_state: 'reserved',
      effective_at: '2026-07-01T00:00:00',
      expires_at: '2026-08-01T00:00:00',
      created_at: '2026-06-09T12:00:00',
    },
    {
      queue_index: 2,
      reward_bid: 'reward-queue-2',
      relation_bid: 'relation-queue-2',
      invitee_user_bid: 'invitee-queue-2',
      invitee_mobile_snapshot: '13900000002',
      reward_status: 7853,
      reward_credit_amount: '1000.0000000000',
      reward_product_code: 'creator-plan-monthly-pro',
      bill_order_bid: 'order-queue-2',
      subscription_bid: 'sub-queue-2',
      wallet_bucket_bid: 'bucket-queue-2',
      ledger_bid: 'ledger-queue-2',
      ledger_credit_state: 'available',
      effective_at: '2026-08-01T00:00:00',
      expires_at: '2026-09-01T00:00:00',
      created_at: '2026-06-09T13:00:00',
    },
  ],
  created_at: '2026-06-09T12:00:00',
  updated_at: '2026-06-09T12:00:00',
};

describe('AdminOperationReferralsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getAdminOperationReferralsOverview as jest.Mock).mockResolvedValue({
      total_relations: 1,
      abnormal_relations: 0,
      generated_rewards: 1,
    });
    (api.getAdminOperationReferrals as jest.Mock).mockResolvedValue({
      items: [relation],
      page_index: 1,
      page_size: 20,
      total: 1,
    });
    (api.getAdminOperationReferralDetail as jest.Mock).mockResolvedValue(
      relation,
    );
    (api.updateAdminOperationReferralStatus as jest.Mock).mockResolvedValue({
      ...relation,
      abnormal_status: 7842,
    });
  });

  test('renders referral rows and overview metrics', async () => {
    render(<AdminOperationReferralsPage />);

    await screen.findByText('domestic_creator_invite_202606');

    await waitFor(() =>
      expect(screen.getByText('user-inviter')).toBeInTheDocument(),
    );
    expect(screen.getByText('13900000000')).toBeInTheDocument();
    expect(screen.getByText('AB12CD34')).toBeInTheDocument();
  });

  test('opens relation detail and sends status update', async () => {
    render(<AdminOperationReferralsPage />);

    await screen.findByText('domestic_creator_invite_202606');
    const detailButton = await screen.findByTestId(
      'referral-detail-relation-1',
    );
    fireEvent.click(detailButton);

    await waitFor(() =>
      expect(api.getAdminOperationReferralDetail).toHaveBeenCalledWith({
        relation_bid: 'relation-1',
      }),
    );

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.referral.operator.actions.markReviewing',
      }),
    );

    await waitFor(() =>
      expect(api.updateAdminOperationReferralStatus).toHaveBeenCalledWith(
        expect.objectContaining({
          relation_bid: 'relation-1',
          abnormal_status: 'reviewing',
        }),
      ),
    );
  });

  test('renders inviter reward queue in relation detail', async () => {
    render(<AdminOperationReferralsPage />);

    await screen.findByText('domestic_creator_invite_202606');
    fireEvent.click(await screen.findByTestId('referral-detail-relation-1'));

    expect(
      await screen.findByText(
        'module.referral.operator.detail.rewardQueue.title',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('reward-queue-1')).toBeInTheDocument();
    expect(screen.getByText('reward-queue-2')).toBeInTheDocument();
    expect(screen.getByText('order-queue-1')).toBeInTheDocument();
    expect(screen.getByText('ledger-queue-1')).toBeInTheDocument();
    expect(screen.getByText('13900000001')).toBeInTheDocument();
    expect(screen.getByText('2026-07-01T00:00:00')).toBeInTheDocument();
    expect(screen.getAllByText('2026-08-01T00:00:00')).toHaveLength(2);
    expect(screen.getByText('reserved')).toBeInTheDocument();
    expect(screen.getByText('available')).toBeInTheDocument();
  });
});

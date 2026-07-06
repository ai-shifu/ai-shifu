import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { copyText } from '@/c-utils/textutils';
import AdminReferralPage from './page';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getReferralInviteProfile: jest.fn(),
  },
}));

jest.mock('@/c-utils/textutils', () => ({
  copyText: jest.fn(),
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage?: string }) => (
    <div>{errorMessage || 'error'}</div>
  ),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en-US' },
    t: (key: string, values?: Record<string, unknown>) =>
      values ? `${key}:${JSON.stringify(values)}` : key,
  }),
}));

describe('AdminReferralPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (copyText as jest.Mock).mockResolvedValue(undefined);
    (api.getReferralInviteProfile as jest.Mock).mockResolvedValue({
      campaign_bid: 'campaign-1',
      campaign_code: 'domestic_creator_invite_202606',
      invite_code: 'AB12CD34',
      invite_url: 'https://app.example.com/invite/AB12CD34',
      reward_product_code: 'creator-plan-monthly-pro',
      reward_cycle_count: 1,
      reward_credit_amount: '1000.0000000000',
      reward_credit_validity_days: 30,
      reward_cap_scope: 'per_inviter',
      reward_cap_count: 12,
      reward_granted_count: 3,
      reward_remaining_count: 9,
      reward_queue_summary: {
        '7852': 1,
      },
      reward_queue: [
        {
          queue_index: 1,
          reward_bid: 'reward-profile-queue',
          relation_bid: 'relation-profile-queue',
          invitee_mobile_snapshot: '135****0781',
          reward_status: 7852,
          reward_credit_amount: '1000.0000000000',
          reward_product_code: 'creator-plan-monthly-pro',
          ledger_credit_state: 'reserved',
          effective_at: '2026-06-26T13:18:00',
          expires_at: '2026-07-26T13:18:00',
          created_at: '2026-06-11T12:00:00',
        },
      ],
      rules_copy_i18n_key: 'module.referral.rules.default',
    });
  });

  test('renders invite link, earned rewards, rules, and invite records', async () => {
    render(<AdminReferralPage />);

    await screen.findByDisplayValue('https://app.example.com/invite/AB12CD34');

    expect(screen.queryByText('common.core.home')).not.toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('creator.inviteCardTitle')).toBeInTheDocument();
    expect(screen.getByText('creator.rewardRulesTitle')).toBeInTheDocument();
    expect(screen.getByText('creator.rules.unregistered')).toBeInTheDocument();
    expect(screen.getByText('creator.queueTitle')).toBeInTheDocument();
    expect(screen.getAllByText(/"credits":"1,000"/).length).toBeGreaterThan(0);
    expect(
      screen.queryByText('creator.metrics.remaining'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('creator.metrics.cap')).not.toBeInTheDocument();
    expect(screen.queryByText('AB12CD34')).not.toBeInTheDocument();
    expect(screen.queryByText('1000.0000000000')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'creator.refresh' }),
    ).not.toBeInTheDocument();
  });

  test('copies invite link', async () => {
    render(<AdminReferralPage />);

    await screen.findByDisplayValue('https://app.example.com/invite/AB12CD34');
    fireEvent.click(screen.getByRole('button', { name: 'creator.copyLink' }));

    await waitFor(() =>
      expect(copyText).toHaveBeenCalledWith(
        'creator.shareMessage:{"url":"https://app.example.com/invite/AB12CD34"}',
      ),
    );
  });

  test('renders masked invite record rows', async () => {
    render(<AdminReferralPage />);

    await screen.findByText('creator.queueColumns.invitee');

    expect(screen.queryByText('#1')).not.toBeInTheDocument();
    expect(screen.getByText('135****0781')).toBeInTheDocument();
    expect(screen.queryByText('13521510781')).not.toBeInTheDocument();
    expect(screen.getAllByText(/"credits":"1,000"/).length).toBeGreaterThan(0);
    expect(screen.getByText('2026-06-26T13:18:00')).toBeInTheDocument();
    expect(screen.getByText('2026-07-26T13:18:00')).toBeInTheDocument();
    expect(
      screen.queryByText('creator.ledgerStates.reserved'),
    ).not.toBeInTheDocument();
  });

  test('hides invite page content when referral campaign is unavailable', async () => {
    (api.getReferralInviteProfile as jest.Mock).mockResolvedValueOnce({
      available: false,
      campaign_bid: '',
      campaign_code: '',
      invite_code: '',
      invite_url: '',
      reward_product_code: '',
      reward_cycle_count: 0,
      reward_credit_amount: null,
      reward_credit_validity_days: null,
      reward_cap_scope: '',
      reward_cap_count: null,
      reward_granted_count: 0,
      reward_remaining_count: null,
      reward_queue_summary: {},
      reward_queue: [],
      rules_copy_i18n_key: '',
    });

    const { container } = render(<AdminReferralPage />);

    await waitFor(() =>
      expect(api.getReferralInviteProfile).toHaveBeenCalledTimes(1),
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText('creator.title')).not.toBeInTheDocument();
    expect(
      screen.queryByText('creator.inviteCardTitle'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('error')).not.toBeInTheDocument();
  });
});

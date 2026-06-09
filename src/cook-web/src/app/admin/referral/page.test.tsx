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
      reward_credit_amount: '1000',
      reward_credit_validity_days: 30,
      reward_cap_scope: 'per_inviter',
      reward_cap_count: 12,
      reward_granted_count: 3,
      reward_remaining_count: 9,
      reward_queue_summary: {
        '7852': 1,
      },
      rules_copy_i18n_key: 'module.referral.rules.default',
    });
  });

  test('renders invite link, invite code, and reward counters', async () => {
    render(<AdminReferralPage />);

    await screen.findByDisplayValue('https://app.example.com/invite/AB12CD34');

    expect(screen.getByText('AB12CD34')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  test('copies invite link', async () => {
    render(<AdminReferralPage />);

    await screen.findByDisplayValue('https://app.example.com/invite/AB12CD34');
    fireEvent.click(screen.getByRole('button', { name: 'creator.copyLink' }));

    await waitFor(() =>
      expect(copyText).toHaveBeenCalledWith(
        'https://app.example.com/invite/AB12CD34',
      ),
    );
  });
});

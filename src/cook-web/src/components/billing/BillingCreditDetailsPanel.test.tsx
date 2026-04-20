import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  useBillingOverview,
  useBillingWalletBuckets,
} from '@/hooks/useBillingData';
import { BillingCreditDetailsPanel } from './BillingCreditDetailsPanel';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/hooks/useBillingData', () => ({
  __esModule: true,
  useBillingOverview: jest.fn(),
  useBillingWalletBuckets: jest.fn(),
}));

const mockUseBillingOverview = useBillingOverview as jest.Mock;
const mockUseBillingWalletBuckets = useBillingWalletBuckets as jest.Mock;

describe('BillingCreditDetailsPanel', () => {
  beforeEach(() => {
    mockUseBillingOverview.mockReset();
    mockUseBillingWalletBuckets.mockReset();

    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 1110,
          reserved_credits: 0,
          lifetime_granted_credits: 2000,
          lifetime_consumed_credits: 890,
        },
        subscription: null,
        billing_alerts: [],
        trial_offer: {
          enabled: true,
          status: 'ineligible',
          product_bid: 'bill-product-plan-trial',
          product_code: 'creator-plan-trial',
          display_name: 'module.billing.package.free.title',
          description: 'module.billing.package.free.description',
          currency: 'CNY',
          price_amount: 0,
          credit_amount: 100,
          valid_days: 15,
          highlights: [
            'module.billing.package.features.free.publish',
            'module.billing.package.features.free.preview',
          ],
          starts_on_first_grant: true,
          granted_at: null,
          expires_at: null,
        },
      },
      error: undefined,
      isLoading: false,
    });
    mockUseBillingWalletBuckets.mockReturnValue({
      data: {
        items: [
          {
            wallet_bucket_bid: 'bucket-sub-1',
            category: 'subscription',
            source_type: 'gift',
            source_bid: 'gift-1',
            available_credits: 10,
            effective_from: '2026-04-01T00:00:00',
            effective_to: '2026-08-12T23:59:00',
            priority: 20,
            status: 'active',
          },
          {
            wallet_bucket_bid: 'bucket-sub-2',
            category: 'subscription',
            source_type: 'subscription',
            source_bid: 'sub-1',
            available_credits: 90,
            effective_from: '2026-04-01T00:00:00',
            effective_to: null,
            priority: 20,
            status: 'active',
          },
          {
            wallet_bucket_bid: 'bucket-topup',
            category: 'topup',
            source_type: 'topup',
            source_bid: 'topup-1',
            available_credits: 1000,
            effective_from: '2026-04-01T00:00:00',
            effective_to: '2026-10-20T23:59:00',
            priority: 30,
            status: 'active',
          },
        ],
      },
      error: undefined,
      isLoading: false,
    });
  });

  test('renders total credits and aggregated bucket categories', async () => {
    const user = userEvent.setup();
    const onUpgrade = jest.fn();
    render(<BillingCreditDetailsPanel onUpgrade={onUpgrade} />);

    expect(
      screen.getByText('module.billing.details.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('1,110.00')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.category.subscription'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.category.topup'),
    ).toBeInTheDocument();
    expect(screen.getByText('1,000.00')).toBeInTheDocument();
    expect(screen.getByText('2026.08.12 23:59')).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', {
        name: 'module.billing.details.actions.upgradeNow',
      }),
    );

    expect(onUpgrade).toHaveBeenCalledTimes(1);
  });
});

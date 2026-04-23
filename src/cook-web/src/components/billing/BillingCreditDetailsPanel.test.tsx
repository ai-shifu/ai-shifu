import React from 'react';
import { act, render, screen, within } from '@testing-library/react';
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
      language: 'zh-CN',
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
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'product-plan-paid',
          product_code: 'creator-plan-pro',
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00',
          current_period_end_at: '2026-10-12T23:59:00',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
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
            source_type: 'manual',
            source_bid: 'manual-1',
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
            effective_to: '2026-10-12T23:59:00',
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

  test('renders subscription credits in one row and prefers the active subscription expiry', async () => {
    const user = userEvent.setup();
    const onUpgrade = jest.fn();
    render(<BillingCreditDetailsPanel onUpgrade={onUpgrade} />);

    expect(
      screen.getByText('module.billing.details.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('1,110.00')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.billing.ledger.category.subscription'),
    ).toHaveLength(1);
    expect(
      screen.getByText('module.billing.ledger.category.topup'),
    ).toBeInTheDocument();
    expect(screen.getByText('100.00')).toBeInTheDocument();
    expect(screen.getByText('1,000.00')).toBeInTheDocument();
    expect(screen.getByText('2026年10月12日 23:59')).toBeInTheDocument();
    expect(screen.getByText('2026年10月20日 23:59')).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', {
        name: 'module.billing.details.actions.upgradeNow',
      }),
    );

    expect(onUpgrade).toHaveBeenCalledTimes(1);
  });

  test('falls back to the earliest manual grant expiry when no active subscription remains', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120,
          reserved_credits: 0,
          lifetime_granted_credits: 2000,
          lifetime_consumed_credits: 1880,
        },
        subscription: {
          subscription_bid: 'sub-expired',
          product_bid: 'product-plan-trial',
          product_code: 'creator-plan-trial',
          status: 'expired',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00',
          current_period_end_at: '2026-04-16T23:59:00',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
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
          highlights: [],
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
            wallet_bucket_bid: 'bucket-manual-1',
            category: 'subscription',
            source_type: 'manual',
            source_bid: 'manual-1',
            available_credits: 20,
            effective_from: '2026-04-01T00:00:00',
            effective_to: '2026-05-06T07:59:00',
            priority: 20,
            status: 'active',
          },
          {
            wallet_bucket_bid: 'bucket-manual-2',
            category: 'subscription',
            source_type: 'manual',
            source_bid: 'manual-2',
            available_credits: 100,
            effective_from: '2026-04-01T00:00:00',
            effective_to: '2026-05-23T10:00:00',
            priority: 20,
            status: 'active',
          },
        ],
      },
      error: undefined,
      isLoading: false,
    });

    render(<BillingCreditDetailsPanel />);

    const subscriptionLabel = screen.getByText(
      'module.billing.ledger.category.subscription',
    );
    const subscriptionRow = subscriptionLabel.closest('.grid');

    expect(subscriptionRow).not.toBeNull();
    expect(
      screen.getByText('module.billing.ledger.category.topup'),
    ).toBeInTheDocument();
    expect(subscriptionLabel).toBeInTheDocument();
    expect(
      within(subscriptionRow as HTMLElement).getByText('120.00'),
    ).toBeInTheDocument();
    expect(
      within(subscriptionRow as HTMLElement).getByText('2026年05月06日 07:59'),
    ).toBeInTheDocument();
  });

  test('does not fall back to manual grant expiry while an active subscription still exists', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 35,
          reserved_credits: 0,
          lifetime_granted_credits: 2000,
          lifetime_consumed_credits: 1965,
        },
        subscription: {
          subscription_bid: 'sub-active-no-expiry',
          product_bid: 'product-plan-paid',
          product_code: 'creator-plan-pro',
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00',
          current_period_end_at: null,
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
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
          highlights: [],
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
            wallet_bucket_bid: 'bucket-manual-active-subscription',
            category: 'subscription',
            source_type: 'manual',
            source_bid: 'manual-1',
            available_credits: 35,
            effective_from: '2026-04-01T00:00:00',
            effective_to: '2026-05-06T07:59:00',
            priority: 20,
            status: 'active',
          },
        ],
      },
      error: undefined,
      isLoading: false,
    });

    render(<BillingCreditDetailsPanel />);

    const subscriptionLabel = screen.getByText(
      'module.billing.ledger.category.subscription',
    );
    const subscriptionRow = subscriptionLabel.closest('.grid');

    expect(subscriptionRow).not.toBeNull();
    expect(
      within(subscriptionRow as HTMLElement).getByText(
        'module.billing.ledger.neverExpires',
      ),
    ).toBeInTheDocument();
    expect(
      within(subscriptionRow as HTMLElement).queryByText(
        '2026年05月06日 07:59',
      ),
    ).not.toBeInTheDocument();
  });

  test('shows a tooltip for topup availability when the topup bucket has no expiry', async () => {
    const user = userEvent.setup();

    mockUseBillingWalletBuckets.mockReturnValue({
      data: {
        items: [
          {
            wallet_bucket_bid: 'bucket-topup',
            category: 'topup',
            source_type: 'topup',
            source_bid: 'topup-1',
            available_credits: 1000,
            effective_from: '2026-04-01T00:00:00',
            effective_to: null,
            priority: 30,
            status: 'active',
          },
        ],
      },
      error: undefined,
      isLoading: false,
    });

    render(<BillingCreditDetailsPanel />);

    expect(
      screen.getByText('module.billing.details.topupAvailabilityLabel'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.hover(
        screen.getByTestId('billing-topup-validity-tooltip-trigger'),
      );
    });

    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'module.billing.details.topupAvailabilityTooltip',
    );
  });
});

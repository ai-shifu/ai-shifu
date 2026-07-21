import React from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
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

jest.mock('@/lib/browser-timezone', () => ({
  __esModule: true,
  getBrowserTimeZone: () => 'Asia/Shanghai',
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
    jest.useFakeTimers().setSystemTime(new Date('2026-04-15T00:00:00Z'));
    mockUseBillingOverview.mockReset();
    mockUseBillingWalletBuckets.mockReset();

    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 1110.7,
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

  afterEach(() => {
    jest.useRealTimers();
  });

  test('renders subscription credits in one row and prefers the active subscription expiry', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    const onUpgrade = jest.fn();
    render(<BillingCreditDetailsPanel onUpgrade={onUpgrade} />);

    expect(
      within(screen.getByTestId('billing-credit-details-panel')).queryByRole(
        'heading',
        { level: 1 },
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('module.billing.details.totalCreditsLabel'),
    ).toBeInTheDocument();
    expect(screen.getByText('1,110')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.billing.ledger.category.subscription'),
    ).toHaveLength(1);
    expect(
      screen.getByText('module.billing.ledger.category.topup'),
    ).toBeInTheDocument();
    expect(screen.getByText('100.00')).toBeInTheDocument();
    expect(screen.getByText('1,000.00')).toBeInTheDocument();
    expect(screen.getByText('2026-10-13 07:59')).toBeInTheDocument();
    expect(screen.getByText('2026-10-21 07:59')).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', {
        name: 'module.billing.details.actions.upgradeNow',
      }),
    );

    expect(onUpgrade).toHaveBeenCalledTimes(1);
  });

  test('revalidates wallet buckets after the overview snapshot loads', async () => {
    const refreshWalletBuckets = jest.fn();
    mockUseBillingWalletBuckets.mockReturnValue({
      data: { items: [] },
      error: undefined,
      isLoading: false,
      mutate: refreshWalletBuckets,
    });

    render(<BillingCreditDetailsPanel />);

    await waitFor(() => {
      expect(refreshWalletBuckets).toHaveBeenCalledTimes(1);
    });
  });

  test('revalidates wallet buckets when the subscription period changes', async () => {
    const refreshWalletBuckets = jest.fn();
    const overview = mockUseBillingOverview().data;
    mockUseBillingOverview.mockImplementation(() => ({
      data: overview,
      error: undefined,
      isLoading: false,
    }));
    mockUseBillingWalletBuckets.mockReturnValue({
      data: { items: [] },
      error: undefined,
      isLoading: false,
      mutate: refreshWalletBuckets,
    });

    const { rerender } = render(<BillingCreditDetailsPanel />);

    await waitFor(() => {
      expect(refreshWalletBuckets).toHaveBeenCalledTimes(1);
    });

    mockUseBillingOverview.mockImplementation(() => ({
      data: {
        ...overview,
        subscription: {
          ...overview.subscription,
          current_period_end_at: '2026-11-12T23:59:00',
        },
      },
      error: undefined,
      isLoading: false,
    }));

    rerender(<BillingCreditDetailsPanel />);

    await waitFor(() => {
      expect(refreshWalletBuckets).toHaveBeenCalledTimes(2);
    });
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
      within(subscriptionRow as HTMLElement).getByText('2026-05-06 15:59'),
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
      within(subscriptionRow as HTMLElement).queryByText('2026-05-06 15:59'),
    ).not.toBeInTheDocument();
  });

  test('excludes future and expired buckets from the current credit summary', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 245.81,
          reserved_credits: 0,
          lifetime_granted_credits: 2200,
          lifetime_consumed_credits: 1954.19,
        },
        subscription: {
          subscription_bid: 'sub-active',
          product_bid: 'product-plan-paid',
          product_code: 'creator-plan-pro',
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-07-01T00:00:00Z',
          current_period_end_at: '2026-08-01T00:00:00Z',
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
            wallet_bucket_bid: 'bucket-current',
            category: 'subscription',
            source_type: 'subscription',
            source_bid: 'sub-active',
            available_credits: 245.81,
            effective_from: '2026-07-01T00:00:00Z',
            effective_to: '2026-08-01T00:00:00Z',
            priority: 20,
            status: 'active',
          },
          {
            wallet_bucket_bid: 'bucket-future',
            category: 'subscription',
            source_type: 'subscription',
            source_bid: 'sub-future',
            available_credits: 1684.76,
            effective_from: '2026-07-23T15:59:59Z',
            effective_to: '2026-08-23T15:59:59Z',
            priority: 20,
            status: 'active',
          },
          {
            wallet_bucket_bid: 'bucket-expired',
            category: 'topup',
            source_type: 'topup',
            source_bid: 'topup-expired',
            available_credits: 99,
            effective_from: '2026-06-01T00:00:00Z',
            effective_to: '2026-07-01T00:00:00Z',
            priority: 30,
            status: 'active',
          },
        ],
      },
      error: undefined,
      isLoading: false,
    });
    jest.setSystemTime(new Date('2026-07-19T00:00:00Z'));

    render(<BillingCreditDetailsPanel />);

    const subscriptionLabel = screen.getByText(
      'module.billing.ledger.category.subscription',
    );
    const subscriptionRow = subscriptionLabel.closest('.grid');
    const topupLabel = screen.getByText('module.billing.ledger.category.topup');
    const topupRow = topupLabel.closest('.grid');

    expect(screen.getByText('245')).toBeInTheDocument();
    expect(subscriptionRow).not.toBeNull();
    expect(
      within(subscriptionRow as HTMLElement).getByText('245.81'),
    ).toBeInTheDocument();
    expect(screen.queryByText('1,684.76')).not.toBeInTheDocument();
    expect(screen.queryByText('99.00')).not.toBeInTheDocument();
    expect(topupRow).not.toBeNull();
    expect(
      within(topupRow as HTMLElement).getByText('0.00'),
    ).toBeInTheDocument();
  });

  test('does not count topup buckets when there is no active subscription', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 15,
          reserved_credits: 0,
          lifetime_granted_credits: 1015,
          lifetime_consumed_credits: 1000,
        },
        subscription: null,
        billing_alerts: [],
        trial_offer: {
          enabled: true,
          status: 'eligible',
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
            wallet_bucket_bid: 'bucket-manual',
            category: 'subscription',
            source_type: 'manual',
            source_bid: 'manual-1',
            available_credits: 15,
            effective_from: '2026-04-01T00:00:00Z',
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
            effective_from: '2026-04-01T00:00:00Z',
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

    const subscriptionLabel = screen.getByText(
      'module.billing.ledger.category.subscription',
    );
    const topupLabel = screen.getByText('module.billing.ledger.category.topup');

    expect(
      within(subscriptionLabel.closest('.grid') as HTMLElement).getByText(
        '15.00',
      ),
    ).toBeInTheDocument();
    expect(
      within(topupLabel.closest('.grid') as HTMLElement).getByText('0.00'),
    ).toBeInTheDocument();
    expect(screen.queryByText('1,000.00')).not.toBeInTheDocument();
  });

  test('shows a tooltip for topup availability when the topup bucket has no expiry', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

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

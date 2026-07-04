import React from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import { useBillingOverview } from '@/hooks/useBillingData';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import useSWR, { mutate as mutateSWRCache } from 'swr';
import { openBillingCheckoutUrl } from '@/lib/billing';
import { BillingOverviewTab } from './BillingOverviewTab';

const mockEnvState = {
  billingEnabled: 'true',
  paymentChannels: ['stripe', 'pingxx'],
  runtimeConfigLoaded: true,
  stripeEnabled: 'true',
};

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (options?.date) {
        return `${key}:${options.date}`;
      }
      if (
        (key === 'module.billing.package.campaign.bonusBadge' ||
          key === 'module.billing.checkout.bonusCreditsLabel') &&
        options
      ) {
        return `${key}:${String(options.credits || options.baseCredits || '')}:${String(options.bonusCredits || '')}`;
      }
      if (
        key.startsWith('module.billing.catalog.topups.') &&
        key.endsWith('.title') &&
        options?.credits
      ) {
        return `${options.credits}-credit pack`;
      }
      if (
        (key === 'module.billing.package.validityShort.monthly' ||
          key === 'module.billing.package.validityShort.yearly') &&
        options?.count
      ) {
        return `${key}:${options.count}`;
      }
      if (
        key === 'module.billing.catalog.labels.providerWithChannel' &&
        typeof options?.provider === 'string' &&
        typeof options?.channel === 'string'
      ) {
        return `${options.provider} / ${options.channel}`;
      }
      if (
        key === 'module.billing.checkout.expiresInValue' &&
        typeof options?.countdown === 'string'
      ) {
        return `${key}:${options.countdown}`;
      }
      return key;
    },
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/lib/browser-timezone', () => ({
  __esModule: true,
  getBrowserTimeZone: () => 'Asia/Shanghai',
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    cancelBillingSubscription: jest.fn(),
    checkoutBillingOrder: jest.fn(),
    checkoutBillingSubscription: jest.fn(),
    checkoutBillingTopup: jest.fn(),
    getBillingCatalog: jest.fn(),
    resumeBillingSubscription: jest.fn(),
    syncBillingOrder: jest.fn(),
  },
}));

jest.mock(
  'swr',
  () => ({
    __esModule: true,
    default: jest.fn(),
    mutate: jest.fn(),
  }),
  { virtual: true },
);

jest.mock('@/hooks/useBillingData', () => ({
  __esModule: true,
  useBillingOverview: jest.fn(),
  BILLING_WALLET_BUCKETS_SWR_KEY: 'billing-wallet-buckets',
}));

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  toast: jest.fn(),
}));

jest.mock('@/lib/stripe-storage', () => ({
  __esModule: true,
  rememberStripeCheckoutSession: jest.fn(),
}));

jest.mock('@/lib/billing', () => {
  const actual = jest.requireActual('@/lib/billing');
  return {
    ...actual,
    openBillingCheckoutUrl: jest.fn(),
  };
});

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/components/ui/Dialog', () => ({
  __esModule: true,
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

const mockCheckoutBillingOrder = api.checkoutBillingOrder as jest.Mock;
const mockCheckoutBillingSubscription =
  api.checkoutBillingSubscription as jest.Mock;
const mockCheckoutBillingTopup = api.checkoutBillingTopup as jest.Mock;
const mockGetBillingCatalog = api.getBillingCatalog as jest.Mock;
const mockResumeBillingSubscription =
  api.resumeBillingSubscription as jest.Mock;
const mockSyncBillingOrder = api.syncBillingOrder as jest.Mock;
const mockRememberStripeCheckoutSession =
  rememberStripeCheckoutSession as jest.Mock;
const mockOpenBillingCheckoutUrl = openBillingCheckoutUrl as jest.Mock;
const mockToast = toast as jest.Mock;
const mockUseBillingOverview = useBillingOverview as jest.Mock;
const mockUseSWR = useSWR as jest.Mock;
const mockMutateSWRCache = mutateSWRCache as jest.Mock;
const mockMutateOverview = jest.fn();
const DEFAULT_TRIAL_OFFER = {
  enabled: true,
  status: 'ineligible' as const,
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
};

const CATALOG_RESPONSE = {
  plans: [
    {
      product_bid: 'bill-product-plan-monthly',
      product_code: 'creator-plan-monthly',
      product_type: 'plan' as const,
      display_name: 'module.billing.catalog.plans.creatorMonthly.title',
      description: 'module.billing.catalog.plans.creatorMonthly.description',
      billing_interval: 'month' as const,
      billing_interval_count: 1,
      currency: 'CNY',
      price_amount: 990,
      credit_amount: 5,
      plan_tier: 10,
      auto_renew_enabled: true,
      highlights: [
        'module.billing.package.features.monthly.publish',
        'module.billing.package.features.monthly.preview',
      ],
    },
    {
      product_bid: 'bill-product-plan-monthly-pro',
      product_code: 'creator-plan-monthly-pro',
      product_type: 'plan' as const,
      display_name: 'module.billing.catalog.plans.creatorMonthlyPro.title',
      description: 'module.billing.catalog.plans.creatorMonthlyPro.description',
      billing_interval: 'month' as const,
      billing_interval_count: 1,
      currency: 'CNY',
      price_amount: 19900,
      credit_amount: 100,
      plan_tier: 20,
      auto_renew_enabled: true,
      highlights: [
        'module.billing.package.features.monthly.publish',
        'module.billing.package.features.monthly.preview',
      ],
      status_badge_key: 'module.billing.catalog.badges.recommended',
    },
    {
      product_bid: 'bill-product-plan-yearly-lite',
      product_code: 'creator-plan-yearly-lite',
      product_type: 'plan' as const,
      display_name: 'module.billing.catalog.plans.creatorYearlyLite.title',
      description: 'module.billing.catalog.plans.creatorYearlyLite.description',
      billing_interval: 'year' as const,
      billing_interval_count: 1,
      currency: 'CNY',
      price_amount: 800000,
      credit_amount: 5000,
      plan_tier: 30,
      auto_renew_enabled: true,
      highlights: [
        'module.billing.package.features.yearly.lite.ops',
        'module.billing.package.features.yearly.lite.publish',
      ],
    },
    {
      product_bid: 'bill-product-plan-yearly',
      product_code: 'creator-plan-yearly',
      product_type: 'plan' as const,
      display_name: 'module.billing.catalog.plans.creatorYearly.title',
      description: 'module.billing.catalog.plans.creatorYearly.description',
      billing_interval: 'year' as const,
      billing_interval_count: 1,
      currency: 'CNY',
      price_amount: 1500000,
      credit_amount: 10000,
      plan_tier: 40,
      auto_renew_enabled: true,
      highlights: [
        'module.billing.package.features.yearly.pro.branding',
        'module.billing.package.features.yearly.pro.domain',
        'module.billing.package.features.yearly.pro.priority',
        'module.billing.package.features.yearly.pro.analytics',
        'module.billing.package.features.yearly.pro.support',
      ],
    },
    {
      product_bid: 'bill-product-plan-yearly-premium',
      product_code: 'creator-plan-yearly-premium',
      product_type: 'plan' as const,
      display_name: 'module.billing.catalog.plans.creatorYearlyPremium.title',
      description:
        'module.billing.catalog.plans.creatorYearlyPremium.description',
      billing_interval: 'year' as const,
      billing_interval_count: 1,
      currency: 'CNY',
      price_amount: 3000000,
      credit_amount: 22000,
      plan_tier: 50,
      auto_renew_enabled: true,
      highlights: [
        'module.billing.package.features.yearly.premium.branding',
        'module.billing.package.features.yearly.premium.domain',
        'module.billing.package.features.yearly.premium.priority',
        'module.billing.package.features.yearly.premium.analytics',
        'module.billing.package.features.yearly.premium.support',
      ],
      status_badge_key: 'module.billing.catalog.badges.bestValue',
    },
  ],
  topups: [
    {
      product_bid: 'bill-product-topup-small',
      product_code: 'creator-topup-small',
      product_type: 'topup' as const,
      display_name: 'module.billing.catalog.topups.default.title',
      description: 'module.billing.catalog.topups.default.description',
      currency: 'CNY',
      price_amount: 5000,
      credit_amount: 24,
      campaign: {
        campaign_bid: 'campaign-topup-small',
        benefit_type: 'discount' as const,
        discount_type: 'percent' as const,
        discount_amount: 400,
        discount_percent: 8,
        campaign_price_amount: 4600,
      },
    },
    {
      product_bid: 'bill-product-topup-medium',
      product_code: 'creator-topup-medium',
      product_type: 'topup' as const,
      display_name: 'module.billing.catalog.topups.default.title',
      description: 'module.billing.catalog.topups.default.description',
      currency: 'CNY',
      price_amount: 9900,
      credit_amount: 50,
    },
    {
      product_bid: 'bill-product-topup-large',
      product_code: 'creator-topup-large',
      product_type: 'topup' as const,
      display_name: 'module.billing.catalog.topups.default.title',
      description: 'module.billing.catalog.topups.default.description',
      currency: 'CNY',
      price_amount: 19900,
      credit_amount: 120,
    },
    {
      product_bid: 'bill-product-topup-xlarge',
      product_code: 'creator-topup-xlarge',
      product_type: 'topup' as const,
      display_name: 'module.billing.catalog.topups.default.title',
      description: 'module.billing.catalog.topups.default.description',
      currency: 'CNY',
      price_amount: 49900,
      credit_amount: 320,
      status_badge_key: 'module.billing.catalog.badges.bestValue',
    },
  ],
};

const DAILY_PLAN = {
  product_bid: 'bill-product-plan-daily',
  product_code: 'creator-plan-daily',
  product_type: 'plan' as const,
  display_name: 'module.billing.catalog.plans.creatorMonthly.title',
  description: 'module.billing.catalog.plans.creatorMonthly.description',
  billing_interval: 'day' as const,
  billing_interval_count: 7,
  currency: 'CNY',
  price_amount: 390,
  credit_amount: 21,
  plan_tier: 5,
  auto_renew_enabled: true,
  highlights: [
    'module.billing.package.features.daily.publish',
    'module.billing.package.features.daily.preview',
    'module.billing.package.features.daily.support',
  ],
};

function renderOverviewTab(
  props?: React.ComponentProps<typeof BillingOverviewTab>,
) {
  return render(<BillingOverviewTab {...props} />);
}

async function acceptBillingAgreement(
  user: ReturnType<typeof userEvent.setup>,
) {
  await act(async () => {
    await user.click(screen.getByRole('checkbox'));
  });
}

describe('BillingOverviewTab', () => {
  beforeEach(() => {
    mockEnvState.paymentChannels = ['stripe', 'pingxx'];
    mockEnvState.runtimeConfigLoaded = true;
    mockEnvState.stripeEnabled = 'true';

    mockCheckoutBillingOrder.mockReset();
    mockCheckoutBillingSubscription.mockReset();
    mockCheckoutBillingTopup.mockReset();
    mockGetBillingCatalog.mockReset();
    mockResumeBillingSubscription.mockReset();
    mockSyncBillingOrder.mockReset();
    mockRememberStripeCheckoutSession.mockReset();
    mockOpenBillingCheckoutUrl.mockReset();
    mockToast.mockReset();
    mockUseBillingOverview.mockReset();
    mockUseSWR.mockReset();
    mockMutateSWRCache.mockReset();
    mockMutateOverview.mockReset();

    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    mockGetBillingCatalog.mockResolvedValue(CATALOG_RESPONSE);
    mockUseSWR.mockReturnValue({
      data: CATALOG_RESPONSE,
      error: undefined,
      isLoading: false,
    });
    mockSyncBillingOrder.mockResolvedValue({
      bill_order_bid: 'order-plan-pingxx-1',
      status: 'pending',
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('renders monthly and yearly plans together in a single combined tab', async () => {
    const user = userEvent.setup();
    renderOverviewTab();

    expect(mockUseSWR).toHaveBeenCalledWith(
      ['billing-catalog'],
      expect.any(Function),
      {
        revalidateOnFocus: false,
      },
    );

    expect(
      screen.queryByRole('heading', {
        name: 'module.billing.package.title',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('tab', {
        name: 'module.billing.package.intervalTabs.plans',
      }),
    ).toHaveAttribute('data-state', 'active');
    expect(
      screen.queryByRole('tab', {
        name: 'module.billing.package.intervalTabs.daily',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('tab', {
        name: 'module.billing.package.intervalTabs.monthly',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('tab', {
        name: 'module.billing.package.intervalTabs.yearly',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('billing-plan-card-free'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly'),
    ).toHaveAttribute('data-featured', 'true');
    expect(
      screen.getAllByText('module.billing.package.validityShort.monthly:1')
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText('module.billing.package.validityShort.yearly:1')
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly-pro'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-yearly-lite'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-yearly'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-yearly-premium'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(
        'billing-plan-card-bill-product-plan-yearly-premium-price-summary',
      ),
    ).toHaveClass('columnPriceSummary');

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.package.intervalTabs.topup',
        }),
      );
    });

    expect(
      screen.getByTestId('billing-topup-card-bill-product-topup-small'),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByTestId('billing-topup-card-bill-product-topup-small'),
      ).getByText('¥50'),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByTestId('billing-topup-card-bill-product-topup-small'),
      ).getByText('¥46'),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByTestId('billing-topup-card-bill-product-topup-small'),
      ).getByText('module.billing.package.campaign.discountBadge'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('billing-topup-note')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.package.topup.noteInstant'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.package.topup.noteFrozen'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('billing-topup-card-bill-product-topup-medium'),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByTestId('billing-topup-card-bill-product-topup-medium'),
      ).queryByText('module.billing.package.campaign.discountBadge'),
    ).not.toBeInTheDocument();
    expect(
      within(
        screen.getByTestId('billing-topup-card-bill-product-topup-medium'),
      ).queryByText('¥99'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('billing-topup-card-bill-product-topup-large'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('billing-topup-card-bill-product-topup-xlarge'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('billing-topup-grid')).toHaveClass(
      '[grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]',
    );
    expect(
      screen.queryByTestId('billing-plan-card-free'),
    ).not.toBeInTheDocument();
  });

  test('renders campaign bonus credits for plans and topups', async () => {
    const user = userEvent.setup();
    const catalogWithBonus = {
      ...CATALOG_RESPONSE,
      plans: CATALOG_RESPONSE.plans.map(plan =>
        plan.product_bid === 'bill-product-plan-monthly'
          ? {
              ...plan,
              campaign: {
                campaign_bid: 'campaign-plan-bonus',
                benefit_type: 'bonus' as const,
                discount_amount: 0,
                discount_percent: 0,
                campaign_price_amount: 0,
                bonus_credit_amount: 2,
              },
            }
          : plan,
      ),
      topups: CATALOG_RESPONSE.topups.map(product =>
        product.product_bid === 'bill-product-topup-medium'
          ? {
              ...product,
              campaign: {
                campaign_bid: 'campaign-topup-bonus',
                benefit_type: 'bonus' as const,
                discount_amount: 0,
                discount_percent: 0,
                campaign_price_amount: 0,
                bonus_credit_amount: 10,
              },
            }
          : product,
      ),
    };
    mockGetBillingCatalog.mockResolvedValue(catalogWithBonus);
    mockUseSWR.mockReturnValue({
      data: catalogWithBonus,
      error: undefined,
      isLoading: false,
    });

    renderOverviewTab();

    expect(
      within(
        screen.getByTestId(
          'billing-plan-card-bill-product-plan-monthly-price-summary',
        ),
      ).getByText('module.billing.package.campaign.bonusBadge:2:'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.package.intervalTabs.topup',
        }),
      );
    });

    expect(
      within(
        screen.getByTestId('billing-topup-card-bill-product-topup-medium'),
      ).getByText('module.billing.package.campaign.bonusBadge:10:'),
    ).toBeInTheDocument();
  });

  test('hides daily plans even when the catalog returns them', () => {
    const dailyCatalog = {
      ...CATALOG_RESPONSE,
      plans: [DAILY_PLAN, ...CATALOG_RESPONSE.plans],
    };

    mockGetBillingCatalog.mockResolvedValue(dailyCatalog);
    mockUseSWR.mockReturnValue({
      data: dailyCatalog,
      error: undefined,
      isLoading: false,
    });

    renderOverviewTab();

    expect(
      screen.queryByRole('tab', {
        name: 'module.billing.package.intervalTabs.daily',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('billing-plan-card-bill-product-plan-daily'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('tab', {
        name: 'module.billing.package.intervalTabs.plans',
      }),
    ).toHaveAttribute('data-state', 'active');
  });

  test('keeps the non-member card hidden when the trial offer is disabled', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: null,
        billing_alerts: [],
        trial_offer: {
          ...DEFAULT_TRIAL_OFFER,
          enabled: false,
          status: 'disabled',
        },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    expect(
      screen.queryByTestId('billing-plan-card-free'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly'),
    ).toBeInTheDocument();
  });

  test('does not mark a hidden non-member card when there is no active subscription', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: null,
        billing_alerts: [],
        trial_offer: {
          ...DEFAULT_TRIAL_OFFER,
          enabled: false,
          status: 'disabled',
        },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    expect(
      screen.queryByTestId('billing-plan-card-free'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly'),
    ).toHaveAttribute('data-featured', 'false');
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly-action'),
    ).toHaveTextContent('module.billing.package.actions.subscribeNow');
    expect(
      screen.getAllByText('module.billing.package.validityShort.monthly:1')
        .length,
    ).toBeGreaterThan(0);
  });

  test('does not render the hidden non-member action tooltip target', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: null,
        billing_alerts: [],
        trial_offer: {
          ...DEFAULT_TRIAL_OFFER,
          enabled: false,
          status: 'disabled',
        },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    expect(
      screen.queryByTestId('billing-plan-card-free-action-trigger'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.billing.package.actions.nonMemberTooltip'),
    ).not.toBeInTheDocument();
  });

  test('blocks lower-tier preorder when the current subscription is Stripe-managed', async () => {
    const user = userEvent.setup();

    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly-pro',
          product_code: 'creator-plan-monthly-pro',
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly-action'),
    ).toBeDisabled();
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly-action'),
    ).toHaveTextContent('module.billing.package.actions.preorderDowngrade');

    await act(async () => {
      await user.hover(
        screen.getByTestId(
          'billing-plan-card-bill-product-plan-monthly-action-trigger',
        ),
      );
    });

    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'module.billing.package.actions.preorderProviderUnsupportedTooltip',
    );
  });

  test('lets trial users upgrade with an available checkout provider instead of manual', async () => {
    const user = userEvent.setup();
    mockEnvState.paymentChannels = ['wechatpay'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 100,
          reserved_credits: 0,
          lifetime_granted_credits: 100,
          lifetime_consumed_credits: 0,
        },
        subscription: {
          subscription_bid: 'sub-trial-1',
          product_bid: 'bill-product-plan-trial',
          product_code: 'creator-plan-trial',
          status: 'active',
          billing_provider: 'manual',
          current_period_start_at: '2026-05-29T05:44:32Z',
          current_period_end_at: '2026-06-13T05:44:32Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-trial-upgrade-1',
      provider: 'wechatpay',
      payment_mode: 'subscription',
      status: 'pending',
      checkout_type: 'subscription_upgrade',
      effective_mode: 'immediate',
      payable_amount: 990,
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://wechatpay.test/trial-upgrade-qr',
        },
      },
    });

    renderOverviewTab();

    const monthlyAction = screen.getByTestId(
      'billing-plan-card-bill-product-plan-monthly-action',
    );
    expect(monthlyAction).toBeEnabled();
    expect(monthlyAction).toHaveTextContent(
      'module.billing.package.actions.upgradeNow',
    );

    await act(async () => {
      await user.click(monthlyAction);
    });
    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'upgrade_immediate',
          channel: 'wx_pub_qr',
          payment_provider: 'wechatpay',
          product_bid: 'bill-product-plan-monthly',
        }),
      );
    });
    expect(
      await screen.findByTestId('billing-pingxx-qr-code'),
    ).toBeInTheDocument();
  });

  test('lets manual paid subscribers upgrade with an available checkout provider', async () => {
    const user = userEvent.setup();
    mockEnvState.paymentChannels = ['wechatpay'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-manual-paid-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'manual',
          current_period_start_at: '2026-05-01T00:00:00Z',
          current_period_end_at: '2026-05-30T15:59:59Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-manual-paid-upgrade-1',
      provider: 'wechatpay',
      payment_mode: 'subscription',
      status: 'pending',
      checkout_type: 'subscription_upgrade',
      effective_mode: 'immediate',
      payable_amount: 18910,
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://wechatpay.test/manual-paid-upgrade-qr',
        },
      },
    });

    renderOverviewTab();

    const proAction = screen.getByTestId(
      'billing-plan-card-bill-product-plan-monthly-pro-action',
    );
    expect(proAction).toBeEnabled();
    expect(proAction).toHaveTextContent(
      'module.billing.package.actions.upgradeNow',
    );

    await act(async () => {
      await user.click(proAction);
    });
    expect(
      screen.getByText('module.billing.checkout.upgradeDescription'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        'module.billing.checkout.upgradeWithPreorderDescription',
      ),
    ).not.toBeInTheDocument();
    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'upgrade_immediate',
          channel: 'wx_pub_qr',
          payment_provider: 'wechatpay',
          product_bid: 'bill-product-plan-monthly-pro',
        }),
      );
    });
    expect(
      await screen.findByTestId('billing-pingxx-qr-code'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.checkout.upgradeDescription'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.billing.checkout.prepaidOffsetLabel'),
    ).not.toBeInTheDocument();
  });

  test('passes preorder action for self-managed same-tier renewal', async () => {
    const user = userEvent.setup();
    mockEnvState.paymentChannels = ['pingxx'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'pingxx',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-preorder-1',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      checkout_type: 'subscription_preorder',
      effective_mode: 'cycle_end',
      payable_amount: 990,
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/preorder-wechat-qr',
        },
      },
    });

    renderOverviewTab();

    const currentPlanAction = screen.getByTestId(
      'billing-plan-card-bill-product-plan-monthly-action',
    );
    expect(currentPlanAction).toBeEnabled();
    expect(currentPlanAction).toHaveTextContent(
      'module.billing.package.actions.preorderRenewal',
    );

    await act(async () => {
      await user.click(currentPlanAction);
    });
    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'preorder',
          channel: 'wx_pub_qr',
          payment_provider: 'pingxx',
          product_bid: 'bill-product-plan-monthly',
        }),
      );
    });
  });

  test('disables same-tier renewal when the current period already includes a prepaid cycle', () => {
    mockEnvState.paymentChannels = ['pingxx'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'pingxx',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2099-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    const currentPlanAction = screen.getByTestId(
      'billing-plan-card-bill-product-plan-monthly-action',
    );
    expect(currentPlanAction).toBeDisabled();
    expect(currentPlanAction).toHaveTextContent(
      'module.billing.package.actions.preorderScheduled',
    );
  });

  test('does not mark the current plan preordered for timezone-shifted single-cycle ends', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-05-29T00:00:00Z'));
    mockEnvState.paymentChannels = ['wechatpay'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 105,
          reserved_credits: 0,
          lifetime_granted_credits: 105,
          lifetime_consumed_credits: 0,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'wechatpay',
          current_period_start_at: '2026-05-29T07:13:24+08:00',
          current_period_end_at: '2026-06-28T07:59:59+08:00',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    const currentPlanAction = screen.getByTestId(
      'billing-plan-card-bill-product-plan-monthly-action',
    );
    expect(currentPlanAction).toBeEnabled();
    expect(currentPlanAction).toHaveTextContent(
      'module.billing.package.actions.preorderRenewal',
    );
    expect(
      screen.queryByTestId('billing-pending-preorder-banner'),
    ).not.toBeInTheDocument();
  });

  test('shows pending preorder and only lets higher-tier checkout use offset', async () => {
    const user = userEvent.setup();
    mockEnvState.paymentChannels = ['pingxx'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'pingxx',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: 'bill-product-plan-monthly-pro',
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-upgrade-1',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      checkout_type: 'subscription_upgrade',
      effective_mode: 'immediate',
      prepaid_offset_amount: 40000,
      payable_amount: 760000,
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/upgrade-wechat-qr',
        },
      },
    });

    renderOverviewTab();

    expect(
      screen.getByTestId('billing-pending-preorder-banner'),
    ).toHaveTextContent('module.billing.package.preorder.pending');
    expect(
      screen.getByTestId(
        'billing-plan-card-bill-product-plan-monthly-pro-action',
      ),
    ).toHaveTextContent('module.billing.package.actions.preorderScheduled');
    expect(
      screen.getByTestId(
        'billing-plan-card-bill-product-plan-monthly-pro-action',
      ),
    ).toBeDisabled();

    await act(async () => {
      await user.click(
        screen.getByTestId(
          'billing-plan-card-bill-product-plan-yearly-lite-action',
        ),
      );
    });
    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'upgrade_immediate',
          channel: 'wx_pub_qr',
          payment_provider: 'pingxx',
          product_bid: 'bill-product-plan-yearly-lite',
        }),
      );
    });
    expect(
      screen.getByText(
        'module.billing.checkout.upgradeWithPreorderDescription',
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId('billing-pingxx-qr-code'),
    ).toBeInTheDocument();
    expect(screen.getByText(/7,600/)).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.checkout.prepaidOffsetLabel'),
    ).toBeInTheDocument();
    expect(screen.getByText(/400/)).toBeInTheDocument();
  });

  test('disables pending-preorder upgrades when the current provider is unavailable', async () => {
    mockEnvState.paymentChannels = ['stripe'];
    mockEnvState.stripeEnabled = 'true';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'pingxx',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: 'bill-product-plan-monthly-pro',
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    expect(
      screen.getByTestId(
        'billing-plan-card-bill-product-plan-yearly-lite-action',
      ),
    ).toBeDisabled();
  });

  test('disables active-subscription upgrades when the current provider is unavailable', async () => {
    mockEnvState.paymentChannels = ['stripe'];
    mockEnvState.stripeEnabled = 'true';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'pingxx',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    expect(
      screen.getByTestId(
        'billing-plan-card-bill-product-plan-monthly-pro-action',
      ),
    ).toBeDisabled();
  });

  test('shows same-plan pending preorder and keeps higher-tier upgrade available', async () => {
    const user = userEvent.setup();
    mockEnvState.paymentChannels = ['pingxx'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 5,
          lifetime_granted_credits: 505,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'pingxx',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: 'bill-product-plan-monthly',
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-upgrade-same-plan-pending',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      checkout_type: 'subscription_upgrade',
      effective_mode: 'immediate',
      preorder_order_bid: 'order-preorder-same-plan',
      prepaid_offset_amount: 990,
      payable_amount: 18910,
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/same-plan-upgrade-wechat-qr',
        },
      },
    });

    renderOverviewTab();

    expect(
      screen.getByTestId('billing-pending-preorder-banner'),
    ).toHaveTextContent('module.billing.package.preorder.pending');
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly-action'),
    ).toHaveTextContent('module.billing.package.actions.preorderScheduled');
    expect(
      screen.getByTestId('billing-plan-card-bill-product-plan-monthly-action'),
    ).toBeDisabled();
    expect(
      screen.getByTestId(
        'billing-plan-card-bill-product-plan-monthly-pro-action',
      ),
    ).toHaveTextContent('module.billing.package.actions.upgradeNow');

    await act(async () => {
      await user.click(
        screen.getByTestId(
          'billing-plan-card-bill-product-plan-monthly-pro-action',
        ),
      );
    });
    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'upgrade_immediate',
          channel: 'wx_pub_qr',
          payment_provider: 'pingxx',
          product_bid: 'bill-product-plan-monthly-pro',
        }),
      );
    });
    expect(
      await screen.findByTestId('billing-pingxx-qr-code'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.checkout.prepaidOffsetLabel'),
    ).toBeInTheDocument();
  });

  test('renders the redesigned low balance alert card', () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 0,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 500,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [
          {
            code: 'low_balance',
            severity: 'warning',
            message_key: 'module.billing.alerts.lowBalance',
            action_type: 'checkout_topup',
          },
        ],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    renderOverviewTab();

    expect(screen.getByTestId('billing-alert-low-balance')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.alerts.lowBalanceTitle'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.alerts.lowBalanceDescription'),
    ).toBeInTheDocument();
    expect(screen.queryByText('low_balance')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.billing.alerts.actions.checkoutTopup',
      }),
    ).not.toBeInTheDocument();
  });

  test('resumes a cancel-scheduled subscription from the billing alert', async () => {
    const user = userEvent.setup();
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'cancel_scheduled',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: true,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [
          {
            code: 'cancel_scheduled',
            severity: 'info',
            message_key: 'module.billing.alerts.cancelScheduled',
            action_type: 'resume_subscription',
          },
        ],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockResumeBillingSubscription.mockResolvedValue({
      subscription_bid: 'sub-1',
      product_bid: 'bill-product-plan-monthly',
      product_code: 'creator-plan-monthly',
      status: 'active',
      billing_provider: 'stripe',
      current_period_start_at: '2026-04-01T00:00:00Z',
      current_period_end_at: '2026-05-01T00:00:00Z',
      grace_period_end_at: null,
      cancel_at_period_end: false,
      next_product_bid: null,
      last_renewed_at: null,
      last_failed_at: null,
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.alerts.actions.resumeSubscription',
        }),
      );
    });

    await waitFor(() => {
      expect(mockResumeBillingSubscription).toHaveBeenCalledWith({
        subscription_bid: 'sub-1',
      });
    });

    expect(mockMutateOverview).toHaveBeenCalled();
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'module.billing.overview.feedback.resumeSuccess',
      }),
    );
  });

  test('opens a Stripe subscription checkout from the yearly showcase card', async () => {
    const user = userEvent.setup();
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 12,
          reserved_credits: 0,
          lifetime_granted_credits: 120,
          lifetime_consumed_credits: 108,
        },
        subscription: null,
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-plan-1',
      provider: 'stripe',
      payment_mode: 'subscription',
      status: 'pending',
      redirect_url: 'https://stripe.test/checkout',
      checkout_session_id: 'cs_test_123',
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        screen.getByTestId('billing-plan-card-bill-product-plan-yearly-action'),
      );
    });

    expect(
      screen.getByText('module.billing.checkout.title'),
    ).toBeInTheDocument();

    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          payment_provider: 'stripe',
          product_bid: 'bill-product-plan-yearly',
        }),
      );
    });

    expect(mockRememberStripeCheckoutSession).toHaveBeenCalledWith(
      'cs_test_123',
      'order-plan-1',
    );
    expect(mockOpenBillingCheckoutUrl).toHaveBeenCalledWith(
      'https://stripe.test/checkout',
    );
  });

  test('uses the returned provider when a same-package checkout reuses an existing QR order', async () => {
    const user = userEvent.setup();
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 12,
          reserved_credits: 0,
          lifetime_granted_credits: 120,
          lifetime_consumed_credits: 108,
        },
        subscription: null,
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-plan-reused-1',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      expires_in_seconds: 1800,
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/reused-wechat-qr',
        },
      },
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        screen.getByTestId('billing-plan-card-bill-product-plan-yearly-action'),
      );
    });
    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          payment_provider: 'stripe',
          product_bid: 'bill-product-plan-yearly',
        }),
      );
    });

    expect(screen.getByTestId('billing-pingxx-qr-code')).toBeInTheDocument();
    expect(mockOpenBillingCheckoutUrl).not.toHaveBeenCalled();
    expect(mockRememberStripeCheckoutSession).not.toHaveBeenCalled();
    expect(
      screen.getByTestId('billing-pingxx-expiration-countdown'),
    ).toHaveTextContent('module.billing.checkout.expiresInValue:30:00');
  });

  test('shows an in-app Pingxx subscription QR and allows switching channels', async () => {
    const user = userEvent.setup();
    mockEnvState.paymentChannels = ['pingxx'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 12,
          reserved_credits: 0,
          lifetime_granted_credits: 120,
          lifetime_consumed_credits: 108,
        },
        subscription: null,
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-plan-pingxx-1',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      expires_in_seconds: 1800,
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/plan-wechat-qr',
        },
      },
    });
    mockCheckoutBillingOrder.mockResolvedValue({
      bill_order_bid: 'order-plan-pingxx-1',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      payment_payload: {
        credential: {
          alipay_qr: 'https://pingxx.test/plan-alipay-qr',
        },
      },
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        screen.getByTestId('billing-plan-card-bill-product-plan-yearly-action'),
      );
    });

    expect(
      screen.getByText(
        (_content, element) =>
          element?.textContent ===
          'module.billing.catalog.labels.providerPingxx / module.pay.wechatPay',
      ),
    ).toBeInTheDocument();

    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          channel: 'wx_pub_qr',
          payment_provider: 'pingxx',
          product_bid: 'bill-product-plan-yearly',
        }),
      );
    });

    expect(screen.getByTestId('billing-pingxx-qr-code')).toBeInTheDocument();
    expect(
      screen.getByTestId('billing-pingxx-expiration-countdown'),
    ).toHaveTextContent('module.billing.checkout.expiresInValue:30:00');
    expect(screen.getByRole('checkbox')).toBeChecked();
    expect(
      screen.getByRole('button', {
        name: 'module.pay.clickRefresh',
      }),
    ).toBeEnabled();

    await act(async () => {
      await user.click(screen.getByTestId('billing-pingxx-channel-alipay_qr'));
    });

    await waitFor(() => {
      expect(mockCheckoutBillingOrder).toHaveBeenCalledWith({
        bill_order_bid: 'order-plan-pingxx-1',
        channel: 'alipay_qr',
      });
    });
  });

  test('shows an in-app Pingxx top-up QR when Stripe is unavailable', async () => {
    const user = userEvent.setup();
    mockEnvState.paymentChannels = ['pingxx'];
    mockEnvState.stripeEnabled = 'false';
    mockCheckoutBillingTopup.mockResolvedValue({
      bill_order_bid: 'order-topup-1',
      provider: 'pingxx',
      payment_mode: 'one_time',
      status: 'pending',
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/wechat-qr',
        },
      },
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.package.intervalTabs.topup',
        }),
      );
    });

    await act(async () => {
      await user.click(
        screen.getByTestId(
          'billing-topup-card-bill-product-topup-small-action',
        ),
      );
    });

    expect(screen.getByText('24-credit pack')).toBeInTheDocument();

    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingTopup).toHaveBeenCalledWith(
        expect.objectContaining({
          channel: 'wx_pub_qr',
          payment_provider: 'pingxx',
          product_bid: 'bill-product-topup-small',
        }),
      );
    });

    expect(screen.getByTestId('billing-pingxx-qr-code')).toBeInTheDocument();
    expect(screen.getByText('24-credit pack')).toBeInTheDocument();
  });

  test('polls pending Pingxx checkout and closes the QR dialog after payment', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({
      advanceTimers: jest.advanceTimersByTime,
    });
    mockEnvState.paymentChannels = ['pingxx'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'pingxx',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-plan-pingxx-1',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/plan-wechat-qr',
        },
      },
    });
    mockSyncBillingOrder.mockResolvedValueOnce({
      bill_order_bid: 'order-plan-pingxx-1',
      status: 'paid',
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        screen.getByTestId('billing-plan-card-bill-product-plan-yearly-action'),
      );
    });

    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    expect(screen.getByTestId('billing-pingxx-qr-code')).toBeInTheDocument();

    await act(async () => {
      jest.advanceTimersByTime(1000);
    });

    await waitFor(() => {
      expect(mockSyncBillingOrder).toHaveBeenCalledWith({
        bill_order_bid: 'order-plan-pingxx-1',
      });
    });
    await waitFor(() => {
      expect(mockMutateOverview).toHaveBeenCalled();
      expect(mockMutateSWRCache).toHaveBeenCalledWith([
        'billing-wallet-buckets',
      ]);
      expect(
        screen.queryByTestId('billing-pingxx-qr-code'),
      ).not.toBeInTheDocument();
    });
  });

  test('syncs the Pingxx order before refreshing the QR dialog manually', async () => {
    const user = userEvent.setup();
    mockEnvState.paymentChannels = ['pingxx'];
    mockEnvState.stripeEnabled = 'false';
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'pingxx',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
        trial_offer: { ...DEFAULT_TRIAL_OFFER },
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockCheckoutBillingSubscription.mockResolvedValue({
      bill_order_bid: 'order-plan-pingxx-1',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/plan-wechat-qr',
        },
      },
    });
    mockSyncBillingOrder.mockResolvedValueOnce({
      bill_order_bid: 'order-plan-pingxx-1',
      status: 'paid',
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        screen.getByTestId('billing-plan-card-bill-product-plan-yearly-action'),
      );
    });

    await acceptBillingAgreement(user);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.checkout.confirm',
        }),
      );
    });

    expect(screen.getByTestId('billing-pingxx-qr-code')).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.pay.clickRefresh',
        }),
      );
    });

    await waitFor(() => {
      expect(mockSyncBillingOrder).toHaveBeenCalledWith({
        bill_order_bid: 'order-plan-pingxx-1',
      });
      expect(mockCheckoutBillingOrder).not.toHaveBeenCalled();
      expect(mockMutateOverview).toHaveBeenCalled();
      expect(mockMutateSWRCache).toHaveBeenCalledWith([
        'billing-wallet-buckets',
      ]);
      expect(
        screen.queryByTestId('billing-pingxx-qr-code'),
      ).not.toBeInTheDocument();
    });
  });
});

import React from 'react';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { openBillingCheckoutUrl } from '@/lib/billing';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import type {
  BillingPlan,
  BillingSubscription,
  BillingTopupProduct,
} from '@/types/billing';
import {
  GLOBAL_BILLING_PRODUCT_CODES,
  GlobalBillingPricing,
} from './GlobalBillingPricing';

const mockTrackEvent = jest.fn();
const mockToast = jest.fn();
let mockBillingSubscription: BillingSubscription | null = null;

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}));

jest.mock('@/hooks/useBillingData', () => ({
  useBillingOverview: () => ({
    data: {
      subscription: mockBillingSubscription,
    },
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getBillingCatalog: jest.fn(),
    checkoutBillingSubscription: jest.fn(),
    checkoutBillingTopup: jest.fn(),
  },
}));

jest.mock('@/components/ui/Tabs', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const TabsContext = ReactModule.createContext<{
    value: string;
    onValueChange?: (value: string) => void;
  }>({ value: '' });

  return {
    Tabs: ({
      children,
      value,
      onValueChange,
    }: {
      children: React.ReactNode;
      value: string;
      onValueChange?: (value: string) => void;
    }) => (
      <TabsContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </TabsContext.Provider>
    ),
    TabsList: ({ children }: { children: React.ReactNode }) => (
      <div role='tablist'>{children}</div>
    ),
    TabsTrigger: ({
      children,
      value,
    }: {
      children: React.ReactNode;
      value: string;
    }) => {
      const context = ReactModule.useContext(TabsContext);
      return (
        <button
          role='tab'
          aria-selected={context.value === value}
          onClick={() => context.onValueChange?.(value)}
        >
          {children}
        </button>
      );
    },
    TabsContent: ({
      children,
      value,
    }: {
      children: React.ReactNode;
      value: string;
    }) => {
      const context = ReactModule.useContext(TabsContext);
      return context.value === value ? <div>{children}</div> : null;
    },
  };
});

jest.mock('@/lib/billing', () => {
  const actual = jest.requireActual('@/lib/billing');
  return {
    ...actual,
    openBillingCheckoutUrl: jest.fn(),
  };
});

jest.mock('@/lib/stripe-storage', () => ({
  rememberStripeCheckoutSession: jest.fn(),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => {
    const translate = (key: string, options?: Record<string, unknown>) => {
      const labels: Record<string, string> = {
        'module.billing.globalPricing.actions.buyCredits': 'Buy credits',
        'module.billing.globalPricing.actions.choosePlan': 'Choose plan',
        'module.billing.globalPricing.actions.checkoutLoading':
          'Opening checkout...',
        'module.billing.globalPricing.actions.cycleSwitchDisabled':
          'Billing cycle change unavailable',
        'module.billing.globalPricing.actions.viewMonthly': 'View monthly plan',
        'module.billing.globalPricing.approximatePricePrefix': 'Approx.',
        'module.billing.checkout.unsupported':
          'This payment method is not available right now.',
        'module.billing.globalPricing.checkoutNotice':
          'Stripe checkout is available. You will be redirected to Stripe to complete payment.',
        'module.billing.globalPricing.cycles.annual': 'Annual',
        'module.billing.globalPricing.cycles.monthly': 'Monthly',
        'module.billing.globalPricing.creditPacks.activeSubscriptionRequired':
          'An active subscription is required to use Credit Pack credits. Unused credits remain in the account while the subscription is inactive.',
        'module.billing.globalPricing.creditPacks.instantAndPermanent':
          'Credits are added immediately and never expire.',
        'module.billing.globalPricing.footnote.intro':
          'Estimates use the default model.',
        'module.billing.globalPricing.learnerEstimateLabel':
          'Estimated learner sessions',
        'module.billing.globalPricing.monthlyOnly': 'Monthly only',
        'module.billing.globalPricing.mostPopular': 'Most Popular',
        'module.billing.globalPricing.plans.business.name': 'Business',
        'module.billing.globalPricing.plans.business.estimates.annual':
          '500 - 1,500 learner sessions',
        'module.billing.globalPricing.plans.business.estimates.monthly':
          '40 - 120 learner sessions',
        'module.billing.globalPricing.plans.growth.name': 'Growth',
        'module.billing.globalPricing.plans.growth.estimates.annual':
          '250 - 750 learner sessions',
        'module.billing.globalPricing.plans.growth.estimates.monthly':
          '20 - 60 learner sessions',
        'module.billing.globalPricing.plans.scale.name': 'Scale',
        'module.billing.globalPricing.plans.scale.estimates.annual':
          '1,100 - 3,300 learner sessions',
        'module.billing.globalPricing.plans.scale.estimates.monthly':
          '90 - 270 learner sessions',
        'module.billing.globalPricing.plans.studio.name': 'Studio',
        'module.billing.globalPricing.plans.studio.estimates.monthly':
          '5 - 15 learner sessions',
        'module.billing.globalPricing.tabs.creditPacks': 'Credit Packs',
        'module.billing.globalPricing.tabs.plans': 'Plans',
        'module.billing.globalPricing.validity.annual':
          'Valid for 12 months from the day credits are granted. Ends at 23:59 on the expiry day.',
        'module.billing.globalPricing.validity.monthly':
          'Valid for 30 days from the day credits are granted, inclusive. Ends at 23:59 on the expiry day.',
        'module.billing.globalPricing.footnote.validity':
          'Credit validity: annual credits are valid for 12 months from the day they are granted.',
        'module.billing.package.footnote.learnerEstimateMode':
          'Listen mode affects supported sessions.',
        'module.billing.package.footnote.learnerEstimateModel':
          'Model choice affects credit consumption.',
        'module.billing.package.footnote.learnerEstimateScale':
          'Course scale affects credit consumption.',
        'module.billing.package.actions.currentSubscription':
          'Current subscription',
        'module.billing.package.actions.downgradeDisabled':
          'Downgrade unavailable',
        'module.billing.package.actions.monthlySwitchDisabled':
          'Monthly billing unavailable',
        'module.billing.package.actions.upgradeNow': 'Upgrade now',
      };
      if (key === 'module.billing.globalPricing.billedAnnually') {
        return `Billed ${options?.price} every 12 months.`;
      }
      if (key === 'module.billing.globalPricing.annualSavings') {
        return `Save ${options?.amount} per year (${options?.percent}%)`;
      }
      if (key === 'module.billing.globalPricing.creditPacks.packName') {
        return `${options?.credits} credits`;
      }
      if (key === 'module.billing.globalPricing.creditsPerMonth') {
        return `${options?.credits} credits per month`;
      }
      if (key === 'module.billing.globalPricing.creditsPerYear') {
        return `${options?.credits} credits per 12-month billing period`;
      }
      if (key === 'module.billing.globalPricing.learnerEstimateValue') {
        return `${options?.minimum} - ${options?.maximum} learner sessions`;
      }
      return labels[key] || key;
    };

    return {
      t: translate,
      i18n: {
        getFixedT: () => translate,
        language: 'zh-CN',
        resolvedLanguage: 'zh-CN',
      },
    };
  },
}));

const mockGetBillingCatalog = api.getBillingCatalog as jest.Mock;
const mockCheckoutSubscription = api.checkoutBillingSubscription as jest.Mock;
const mockCheckoutTopup = api.checkoutBillingTopup as jest.Mock;
const mockOpenBillingCheckoutUrl = openBillingCheckoutUrl as jest.Mock;
const mockRememberStripeCheckoutSession =
  rememberStripeCheckoutSession as jest.Mock;

function plan(
  productCode: string,
  billingInterval: 'month' | 'year',
  priceAmount: number,
  creditAmount: number,
): BillingPlan {
  return {
    product_bid: `bid-${productCode}`,
    product_code: productCode,
    product_type: 'plan',
    display_name: productCode,
    description: productCode,
    billing_interval: billingInterval,
    billing_interval_count: 1,
    currency: 'USD',
    price_amount: priceAmount,
    credit_amount: creditAmount,
    auto_renew_enabled: true,
  };
}

function creditPack(
  productCode: string,
  priceAmount: number,
  creditAmount: number,
): BillingTopupProduct {
  return {
    product_bid: `bid-${productCode}`,
    product_code: productCode,
    product_type: 'topup',
    display_name: productCode,
    description: productCode,
    currency: 'USD',
    price_amount: priceAmount,
    credit_amount: creditAmount,
  };
}

function buildGlobalCatalog() {
  return {
    plans: [
      plan(GLOBAL_BILLING_PRODUCT_CODES.studioMonthly, 'month', 5900, 1000),
      plan(GLOBAL_BILLING_PRODUCT_CODES.growthMonthly, 'month', 22900, 4000),
      plan(GLOBAL_BILLING_PRODUCT_CODES.growthAnnual, 'year', 219900, 50000),
      plan(GLOBAL_BILLING_PRODUCT_CODES.businessMonthly, 'month', 41900, 8000),
      plan(GLOBAL_BILLING_PRODUCT_CODES.businessAnnual, 'year', 399900, 100000),
      plan(GLOBAL_BILLING_PRODUCT_CODES.scaleMonthly, 'month', 83900, 18000),
      plan(GLOBAL_BILLING_PRODUCT_CODES.scaleAnnual, 'year', 799900, 220000),
    ],
    topups: [
      creditPack(GLOBAL_BILLING_PRODUCT_CODES.credits250, 2900, 250),
      creditPack(GLOBAL_BILLING_PRODUCT_CODES.credits3000, 27900, 3000),
    ],
  };
}

function renderPricing() {
  return render(
    <SWRConfig value={{ provider: () => new Map() }}>
      <GlobalBillingPricing />
    </SWRConfig>,
  );
}

describe('GlobalBillingPricing', () => {
  beforeEach(() => {
    mockGetBillingCatalog.mockReset();
    mockCheckoutSubscription.mockReset();
    mockCheckoutTopup.mockReset();
    mockTrackEvent.mockReset();
    mockToast.mockReset();
    mockOpenBillingCheckoutUrl.mockReset();
    mockRememberStripeCheckoutSession.mockReset();
    mockBillingSubscription = null;
    mockGetBillingCatalog.mockResolvedValue(buildGlobalCatalog());
  });

  test('renders the approved annual plans with domestic learner estimates', async () => {
    renderPricing();

    const studio = await screen.findByTestId('global-plan-studio');
    const growth = screen.getByTestId('global-plan-growth');
    const business = screen.getByTestId('global-plan-business');
    const scale = screen.getByTestId('global-plan-scale');
    const planGrid = screen.getByTestId('global-plan-grid');

    expect(planGrid).toHaveClass(
      'grid-cols-1',
      'gap-4',
      'sm:grid-cols-2',
      'xl:grid-cols-4',
      '2xl:gap-5',
    );
    for (const card of [studio, growth, business, scale]) {
      expect(card).toHaveClass('min-w-0', 'flex-col');
      expect(card).not.toHaveClass('sm:grid-rows-subgrid');
    }
    for (const tier of ['studio', 'growth', 'business', 'scale']) {
      expect(
        screen.getByTestId(`global-plan-${tier}-title`),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(`global-plan-${tier}-price`),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(`global-plan-${tier}-credits`),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(`global-plan-${tier}-action`),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(`global-plan-${tier}-audience`),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(`global-plan-${tier}-estimate`),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(`global-plan-${tier}-benefits`),
      ).toBeInTheDocument();
    }

    expect(within(studio).getByText('Monthly only')).toBeInTheDocument();
    expect(within(studio).getByText('$59')).toBeInTheDocument();
    expect(
      within(studio).getByText('5 - 15 learner sessions'),
    ).toBeInTheDocument();
    expect(within(growth).getByText('$183')).toBeInTheDocument();
    expect(
      within(growth).getByText('50,000 credits per 12-month billing period'),
    ).toBeInTheDocument();
    expect(
      within(growth).getByText('250 - 750 learner sessions'),
    ).toBeInTheDocument();
    expect(
      within(growth).getByText('Save $549 per year (20.0%)'),
    ).toBeInTheDocument();
    expect(within(business).getByText('$333')).toBeInTheDocument();
    expect(within(business).getByText('Most Popular')).toBeInTheDocument();
    expect(
      within(business).getByText('Save $1,029 per year (20.5%)'),
    ).toBeInTheDocument();
    expect(
      within(business).getByText('500 - 1,500 learner sessions'),
    ).toBeInTheDocument();
    expect(business).not.toHaveClass('border-primary');
    expect(business).not.toHaveClass('ring-1');
    expect(within(scale).getByText('$667')).toBeInTheDocument();
    expect(
      within(scale).getByText('220,000 credits per 12-month billing period'),
    ).toBeInTheDocument();
    expect(
      within(scale).getByText('1,100 - 3,300 learner sessions'),
    ).toBeInTheDocument();
    expect(
      within(scale).getByText('Save $2,069 per year (20.6%)'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/extra|bonus/i)).not.toBeInTheDocument();
    expect(
      screen.getByText('Estimates use the default model.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Stripe checkout is available. You will be redirected to Stripe to complete payment.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Listen mode affects supported sessions.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Model choice affects credit consumption.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Course scale affects credit consumption.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Credit validity: annual credits are valid for 12 months from the day they are granted.',
      ),
    ).toBeInTheDocument();
    expect(
      within(growth).queryByText('Credit validity'),
    ).not.toBeInTheDocument();
    expect(
      within(growth).queryByText(/Valid for 12 months/),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.billing.globalPricing.title'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.billing.globalPricing.subtitle'),
    ).not.toBeInTheDocument();
  });

  test('switches to monthly pricing without a Studio first-month offer', async () => {
    const user = userEvent.setup();
    renderPricing();

    await screen.findByTestId('global-plan-studio');
    await act(async () => {
      await user.click(screen.getByRole('tab', { name: 'Monthly' }));
    });

    expect(
      within(screen.getByTestId('global-plan-studio')).getByText('$59'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('global-plan-growth')).getByText('$229'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('global-plan-business')).getByText('$419'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('global-plan-scale')).getByText('$839'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('global-plan-growth')).getByText(
        '20 - 60 learner sessions',
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('global-plan-business')).getByText(
        '40 - 120 learner sessions',
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('global-plan-scale')).getByText(
        '90 - 270 learner sessions',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/first month/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText('module.billing.globalPricing.studioBonus'),
    ).not.toBeInTheDocument();
  });

  test('switches Studio to monthly without tracking a payment click', async () => {
    const user = userEvent.setup();
    renderPricing();

    const studio = await screen.findByTestId('global-plan-studio');
    await act(async () => {
      await user.click(
        within(studio).getByRole('button', { name: 'View monthly plan' }),
      );
    });

    expect(mockTrackEvent).not.toHaveBeenCalled();
    expect(
      within(screen.getByTestId('global-plan-studio')).getByRole('button', {
        name: 'Choose plan',
      }),
    ).toBeInTheDocument();
  });

  test('starts Stripe checkout for an annual plan', async () => {
    const user = userEvent.setup();
    mockCheckoutSubscription.mockResolvedValue({
      bill_order_bid: 'order-business-annual',
      provider: 'stripe',
      payment_mode: 'subscription',
      status: 'pending',
      redirect_url: 'https://checkout.stripe.test/session',
      checkout_session_id: 'cs_test_plan',
    });
    renderPricing();

    const business = await screen.findByTestId('global-plan-business');
    await act(async () => {
      await user.click(
        within(business).getByRole('button', { name: 'Choose plan' }),
      );
    });

    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_click',
      {
        billing_market: 'global',
        product_type: 'plan',
        product_code: GLOBAL_BILLING_PRODUCT_CODES.businessAnnual,
        plan_name: 'Business',
        billing_interval: 'year',
        price_amount: 399900,
        currency: 'USD',
        credit_amount: 100000,
        source_tab: 'plans',
        checkout_status: 'pending',
      },
    );
    expect(mockCheckoutSubscription).toHaveBeenCalledWith({
      payment_provider: 'stripe',
      product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.businessAnnual}`,
    });
    expect(mockRememberStripeCheckoutSession).toHaveBeenCalledWith(
      'cs_test_plan',
      'order-business-annual',
    );
    expect(mockOpenBillingCheckoutUrl).toHaveBeenCalledWith(
      'https://checkout.stripe.test/session',
    );
    expect(mockCheckoutTopup).not.toHaveBeenCalled();
  });

  test('starts Stripe checkout for approved credit packs', async () => {
    const user = userEvent.setup();
    mockCheckoutTopup.mockResolvedValue({
      bill_order_bid: 'order-topup',
      provider: 'stripe',
      payment_mode: 'one_time',
      status: 'pending',
      redirect_url: 'https://checkout.stripe.test/topup',
      checkout_session_id: 'cs_test_topup',
    });
    renderPricing();

    await screen.findByTestId('global-plan-studio');
    await act(async () => {
      await user.click(screen.getByRole('tab', { name: 'Credit Packs' }));
    });

    const smallPack = screen.getByTestId('global-credit-pack-250');
    const largePack = screen.getByTestId('global-credit-pack-3000');
    expect(screen.getByTestId('global-credit-pack-grid')).toHaveClass(
      'grid',
      'md:grid-cols-2',
    );
    expect(within(smallPack).getByText('$29')).toBeInTheDocument();
    expect(within(largePack).getByText('$279')).toBeInTheDocument();
    expect(
      within(largePack).getByRole('button', { name: 'Buy credits' }),
    ).toHaveClass('min-w-32');
    expect(
      screen.getByText('Credits are added immediately and never expire.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'An active subscription is required to use Credit Pack credits. Unused credits remain in the account while the subscription is inactive.',
      ),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        within(largePack).getByRole('button', { name: 'Buy credits' }),
      );
    });

    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_click',
      expect.objectContaining({
        product_type: 'topup',
        product_code: GLOBAL_BILLING_PRODUCT_CODES.credits3000,
        billing_interval: 'one_time',
        price_amount: 27900,
        currency: 'USD',
        credit_amount: 3000,
        source_tab: 'credit_packs',
        checkout_status: 'pending',
      }),
    );
    expect(mockCheckoutTopup).toHaveBeenCalledWith({
      payment_provider: 'stripe',
      product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.credits3000}`,
    });
    expect(mockRememberStripeCheckoutSession).toHaveBeenCalledWith(
      'cs_test_topup',
      'order-topup',
    );
    expect(mockOpenBillingCheckoutUrl).toHaveBeenCalledWith(
      'https://checkout.stripe.test/topup',
    );
  });

  test('uses immediate upgrade and disables unsupported active plan transitions', async () => {
    const user = userEvent.setup();
    mockBillingSubscription = {
      subscription_bid: 'sub-growth-monthly',
      product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.growthMonthly}`,
      product_code: GLOBAL_BILLING_PRODUCT_CODES.growthMonthly,
      status: 'active',
      billing_provider: 'stripe',
      current_period_start_at: null,
      current_period_end_at: null,
      grace_period_end_at: null,
      cancel_at_period_end: false,
      next_product_bid: null,
      last_renewed_at: null,
      last_failed_at: null,
    };
    mockCheckoutSubscription.mockResolvedValue({
      bill_order_bid: 'order-upgrade',
      provider: 'stripe',
      payment_mode: 'subscription',
      status: 'pending',
      redirect_url: 'https://checkout.stripe.test/upgrade',
    });
    renderPricing();

    const growth = await screen.findByTestId('global-plan-growth');
    expect(
      within(growth).getByRole('button', {
        name: 'Billing cycle change unavailable',
      }),
    ).toBeDisabled();

    await act(async () => {
      await user.click(screen.getByRole('tab', { name: 'Monthly' }));
    });

    expect(
      within(screen.getByTestId('global-plan-growth')).getByRole('button', {
        name: 'Current subscription',
      }),
    ).toBeDisabled();
    expect(
      within(screen.getByTestId('global-plan-studio')).getByRole('button', {
        name: 'Downgrade unavailable',
      }),
    ).toBeDisabled();

    await act(async () => {
      await user.click(
        within(screen.getByTestId('global-plan-business')).getByRole('button', {
          name: 'Upgrade now',
        }),
      );
    });

    expect(mockCheckoutSubscription).toHaveBeenCalledWith({
      action: 'upgrade_immediate',
      payment_provider: 'stripe',
      product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.businessMonthly}`,
    });
  });

  test('shows a destructive toast when Stripe checkout is unsupported', async () => {
    const user = userEvent.setup();
    mockCheckoutSubscription.mockResolvedValue({
      bill_order_bid: 'order-unsupported',
      provider: 'stripe',
      payment_mode: 'subscription',
      status: 'unsupported',
    });
    renderPricing();

    const business = await screen.findByTestId('global-plan-business');
    await act(async () => {
      await user.click(
        within(business).getByRole('button', { name: 'Choose plan' }),
      );
    });

    expect(mockToast).toHaveBeenCalledWith({
      title: 'This payment method is not available right now.',
      variant: 'destructive',
    });
    expect(mockOpenBillingCheckoutUrl).not.toHaveBeenCalled();
  });

  test('fails closed when the global catalog has an unexpected price', async () => {
    const catalog = buildGlobalCatalog();
    catalog.plans[0].price_amount = 1;
    mockGetBillingCatalog.mockResolvedValue(catalog);

    renderPricing();

    expect(
      await screen.findByTestId('global-billing-unavailable'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Choose plan')).not.toBeInTheDocument();
  });

  test('fails closed instead of crashing when a catalog currency is missing', async () => {
    const catalog = buildGlobalCatalog();
    (catalog.plans[0] as { currency?: string }).currency = undefined;
    mockGetBillingCatalog.mockResolvedValue(catalog);

    renderPricing();

    expect(
      await screen.findByTestId('global-billing-unavailable'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Choose plan')).not.toBeInTheDocument();
  });
});

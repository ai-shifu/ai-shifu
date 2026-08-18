import React from 'react';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { useBillingOverview } from '@/hooks/useBillingData';
import type { BillingPlan, BillingTopupProduct } from '@/types/billing';
const mockTrackEvent = jest.fn();

const mockOpenBillingCheckoutUrl = jest.fn();
const mockRememberStripeCheckoutSession = jest.fn();
const mockToast = jest.fn();

jest.mock('@/lib/billing', () => {
  const actual = jest.requireActual('@/lib/billing');
  return {
    ...actual,
    openBillingCheckoutUrl: mockOpenBillingCheckoutUrl,
  };
});

jest.mock('@/lib/stripe-storage', () => ({
  rememberStripeCheckoutSession: mockRememberStripeCheckoutSession,
}));

jest.mock('@/hooks/useToast', () => ({
  toast: mockToast,
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/hooks/useBillingData', () => ({
  useBillingOverview: jest.fn(),
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

jest.mock('@/components/ui/Dialog', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const DialogContext = ReactModule.createContext<{
    open: boolean;
    onOpenChange?: (open: boolean) => void;
  }>({ open: false });

  return {
    Dialog: ({
      children,
      open,
      onOpenChange,
    }: {
      children: React.ReactNode;
      open: boolean;
      onOpenChange?: (open: boolean) => void;
    }) => (
      <DialogContext.Provider value={{ open, onOpenChange }}>
        {children}
      </DialogContext.Provider>
    ),
    DialogContent: ({ children }: { children: React.ReactNode }) => {
      const context = ReactModule.useContext(DialogContext);
      return context.open ? <div role='dialog'>{children}</div> : null;
    },
    DialogHeader: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
    DialogTitle: ({ children }: { children: React.ReactNode }) => (
      <h2>{children}</h2>
    ),
    DialogDescription: ({ children }: { children: React.ReactNode }) => (
      <p>{children}</p>
    ),
    DialogFooter: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
    DialogClose: ({ children }: { children: React.ReactElement }) => {
      const context = ReactModule.useContext(DialogContext);
      return ReactModule.cloneElement(children, {
        onClick: () => context.onOpenChange?.(false),
      } as React.HTMLAttributes<HTMLElement>);
    },
  };
});

jest.mock('react-i18next', () => ({
  useTranslation: () => {
    const translate = (key: string, options?: Record<string, unknown>) => {
      const labels: Record<string, string> = {
        'module.billing.globalPricing.actions.buyCredits': 'Buy now',
        'module.billing.globalPricing.actions.choosePlan': 'Subscribe now',
        'module.billing.globalPricing.actions.viewMonthly': 'View monthly plan',
        'module.billing.globalPricing.approximatePricePrefix': 'About',
        'module.billing.globalPricing.comingSoon.close': 'Got it',
        'module.billing.globalPricing.comingSoon.description':
          "We're building the payment experience. Please check back soon.",
        'module.billing.globalPricing.checkoutNotice':
          'Secure checkout is powered by Stripe.',
        'module.billing.globalPricing.comingSoon.title':
          'Payments are coming soon',
        'module.billing.globalPricing.cycles.annual': 'Annual',
        'module.billing.globalPricing.cycles.monthly': 'Monthly',
        'module.billing.globalPricing.creditPacks.activeSubscriptionRequired':
          'An active subscription is required to use Credit Pack credits. Unused credits remain in the account while the subscription is inactive.',
        'module.billing.globalPricing.creditPacks.instantAndPermanent':
          'Credits are added immediately and never expire.',
        'module.billing.globalPricing.footnote.intro':
          'Estimates use DeepSeek.',
        'module.billing.globalPricing.learnerEstimateLabel':
          'Estimated learner sessions',
        'module.billing.globalPricing.monthlyOnly': 'Monthly only',
        'module.billing.globalPricing.mostPopular': 'Most Popular',
        'module.billing.globalPricing.plans.business.name': 'Business',
        'module.billing.globalPricing.plans.business.estimates.annual':
          '5,000 - 15,000 learner sessions',
        'module.billing.globalPricing.plans.business.estimates.monthly':
          '400 - 1,200 learner sessions',
        'module.billing.globalPricing.plans.growth.name': 'Growth',
        'module.billing.globalPricing.plans.growth.estimates.annual':
          '2,500 - 7,500 learner sessions',
        'module.billing.globalPricing.plans.growth.estimates.monthly':
          '200 - 600 learner sessions',
        'module.billing.globalPricing.plans.scale.name': 'Scale',
        'module.billing.globalPricing.plans.scale.estimates.annual':
          '11,000 - 33,000 learner sessions',
        'module.billing.globalPricing.plans.scale.estimates.monthly':
          '900 - 2,700 learner sessions',
        'module.billing.globalPricing.plans.studio.name': 'Studio',
        'module.billing.globalPricing.plans.studio.estimates.monthly':
          '50 - 150 learner sessions',
        'module.billing.globalPricing.tabs.creditPacks': 'Credit Packs',
        'module.billing.globalPricing.tabs.plans': 'Plans',
        'module.billing.package.actions.currentSubscription':
          'Current subscription',
        'module.billing.package.actions.downgradeDisabled':
          'Downgrade unavailable',
        'module.billing.package.actions.monthlySwitchDisabled':
          'Switching to a monthly plan is unavailable',
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
      };
      if (key === 'module.billing.globalPricing.billedAnnually') {
        return `Billed ${options?.price} every 12 months`;
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
        return `${options?.credits} credits/year`;
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

const { GLOBAL_BILLING_PRODUCT_CODES, GlobalBillingPricing } =
  jest.requireActual(
    './GlobalBillingPricing',
  ) as typeof import('./GlobalBillingPricing');

const mockGetBillingCatalog = api.getBillingCatalog as jest.Mock;
const mockCheckoutSubscription = api.checkoutBillingSubscription as jest.Mock;
const mockCheckoutTopup = api.checkoutBillingTopup as jest.Mock;
const mockUseBillingOverview = useBillingOverview as jest.Mock;

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
    mockOpenBillingCheckoutUrl.mockReset();
    mockRememberStripeCheckoutSession.mockReset();
    mockToast.mockReset();
    mockGetBillingCatalog.mockResolvedValue(buildGlobalCatalog());
    mockUseBillingOverview.mockReturnValue({ data: { subscription: null } });
  });

  test('renders the approved annual plans by default with DeepSeek estimates', async () => {
    renderPricing();

    const studio = await screen.findByTestId('global-plan-studio');
    const growth = screen.getByTestId('global-plan-growth');
    const business = screen.getByTestId('global-plan-business');
    const scale = screen.getByTestId('global-plan-scale');

    expect(within(studio).getByText('Monthly only')).toBeInTheDocument();
    expect(within(studio).getByText('$59')).toBeInTheDocument();
    expect(
      within(studio).getByText('50 - 150 learner sessions'),
    ).toBeInTheDocument();
    expect(within(growth).getByText('$183')).toBeInTheDocument();
    expect(within(growth).getByText('50,000 credits/year')).toBeInTheDocument();
    expect(
      within(growth).getByText('2,500 - 7,500 learner sessions'),
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
      within(business).getByText('5,000 - 15,000 learner sessions'),
    ).toBeInTheDocument();
    expect(business).not.toHaveClass('border-primary');
    expect(business).not.toHaveClass('ring-1');
    expect(within(scale).getByText('$667')).toBeInTheDocument();
    expect(within(scale).getByText('220,000 credits/year')).toBeInTheDocument();
    expect(
      within(scale).getByText('11,000 - 33,000 learner sessions'),
    ).toBeInTheDocument();
    expect(
      within(scale).getByText('Save $2,069 per year (20.6%)'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/extra|bonus/i)).not.toBeInTheDocument();
    expect(screen.getByText('Estimates use DeepSeek.')).toBeInTheDocument();
    expect(
      screen.getByText('Secure checkout is powered by Stripe.'),
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
        '200 - 600 learner sessions',
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('global-plan-business')).getByText(
        '400 - 1,200 learner sessions',
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('global-plan-scale')).getByText(
        '900 - 2,700 learner sessions',
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
        name: 'Subscribe now',
      }),
    ).toBeInTheDocument();
  });

  test('shows the current subscription state for Studio on the annual tab', async () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        subscription: {
          subscription_bid: 'subscription-studio',
          product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.studioMonthly}`,
          product_code: GLOBAL_BILLING_PRODUCT_CODES.studioMonthly,
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-08-01T00:00:00Z',
          current_period_end_at: '2026-09-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: '2026-08-01T00:00:00Z',
          last_failed_at: null,
        },
      },
    });

    renderPricing();

    const studio = await screen.findByTestId('global-plan-studio');
    const currentButton = within(studio).getByRole('button', {
      name: 'Current subscription',
    });

    expect(currentButton).toBeDisabled();
    expect(within(studio).getByText('Monthly only')).toBeInTheDocument();
    expect(studio.className).toContain('bg-primary/[0.05]');
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  test('keeps same-tier annual checkout available and disables lower monthly tiers for an active Growth subscription', async () => {
    const user = userEvent.setup();
    mockUseBillingOverview.mockReturnValue({
      data: {
        subscription: {
          subscription_bid: 'subscription-growth',
          product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.growthMonthly}`,
          product_code: GLOBAL_BILLING_PRODUCT_CODES.growthMonthly,
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-08-01T00:00:00Z',
          current_period_end_at: '2026-09-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: '2026-08-01T00:00:00Z',
          last_failed_at: null,
        },
      },
    });

    renderPricing();

    expect(
      within(await screen.findByTestId('global-plan-growth')).getByRole(
        'button',
        { name: 'Subscribe now' },
      ),
    ).toBeEnabled();
    expect(
      within(screen.getByTestId('global-plan-studio')).getByRole('button', {
        name: 'View monthly plan',
      }),
    ).toBeEnabled();

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
    expect(
      within(screen.getByTestId('global-plan-business')).getByRole('button', {
        name: 'Subscribe now',
      }),
    ).toBeEnabled();
  });

  test('blocks monthly plan purchases for an active annual subscription', async () => {
    const user = userEvent.setup();
    mockUseBillingOverview.mockReturnValue({
      data: {
        subscription: {
          subscription_bid: 'subscription-business-yearly',
          product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.businessAnnual}`,
          product_code: GLOBAL_BILLING_PRODUCT_CODES.businessAnnual,
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-08-18T05:35:39Z',
          current_period_end_at: '2027-08-18T05:35:39Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: '2026-08-18T05:35:39Z',
          last_failed_at: null,
        },
      },
    });

    renderPricing();

    await screen.findByTestId('global-plan-business');
    await act(async () => {
      await user.click(screen.getByRole('tab', { name: 'Monthly' }));
    });

    expect(
      within(screen.getByTestId('global-plan-studio')).getByRole('button', {
        name: 'Downgrade unavailable',
      }),
    ).toBeDisabled();
    expect(
      within(screen.getByTestId('global-plan-growth')).getByRole('button', {
        name: 'Downgrade unavailable',
      }),
    ).toBeDisabled();
    expect(
      within(screen.getByTestId('global-plan-business')).getByRole('button', {
        name: 'Switching to a monthly plan is unavailable',
      }),
    ).toBeDisabled();
    expect(
      within(screen.getByTestId('global-plan-scale')).getByRole('button', {
        name: 'Switching to a monthly plan is unavailable',
      }),
    ).toBeDisabled();
  });

  test('starts Stripe subscription checkout from a plan click', async () => {
    const user = userEvent.setup();
    mockCheckoutSubscription.mockResolvedValue({
      bill_order_bid: 'bill-order-business',
      checkout_session_id: 'cs_business',
      provider: 'stripe',
      payment_mode: 'subscription',
      redirect_url: 'https://stripe.test/business',
      status: 'pending',
    });
    renderPricing();

    const business = await screen.findByTestId('global-plan-business');
    await act(async () => {
      await user.click(
        within(business).getByRole('button', { name: 'Subscribe now' }),
      );
    });

    expect(mockCheckoutSubscription).toHaveBeenCalledWith({
      payment_provider: 'stripe',
      product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.businessAnnual}`,
    });
    expect(mockCheckoutTopup).not.toHaveBeenCalled();
    expect(mockRememberStripeCheckoutSession).toHaveBeenCalledWith(
      'cs_business',
      'bill-order-business',
    );
    expect(mockOpenBillingCheckoutUrl).toHaveBeenCalledWith(
      'https://stripe.test/business',
    );
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
  });

  test('renders and starts Stripe checkout for the approved credit packs', async () => {
    const user = userEvent.setup();
    mockCheckoutTopup.mockResolvedValue({
      bill_order_bid: 'bill-order-topup',
      checkout_session_id: 'cs_topup',
      provider: 'stripe',
      payment_mode: 'one_time',
      redirect_url: 'https://stripe.test/topup',
      status: 'pending',
    });
    renderPricing();

    await screen.findByTestId('global-plan-studio');
    await act(async () => {
      await user.click(screen.getByRole('tab', { name: 'Credit Packs' }));
    });

    const smallPack = screen.getByTestId('global-credit-pack-250');
    const largePack = screen.getByTestId('global-credit-pack-3000');
    expect(within(smallPack).getByText('$29')).toBeInTheDocument();
    expect(within(largePack).getByText('$279')).toBeInTheDocument();
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
        within(largePack).getByRole('button', { name: 'Buy now' }),
      );
    });

    expect(mockCheckoutTopup).toHaveBeenCalledWith({
      payment_provider: 'stripe',
      product_bid: `bid-${GLOBAL_BILLING_PRODUCT_CODES.credits3000}`,
    });
    expect(mockRememberStripeCheckoutSession).toHaveBeenCalledWith(
      'cs_topup',
      'bill-order-topup',
    );
    expect(mockOpenBillingCheckoutUrl).toHaveBeenCalledWith(
      'https://stripe.test/topup',
    );
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
  });

  test('shows an unavailable toast when Stripe checkout has no redirect URL', async () => {
    const user = userEvent.setup();
    mockCheckoutSubscription.mockResolvedValue({
      bill_order_bid: 'bill-order-unsupported',
      provider: 'stripe',
      payment_mode: 'subscription',
      status: 'unsupported',
    });
    renderPricing();

    const business = await screen.findByTestId('global-plan-business');
    await act(async () => {
      await user.click(
        within(business).getByRole('button', { name: 'Subscribe now' }),
      );
    });

    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.billing.checkout.unsupported',
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

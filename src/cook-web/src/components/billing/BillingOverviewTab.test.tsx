import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import { useBillingOverview } from '@/hooks/useBillingOverview';
import { rememberStripeCheckoutSession } from '@/lib/stripe-storage';
import useSWR from 'swr';
import {
  openBillingCheckoutUrl,
  openBillingPaymentWindow,
} from '@/lib/billing';
import { BillingOverviewTab } from './BillingOverviewTab';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (options?.date) {
        return `${key}:${options.date}`;
      }
      return key;
    },
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    cancelBillingSubscription: jest.fn(),
    checkoutBillingSubscription: jest.fn(),
    checkoutBillingTopup: jest.fn(),
    getBillingCatalog: jest.fn(),
    resumeBillingSubscription: jest.fn(),
  },
}));

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}));

jest.mock('@/hooks/useBillingOverview', () => ({
  __esModule: true,
  useBillingOverview: jest.fn(),
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
    openBillingPaymentWindow: jest.fn(),
  };
});

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      paymentChannels: string[];
      runtimeConfigLoaded: boolean;
      stripeEnabled: string;
    }) => unknown,
  ) =>
    selector({
      paymentChannels: ['stripe', 'pingxx'],
      runtimeConfigLoaded: true,
      stripeEnabled: 'true',
    }),
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

const mockGetBillingCatalog = api.getBillingCatalog as jest.Mock;
const mockCancelBillingSubscription =
  api.cancelBillingSubscription as jest.Mock;
const mockCheckoutBillingSubscription =
  api.checkoutBillingSubscription as jest.Mock;
const mockCheckoutBillingTopup = api.checkoutBillingTopup as jest.Mock;
const mockResumeBillingSubscription =
  api.resumeBillingSubscription as jest.Mock;
const mockUseBillingOverview = useBillingOverview as jest.Mock;
const mockUseSWR = useSWR as jest.Mock;
const mockRememberStripeCheckoutSession =
  rememberStripeCheckoutSession as jest.Mock;
const mockOpenBillingCheckoutUrl = openBillingCheckoutUrl as jest.Mock;
const mockOpenBillingPaymentWindow = openBillingPaymentWindow as jest.Mock;
const mockToast = toast as jest.Mock;
const mockMutateOverview = jest.fn();
const CATALOG_RESPONSE = {
  plans: [
    {
      product_bid: 'billing-product-plan-monthly',
      product_code: 'creator-plan-monthly',
      product_type: 'plan' as const,
      display_name: 'module.billing.catalog.plans.creatorMonthly.title',
      description: 'module.billing.catalog.plans.creatorMonthly.description',
      billing_interval: 'month' as const,
      billing_interval_count: 1,
      currency: 'CNY',
      price_amount: 9900,
      credit_amount: 300000,
      auto_renew_enabled: true,
    },
    {
      product_bid: 'billing-product-plan-yearly',
      product_code: 'creator-plan-yearly',
      product_type: 'plan' as const,
      display_name: 'module.billing.catalog.plans.creatorYearly.title',
      description: 'module.billing.catalog.plans.creatorYearly.description',
      billing_interval: 'year' as const,
      billing_interval_count: 1,
      currency: 'CNY',
      price_amount: 99900,
      credit_amount: 3600000,
      auto_renew_enabled: true,
      status_badge_key: 'module.billing.catalog.badges.recommended',
    },
  ],
  topups: [
    {
      product_bid: 'billing-product-topup-small',
      product_code: 'creator-topup-small',
      product_type: 'topup' as const,
      display_name: 'module.billing.catalog.topups.creatorSmall.title',
      description: 'module.billing.catalog.topups.creatorSmall.description',
      currency: 'CNY',
      price_amount: 19900,
      credit_amount: 500000,
    },
  ],
};

function renderOverviewTab() {
  return render(<BillingOverviewTab />);
}

describe('BillingOverviewTab', () => {
  beforeEach(() => {
    mockGetBillingCatalog.mockReset();
    mockCancelBillingSubscription.mockReset();
    mockCheckoutBillingSubscription.mockReset();
    mockCheckoutBillingTopup.mockReset();
    mockResumeBillingSubscription.mockReset();
    mockUseBillingOverview.mockReset();
    mockUseSWR.mockReset();
    mockRememberStripeCheckoutSession.mockReset();
    mockOpenBillingCheckoutUrl.mockReset();
    mockOpenBillingPaymentWindow.mockReset();
    mockToast.mockReset();
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
          product_bid: 'billing-product-plan-monthly',
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
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });

    mockGetBillingCatalog.mockResolvedValue({
      ...CATALOG_RESPONSE,
    });
    mockUseSWR.mockReturnValue({
      data: CATALOG_RESPONSE,
      error: undefined,
      isLoading: false,
    });
  });

  test('cancels a subscription from the current subscription card', async () => {
    const user = userEvent.setup();
    mockCancelBillingSubscription.mockResolvedValue({
      subscription_bid: 'sub-1',
      product_bid: 'billing-product-plan-monthly',
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
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.overview.actions.cancelSubscription',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCancelBillingSubscription).toHaveBeenCalledWith({
        subscription_bid: 'sub-1',
      });
    });

    expect(mockMutateOverview).toHaveBeenCalled();
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'module.billing.overview.feedback.cancelSuccess',
      }),
    );
  });

  test('resumes a cancel-scheduled subscription from the current subscription card', async () => {
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
          product_bid: 'billing-product-plan-monthly',
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
        billing_alerts: [],
      },
      error: undefined,
      isLoading: false,
      mutate: mockMutateOverview,
    });
    mockResumeBillingSubscription.mockResolvedValue({
      subscription_bid: 'sub-1',
      product_bid: 'billing-product-plan-monthly',
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
          name: 'module.billing.overview.actions.resumeSubscription',
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

  test('renders wallet summary, subscription card, and catalog cards', async () => {
    renderOverviewTab();

    expect(screen.getByText('120.5')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.billing.status.active').length,
    ).toBeGreaterThan(0);

    expect(
      screen.getAllByText('module.billing.catalog.plans.creatorMonthly.title')
        .length,
    ).toBeGreaterThan(0);

    expect(
      screen.getByText('module.billing.catalog.topups.creatorSmall.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.catalog.badges.recommended'),
    ).toBeInTheDocument();
  });

  test('opens a Stripe subscription checkout from the confirmation dialog', async () => {
    const user = userEvent.setup();
    mockCheckoutBillingSubscription.mockResolvedValue({
      billing_order_bid: 'order-plan-1',
      provider: 'stripe',
      payment_mode: 'subscription',
      status: 'pending',
      redirect_url: 'https://stripe.test/checkout',
      checkout_session_id: 'cs_test_123',
    });

    renderOverviewTab();

    await act(async () => {
      await user.click(
        (
          await screen.findAllByRole('button', {
            name: 'module.billing.catalog.actions.subscribe',
          })
        )[0],
      );
    });

    expect(
      screen.getByText('module.billing.checkout.title'),
    ).toBeInTheDocument();

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
          product_bid: 'billing-product-plan-yearly',
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

  test('opens a Pingxx QR top-up checkout from the confirmation dialog', async () => {
    const user = userEvent.setup();
    mockCheckoutBillingTopup.mockResolvedValue({
      billing_order_bid: 'order-topup-1',
      provider: 'pingxx',
      payment_mode: 'one_time',
      status: 'pending',
      payment_payload: {
        credential: {
          alipay_qr: 'https://pingxx.test/qr',
        },
      },
    });
    mockOpenBillingPaymentWindow.mockReturnValue(true);

    renderOverviewTab();

    await act(async () => {
      await user.click(
        await screen.findByRole('button', {
          name: 'module.billing.catalog.actions.buyWithPingxx',
        }),
      );
    });

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
          channel: 'alipay_qr',
          payment_provider: 'pingxx',
          product_bid: 'billing-product-topup-small',
        }),
      );
    });

    expect(mockOpenBillingPaymentWindow).toHaveBeenCalledWith(
      'https://pingxx.test/qr',
    );
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'module.billing.checkout.qrOpened',
      }),
    );
  });
});

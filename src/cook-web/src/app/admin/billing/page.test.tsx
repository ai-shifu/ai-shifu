import React from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { useBillingOverview } from '@/hooks/useBillingData';
import { AdminBillingPageClient } from './AdminBillingPageClient';

let mockSearchParamsValue = '';
const mockReplace = jest.fn();

jest.mock('next/navigation', () => ({
  usePathname: () => '/admin/billing',
  useRouter: () => ({
    replace: mockReplace,
  }),
  useSearchParams: () => new URLSearchParams(mockSearchParamsValue),
}));

const mockEnvState = {
  billingEnabled: 'true',
  paymentChannels: ['stripe', 'pingxx'],
  runtimeConfigLoaded: true,
  stripeEnabled: 'true',
};

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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
    getBillingBootstrap: jest.fn(),
    getBillingCatalog: jest.fn(),
    getBillingLedger: jest.fn(),
    getBillingWalletBuckets: jest.fn(),
  },
}));

jest.mock('@/hooks/useBillingData', () => ({
  ...jest.requireActual('@/hooks/useBillingData'),
  useBillingOverview: jest.fn(),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/components/ui/Sheet', () => ({
  __esModule: true,
  Sheet: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div>{children}</div> : null,
  SheetContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetDescription: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

const mockGetBillingBootstrap = api.getBillingBootstrap as jest.Mock;
const mockGetBillingCatalog = api.getBillingCatalog as jest.Mock;
const mockGetBillingLedger = api.getBillingLedger as jest.Mock;
const mockGetBillingWalletBuckets = api.getBillingWalletBuckets as jest.Mock;
const mockUseBillingOverview = useBillingOverview as jest.Mock;

function renderPage(
  props: React.ComponentProps<typeof AdminBillingPageClient> = {},
) {
  return render(
    <SWRConfig
      value={{
        provider: () => new Map(),
      }}
    >
      <AdminBillingPageClient {...props} />
    </SWRConfig>,
  );
}

describe('AdminBillingPage', () => {
  beforeEach(() => {
    mockSearchParamsValue = '';
    mockReplace.mockReset();
    mockEnvState.billingEnabled = 'true';
    mockEnvState.paymentChannels = ['stripe', 'pingxx'];
    mockEnvState.runtimeConfigLoaded = true;
    mockEnvState.stripeEnabled = 'true';

    mockGetBillingBootstrap.mockReset();
    mockGetBillingCatalog.mockReset();
    mockGetBillingLedger.mockReset();
    mockGetBillingWalletBuckets.mockReset();
    mockUseBillingOverview.mockReset();

    const bootstrapPayload = {
      service: 'billing',
      status: 'bootstrap',
      path_prefix: '/api/billing',
      creator_routes: [],
      admin_routes: [],
      capabilities: [
        {
          key: 'creator_catalog',
          status: 'active',
          audience: 'creator',
          user_visible: true,
          default_enabled: true,
          entry_points: [],
          notes: [],
        },
        {
          key: 'billing_feature_flag',
          status: 'default_disabled',
          audience: 'ops',
          user_visible: false,
          default_enabled: false,
          entry_points: [],
          notes: [],
        },
        {
          key: 'usage_settlement',
          status: 'internal_only',
          audience: 'worker',
          user_visible: false,
          default_enabled: true,
          entry_points: [],
          notes: [],
        },
      ],
      notes: [],
    };

    mockGetBillingCatalog.mockResolvedValue({
      plans: [
        {
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          product_type: 'plan',
          display_name: 'module.billing.catalog.plans.creatorMonthly.title',
          description:
            'module.billing.catalog.plans.creatorMonthly.description',
          billing_interval: 'month',
          billing_interval_count: 1,
          currency: 'CNY',
          price_amount: 9900,
          credit_amount: 300000,
          auto_renew_enabled: true,
        },
        {
          product_bid: 'bill-product-plan-yearly',
          product_code: 'creator-plan-yearly',
          product_type: 'plan',
          display_name: 'module.billing.catalog.plans.creatorYearly.title',
          description: 'module.billing.catalog.plans.creatorYearly.description',
          billing_interval: 'year',
          billing_interval_count: 1,
          currency: 'CNY',
          price_amount: 99900,
          credit_amount: 3600000,
          auto_renew_enabled: true,
        },
      ],
      topups: [
        {
          product_bid: 'bill-product-topup-small',
          product_code: 'creator-topup-small',
          product_type: 'topup',
          display_name: 'module.billing.catalog.topups.creatorSmall.title',
          description: 'module.billing.catalog.topups.creatorSmall.description',
          currency: 'CNY',
          price_amount: 19900,
          credit_amount: 500000,
        },
      ],
    });
    mockGetBillingBootstrap.mockResolvedValue(bootstrapPayload);
    mockGetBillingWalletBuckets.mockResolvedValue({
      items: [
        {
          wallet_bucket_bid: 'bucket-subscription',
          category: 'subscription',
          source_type: 'gift',
          source_bid: 'gift-1',
          available_credits: 10,
          effective_from: '2026-04-01T00:00:00Z',
          effective_to: '2026-08-12T23:59:00',
          priority: 20,
          status: 'active',
        },
      ],
    });
    mockGetBillingLedger.mockResolvedValue({
      items: [
        {
          ledger_bid: 'ledger-1',
          wallet_bucket_bid: 'bucket-subscription',
          entry_type: 'consume',
          source_type: 'usage',
          source_bid: 'usage-1',
          idempotency_key: 'usage-1-bucket-subscription',
          amount: -2.5,
          balance_after: 97.5,
          expires_at: null,
          consumable_from: null,
          metadata: {
            usage_bid: 'usage-1',
            usage_scene: 'production',
            metric_breakdown: [
              {
                billing_metric: 'llm_output_tokens',
                raw_amount: 1234,
                unit_size: 1000,
                credits_per_unit: 1.25,
                rounding_mode: 'ceil',
                consumed_credits: 2.5,
              },
            ],
          },
          created_at: '2026-04-06T10:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 4,
      total: 1,
    });
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
      mutate: jest.fn(),
    });
  });

  test('renders tab triggers and defaults to packages tab', async () => {
    renderPage();
    const tabs = screen.getByTestId('admin-billing-tabs');
    const packagesPanel = screen.getByTestId('admin-billing-packages-panel');

    expect(screen.getByTestId('admin-billing-page')).toBeInTheDocument();
    expect(screen.getByTestId('admin-billing-page')).toHaveClass(
      'overscroll-none',
    );
    expect(packagesPanel).toHaveClass('flex-1');
    expect(packagesPanel).toHaveClass('overflow-y-auto');
    expect(
      within(tabs).getByRole('tab', {
        name: 'module.billing.page.tabs.plans',
      }),
    ).toBeInTheDocument();
    expect(
      within(tabs).getByRole('tab', {
        name: 'module.billing.page.tabs.ledger',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.package.title'),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetBillingCatalog).toHaveBeenCalledTimes(1);
    });

    expect(mockGetBillingWalletBuckets).not.toHaveBeenCalled();
    expect(mockGetBillingLedger).not.toHaveBeenCalled();
  });

  test('redirects back to admin when billing is disabled', async () => {
    mockEnvState.billingEnabled = 'false';

    renderPage();

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
    expect(mockGetBillingBootstrap).not.toHaveBeenCalled();
    expect(mockGetBillingCatalog).not.toHaveBeenCalled();
    expect(screen.queryByTestId('admin-billing-page')).not.toBeInTheDocument();
  });

  test('switches to details and scrolls when an open-orders alert is triggered', async () => {
    const user = userEvent.setup();
    const scrollIntoView = jest.fn();
    Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    });

    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 10,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 490,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'bill-product-plan-monthly',
          product_code: 'creator-plan-monthly',
          status: 'past_due',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: '2026-04-06T12:00:00Z',
        },
        billing_alerts: [
          {
            code: 'subscription_past_due',
            severity: 'error',
            message_key: 'module.billing.alerts.subscriptionPastDue',
            action_type: 'open_orders',
            action_payload: {
              subscription_bid: 'sub-1',
            },
          },
        ],
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
      mutate: jest.fn(),
    });

    renderPage();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.alerts.actions.openOrders',
        }),
      );
    });

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled();
      expect(mockGetBillingLedger).toHaveBeenCalledTimes(1);
    });
    expect(mockGetBillingLedger).toHaveBeenCalledWith({
      page_index: 1,
      page_size: 10,
      timezone: 'Asia/Shanghai',
    });

    expect(
      screen.getByRole('tab', {
        name: 'module.billing.page.tabs.ledger',
      }),
    ).toBeInTheDocument();
  });

  test('opens the details tab when the url tab query targets details', async () => {
    mockSearchParamsValue = 'tab=details';

    renderPage();
    const tabs = screen.getByTestId('admin-billing-tabs');

    expect(
      within(tabs).getByRole('tab', {
        name: 'module.billing.page.tabs.plans',
      }),
    ).toBeInTheDocument();
    expect(
      within(tabs).getByRole('tab', {
        name: 'module.billing.page.tabs.ledger',
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText('module.billing.details.title'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('admin-billing-details-panel')).toHaveClass(
      'overflow-y-auto',
    );
    expect(mockGetBillingCatalog).toHaveBeenCalledWith({
      timezone: 'Asia/Shanghai',
    });
  });

  test('respects the server-provided initial details tab before search params hydrate', async () => {
    renderPage({ initialTab: 'details' });
    const tabs = screen.getByTestId('admin-billing-tabs');

    expect(
      within(tabs).getByRole('tab', {
        name: 'module.billing.page.tabs.plans',
      }),
    ).toBeInTheDocument();
    expect(
      within(tabs).getByRole('tab', {
        name: 'module.billing.page.tabs.ledger',
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText('module.billing.details.title'),
    ).toBeInTheDocument();
  });
});

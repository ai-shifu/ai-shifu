import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { useBillingOverview } from '@/hooks/useBillingOverview';

import AdminBillingPage from './page';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    bindAdminBillingDomain: jest.fn(),
    getBillingCatalog: jest.fn(),
    getBillingDailyLedgerSummary: jest.fn(),
    getBillingDailyUsageMetrics: jest.fn(),
    getBillingEntitlements: jest.fn(),
    getBillingLedger: jest.fn(),
    getBillingOrders: jest.fn(),
    getBillingWalletBuckets: jest.fn(),
    getAdminBillingDomainBindings: jest.fn(),
  },
}));

jest.mock('@/hooks/useBillingOverview', () => ({
  __esModule: true,
  useBillingOverview: jest.fn(),
}));

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

const mockBindAdminBillingDomain = api.bindAdminBillingDomain as jest.Mock;
const mockGetBillingCatalog = api.getBillingCatalog as jest.Mock;
const mockGetBillingDailyLedgerSummary =
  api.getBillingDailyLedgerSummary as jest.Mock;
const mockGetBillingDailyUsageMetrics =
  api.getBillingDailyUsageMetrics as jest.Mock;
const mockGetBillingEntitlements = api.getBillingEntitlements as jest.Mock;
const mockGetBillingLedger = api.getBillingLedger as jest.Mock;
const mockGetBillingOrders = api.getBillingOrders as jest.Mock;
const mockGetBillingWalletBuckets = api.getBillingWalletBuckets as jest.Mock;
const mockGetAdminBillingDomainBindings =
  api.getAdminBillingDomainBindings as jest.Mock;
const mockUseBillingOverview = useBillingOverview as jest.Mock;

describe('AdminBillingPage', () => {
  beforeEach(() => {
    mockBindAdminBillingDomain.mockReset();
    mockGetBillingCatalog.mockReset();
    mockGetBillingDailyLedgerSummary.mockReset();
    mockGetBillingDailyUsageMetrics.mockReset();
    mockGetBillingEntitlements.mockReset();
    mockGetBillingLedger.mockReset();
    mockGetBillingOrders.mockReset();
    mockGetBillingWalletBuckets.mockReset();
    mockGetAdminBillingDomainBindings.mockReset();
    mockUseBillingOverview.mockReset();

    mockGetBillingCatalog.mockResolvedValue({
      plans: [],
      topups: [],
    });
    mockGetBillingDailyUsageMetrics.mockResolvedValue({
      items: [
        {
          daily_usage_metric_bid: 'daily-usage-1',
          stat_date: '2026-04-06',
          shifu_bid: 'shifu-1',
          usage_scene: 'production',
          usage_type: 'llm',
          provider: 'openai',
          model: 'gpt-4o-mini',
          billing_metric: 'llm_output_tokens',
          raw_amount: 1234,
          record_count: 3,
          consumed_credits: 4.5,
          window_started_at: '2026-04-06T00:00:00+00:00',
          window_ended_at: '2026-04-07T00:00:00+00:00',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 8,
      total: 1,
    });
    mockGetBillingDailyLedgerSummary.mockResolvedValue({
      items: [
        {
          daily_ledger_summary_bid: 'daily-ledger-1',
          stat_date: '2026-04-06',
          entry_type: 'consume',
          source_type: 'usage',
          amount: -4.5,
          entry_count: 3,
          window_started_at: '2026-04-06T00:00:00+00:00',
          window_ended_at: '2026-04-07T00:00:00+00:00',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 8,
      total: 1,
    });
    mockGetBillingWalletBuckets.mockResolvedValue([
      {
        wallet_bucket_bid: 'bucket-free',
        category: 'free',
        source_type: 'gift',
        source_bid: 'grant-1',
        available_credits: 80,
        effective_from: '2026-03-01T00:00:00Z',
        effective_to: '2026-05-01T00:00:00Z',
        priority: 10,
        status: 'active',
      },
    ]);
    mockGetBillingLedger.mockResolvedValue({
      items: [
        {
          ledger_bid: 'ledger-1',
          wallet_bucket_bid: 'bucket-free',
          entry_type: 'consume',
          source_type: 'usage',
          source_bid: 'usage-1',
          idempotency_key: 'usage-1-bucket-free',
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
      page_size: 10,
      total: 1,
    });
    mockGetBillingOrders.mockResolvedValue({
      items: [
        {
          billing_order_bid: 'order-1',
          creator_bid: 'creator-1',
          product_bid: 'billing-product-plan-monthly',
          subscription_bid: 'sub-1',
          order_type: 'subscription_start',
          status: 'paid',
          payment_provider: 'stripe',
          payment_mode: 'subscription',
          payable_amount: 9900,
          paid_amount: 9900,
          currency: 'CNY',
          provider_reference_id: 'cs_test_1',
          failure_message: '',
          created_at: '2026-04-05T12:00:00Z',
          paid_at: '2026-04-05T12:05:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });
    mockGetBillingEntitlements.mockResolvedValue({
      branding_enabled: true,
      custom_domain_enabled: true,
      priority_class: 'priority',
      max_concurrency: 3,
      analytics_tier: 'advanced',
      support_tier: 'business_hours',
    });
    mockGetAdminBillingDomainBindings.mockResolvedValue({
      creator_bid: 'creator-1',
      custom_domain_enabled: true,
      items: [
        {
          domain_binding_bid: 'domain-1',
          creator_bid: 'creator-1',
          host: 'creator.example.com',
          status: 'verified',
          verification_method: 'dns_txt',
          verification_token: 'verify-token-1',
          verification_record_name: '_ai-shifu.creator.example.com',
          verification_record_value: 'verify-token-1',
          last_verified_at: '2026-04-06T12:00:00Z',
          ssl_status: 'issued',
          is_effective: true,
          metadata: {},
        },
      ],
    });
    mockBindAdminBillingDomain.mockResolvedValue({
      action: 'bind',
      binding: {
        domain_binding_bid: 'domain-2',
        creator_bid: 'creator-1',
        host: 'new.example.com',
        status: 'pending',
        verification_method: 'dns_txt',
        verification_token: 'verify-token-2',
        verification_record_name: '_ai-shifu.new.example.com',
        verification_record_value: 'verify-token-2',
        last_verified_at: null,
        ssl_status: 'not_requested',
        is_effective: false,
        metadata: {},
      },
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
      },
      error: undefined,
      isLoading: false,
    });
  });

  test('renders the expanded billing center tabs and switches content', async () => {
    const user = userEvent.setup();

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingPage />
      </SWRConfig>,
    );

    expect(screen.getByTestId('admin-billing-page')).toBeInTheDocument();
    expect(screen.getByText('module.billing.page.title')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'module.billing.page.adminLink' }),
    ).toHaveAttribute('href', '/admin/billing/admin');
    expect(
      screen.getByRole('tab', { name: 'module.billing.page.tabs.plans' }),
    ).toHaveAttribute('data-state', 'active');
    expect(
      screen.getByRole('tab', {
        name: 'module.billing.page.tabs.entitlements',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('tab', { name: 'module.billing.page.tabs.domains' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('tab', { name: 'module.billing.page.tabs.reports' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.overview.walletTitle'),
    ).toBeInTheDocument();
    expect(mockGetBillingWalletBuckets).not.toHaveBeenCalled();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', { name: 'module.billing.page.tabs.ledger' }),
      );
    });

    expect(screen.getByText('module.billing.ledger.title')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.entriesTitle'),
    ).toBeInTheDocument();
    expect(await screen.findByText('grant-1')).toBeInTheDocument();
    expect(mockGetBillingWalletBuckets).toHaveBeenCalledTimes(1);
    expect(mockGetBillingLedger).toHaveBeenCalledTimes(1);

    await act(async () => {
      await user.click(
        screen.getByRole('tab', { name: 'module.billing.page.tabs.orders' }),
      );
    });

    expect(screen.getByText('module.billing.orders.title')).toBeInTheDocument();
    expect(await screen.findByText('order-1')).toBeInTheDocument();
    expect(mockGetBillingOrders).toHaveBeenCalledTimes(1);

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.page.tabs.entitlements',
        }),
      );
    });

    expect(
      screen.getByText('module.billing.entitlements.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.entitlements.description'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.entitlements.priority.priority'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.entitlements.support.businessHours'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', { name: 'module.billing.page.tabs.domains' }),
      );
    });

    expect(
      screen.getByText('module.billing.domains.branding.title'),
    ).toBeInTheDocument();
    expect(await screen.findByText('creator.example.com')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.domains.settings.effectiveDomain'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', { name: 'module.billing.page.tabs.reports' }),
      );
    });

    expect(
      screen.getByText('module.billing.reports.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.reports.sections.usage.title'),
    ).toBeInTheDocument();
    expect(await screen.findByText('shifu-1')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.reports.metric.llmOutputTokens'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.reports.sections.ledger.title'),
    ).toBeInTheDocument();
  });

  test('opens the orders tab from a structured billing alert action', async () => {
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
      },
      error: undefined,
      isLoading: false,
    });

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingPage />
      </SWRConfig>,
    );

    expect(
      screen.getByText('module.billing.alerts.subscriptionPastDue'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.catalog.labels.providerStripe'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.alerts.actions.openOrders',
        }),
      );
    });

    expect(
      screen.getByRole('tab', { name: 'module.billing.page.tabs.orders' }),
    ).toHaveAttribute('data-state', 'active');
    expect(await screen.findByText('order-1')).toBeInTheDocument();
    expect(mockGetBillingOrders).toHaveBeenCalledTimes(1);
  });
});

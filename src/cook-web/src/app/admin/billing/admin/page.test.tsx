import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';

import AdminBillingConsolePage from './page';

const mockReplace = jest.fn();
const mockEnvState = {
  billingEnabled: 'true',
  runtimeConfigLoaded: true,
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/lib/browser-timezone', () => ({
  __esModule: true,
  getBrowserTimeZone: () => 'Asia/Shanghai',
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    adjustAdminBillingLedger: jest.fn(),
    getBillingBootstrap: jest.fn(),
    getAdminBillingDailyLedgerSummary: jest.fn(),
    getAdminBillingDailyUsageMetrics: jest.fn(),
    getAdminBillingDomainAudits: jest.fn(),
    getAdminBillingEntitlements: jest.fn(),
    getAdminBillingSubscriptions: jest.fn(),
    getAdminBillingOrders: jest.fn(),
  },
}));

const mockAdjustAdminBillingLedger = api.adjustAdminBillingLedger as jest.Mock;
const mockGetBillingBootstrap = api.getBillingBootstrap as jest.Mock;
const mockGetAdminBillingDailyLedgerSummary =
  api.getAdminBillingDailyLedgerSummary as jest.Mock;
const mockGetAdminBillingDailyUsageMetrics =
  api.getAdminBillingDailyUsageMetrics as jest.Mock;
const mockGetAdminBillingDomainAudits =
  api.getAdminBillingDomainAudits as jest.Mock;
const mockGetAdminBillingEntitlements =
  api.getAdminBillingEntitlements as jest.Mock;
const mockGetAdminBillingSubscriptions =
  api.getAdminBillingSubscriptions as jest.Mock;
const mockGetAdminBillingOrders = api.getAdminBillingOrders as jest.Mock;

describe('AdminBillingConsolePage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockEnvState.billingEnabled = 'true';
    mockEnvState.runtimeConfigLoaded = true;
    mockAdjustAdminBillingLedger.mockReset();
    mockGetBillingBootstrap.mockReset();
    mockGetAdminBillingDailyLedgerSummary.mockReset();
    mockGetAdminBillingDailyUsageMetrics.mockReset();
    mockGetAdminBillingDomainAudits.mockReset();
    mockGetAdminBillingEntitlements.mockReset();
    mockGetAdminBillingSubscriptions.mockReset();
    mockGetAdminBillingOrders.mockReset();

    mockGetBillingBootstrap.mockResolvedValue({
      service: 'billing',
      status: 'bootstrap',
      path_prefix: '/api/billing',
      creator_routes: [],
      admin_routes: [],
      capabilities: [
        {
          key: 'admin_orders',
          status: 'active',
          audience: 'admin',
          user_visible: true,
          default_enabled: true,
          entry_points: [],
          notes: [],
        },
        {
          key: 'renewal_task_queue',
          status: 'default_disabled',
          audience: 'ops',
          user_visible: false,
          default_enabled: false,
          entry_points: [],
          notes: [],
        },
        {
          key: 'renewal_compensation',
          status: 'internal_only',
          audience: 'worker',
          user_visible: false,
          default_enabled: true,
          entry_points: [],
          notes: [],
        },
      ],
      notes: [],
    });

    mockGetAdminBillingSubscriptions.mockResolvedValue({
      items: [
        {
          subscription_bid: 'sub-past-due',
          creator_bid: 'creator-2',
          product_bid: 'bill-product-plan-yearly',
          product_code: 'creator-plan-yearly',
          status: 'past_due',
          billing_provider: 'stripe',
          current_period_start_at: '2026-03-01T00:00:00Z',
          current_period_end_at: '2026-04-01T00:00:00Z',
          grace_period_end_at: '2026-04-08T00:00:00Z',
          cancel_at_period_end: false,
          next_product_bid: null,
          next_product_code: '',
          last_renewed_at: '2026-03-01T00:00:00Z',
          last_failed_at: '2026-04-02T12:00:00Z',
          wallet: {
            available_credits: 5,
            reserved_credits: 0,
            lifetime_granted_credits: 5,
            lifetime_consumed_credits: 0,
          },
          latest_renewal_event: {
            renewal_event_bid: 'renewal-1',
            event_type: 'retry',
            status: 'failed',
            scheduled_at: '2026-04-03T08:00:00Z',
            processed_at: '2026-04-03T08:05:00Z',
            attempt_count: 2,
            last_error: 'card_declined',
            payload: {
              bill_order_bid: 'order-1',
            },
          },
          has_attention: true,
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });
    mockGetAdminBillingOrders.mockResolvedValue({
      items: [
        {
          bill_order_bid: 'order-1',
          creator_bid: 'creator-2',
          product_bid: 'bill-product-plan-yearly',
          subscription_bid: 'sub-past-due',
          order_type: 'subscription_renewal',
          status: 'failed',
          payment_provider: 'stripe',
          payment_mode: 'subscription',
          payable_amount: 99900,
          paid_amount: 0,
          currency: 'CNY',
          provider_reference_id: 'cs_failed',
          failure_message: 'Card was declined',
          failure_code: 'card_declined',
          created_at: '2026-04-03T07:55:00Z',
          paid_at: null,
          failed_at: '2026-04-03T08:00:00Z',
          refunded_at: null,
          has_attention: true,
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });
    mockGetAdminBillingEntitlements.mockResolvedValue({
      items: [
        {
          creator_bid: 'creator-2',
          source_kind: 'snapshot',
          source_type: 'manual',
          source_bid: 'manual-2',
          product_bid: '',
          branding_enabled: true,
          custom_domain_enabled: false,
          priority_class: 'priority',
          analytics_tier: 'advanced',
          support_tier: 'business_hours',
          effective_from: '2026-04-01T00:00:00Z',
          effective_to: null,
          feature_payload: {},
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });
    mockGetAdminBillingDomainAudits.mockResolvedValue({
      items: [
        {
          domain_binding_bid: 'binding-1',
          creator_bid: 'creator-2',
          host: 'academy.creator-two.com',
          status: 'pending',
          verification_method: 'dns_txt',
          verification_token: 'token-1',
          verification_record_name: '_ai-shifu.academy.creator-two.com',
          verification_record_value: 'token-1',
          last_verified_at: null,
          ssl_status: 'pending',
          is_effective: false,
          custom_domain_enabled: false,
          has_attention: true,
          metadata: {},
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });
    mockGetAdminBillingDailyUsageMetrics.mockResolvedValue({
      items: [
        {
          creator_bid: 'creator-2',
          daily_usage_metric_bid: 'daily-usage-1',
          stat_date: '2026-04-06',
          shifu_bid: 'shifu-2',
          usage_scene: 'production',
          usage_type: 'llm',
          provider: 'openai',
          model: 'gpt-4o-mini',
          billing_metric: 'llm_output_tokens',
          raw_amount: 4096,
          record_count: 4,
          consumed_credits: 6.5,
          window_started_at: '2026-04-06T00:00:00Z',
          window_ended_at: '2026-04-07T00:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 6,
      total: 1,
    });
    mockGetAdminBillingDailyLedgerSummary.mockResolvedValue({
      items: [
        {
          creator_bid: 'creator-2',
          daily_ledger_summary_bid: 'daily-ledger-1',
          stat_date: '2026-04-06',
          entry_type: 'consume',
          source_type: 'usage',
          amount: -6.5,
          entry_count: 4,
          window_started_at: '2026-04-06T00:00:00Z',
          window_ended_at: '2026-04-07T00:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 6,
      total: 1,
    });
    mockAdjustAdminBillingLedger.mockResolvedValue({
      status: 'adjusted',
      creator_bid: 'creator-2',
      amount: 12.5,
      wallet: {
        wallet_bid: 'wallet-2',
        available_credits: 17.5,
        reserved_credits: 0,
      },
      wallet_bucket_bids: ['bucket-1'],
      ledger_bids: ['ledger-1'],
    });
  });

  test('redirects back to admin when billing is disabled', async () => {
    mockEnvState.billingEnabled = 'false';

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingConsolePage />
      </SWRConfig>,
    );

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
    expect(
      screen.queryByTestId('admin-billing-console-page'),
    ).not.toBeInTheDocument();
  });

  test('renders admin billing tabs and loads subscriptions, orders, and exceptions', async () => {
    const user = userEvent.setup();

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingConsolePage />
      </SWRConfig>,
    );

    expect(
      screen.getByTestId('admin-billing-console-page'),
    ).toBeInTheDocument();
    expect(screen.getByText('module.billing.admin.title')).toBeInTheDocument();
    expect(
      screen.getByRole('link', {
        name: 'module.billing.admin.backToCreatorBilling',
      }),
    ).toHaveAttribute('href', '/admin/billing');
    expect(
      screen.getByRole('tab', {
        name: 'module.billing.admin.tabs.subscriptions',
      }),
    ).toHaveAttribute('data-state', 'active');
    expect(mockGetAdminBillingSubscriptions).toHaveBeenCalledWith({
      page_index: 1,
      page_size: 10,
      timezone: 'Asia/Shanghai',
    });
    expect(await screen.findByText('sub-past-due')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.renewal.eventType.retry'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.renewal.status.failed'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.orders',
        }),
      );
    });

    expect(await screen.findByText('order-1')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.admin.orders.title'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.exceptions',
        }),
      );
    });

    expect(
      await screen.findByText('module.billing.admin.exceptions.title'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('creator-2').length).toBeGreaterThan(0);
    expect(screen.getByText('Card was declined')).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.entitlements',
        }),
      );
    });

    expect(
      await screen.findByText('module.billing.admin.entitlements.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('manual-2')).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.domains',
        }),
      );
    });

    expect(
      await screen.findByText('module.billing.admin.domains.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('academy.creator-two.com')).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.reports',
        }),
      );
    });

    expect(
      await screen.findByText('module.billing.admin.reports.title'),
    ).toBeInTheDocument();
    expect(mockGetAdminBillingDailyUsageMetrics).toHaveBeenCalledWith({
      page_index: 1,
      page_size: 6,
      timezone: 'Asia/Shanghai',
    });
    expect(
      screen.getByText('module.billing.admin.reports.sections.usage.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.reports.metric.llmOutputTokens'),
    ).toBeInTheDocument();
  });

  test('submits a manual ledger adjustment and revalidates admin billing data', async () => {
    const user = userEvent.setup();

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingConsolePage />
      </SWRConfig>,
    );

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.exceptions',
        }),
      );
    });

    await screen.findByText('module.billing.admin.exceptions.title');
    const initialSubscriptionCalls =
      mockGetAdminBillingSubscriptions.mock.calls.length;
    const initialOrderCalls = mockGetAdminBillingOrders.mock.calls.length;

    await act(async () => {
      await user.click(
        screen.getAllByRole('button', {
          name: 'module.billing.admin.adjust.quickAction',
        })[0],
      );
    });

    expect(
      screen.getByRole('dialog', {
        name: 'module.billing.admin.adjust.title',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('module.billing.admin.adjust.fields.creatorBid'),
    ).toHaveValue('creator-2');

    await act(async () => {
      await user.type(
        screen.getByLabelText('module.billing.admin.adjust.fields.amount'),
        '12.5000000000',
      );
      await user.type(
        screen.getByLabelText('module.billing.admin.adjust.fields.note'),
        'manual recovery',
      );
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.admin.adjust.submit',
        }),
      );
    });

    expect(mockAdjustAdminBillingLedger).toHaveBeenCalledWith({
      creator_bid: 'creator-2',
      amount: '12.5000000000',
      note: 'manual recovery',
    });

    await screen.findByText('module.billing.admin.exceptions.title');
    expect(mockGetAdminBillingSubscriptions.mock.calls.length).toBeGreaterThan(
      initialSubscriptionCalls,
    );
    expect(mockGetAdminBillingOrders.mock.calls.length).toBeGreaterThan(
      initialOrderCalls,
    );
  });
});

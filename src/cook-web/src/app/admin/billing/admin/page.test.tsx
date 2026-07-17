import React from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';

import { AdminBillingOperationsConsole } from '@/app/admin/operations/billing/AdminBillingOperationsConsole';
import {
  applyAdminBillingOpsState,
  readAdminBillingExceptionHandledMap,
} from '@/components/billing/AdminBillingShared';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockEnvState = {
  billingEnabled: 'true',
  runtimeConfigLoaded: true,
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
  useSearchParams: () => new URLSearchParams(window.location.search),
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

const mockBrowserTimeZone = jest.fn(() => 'America/Los_Angeles');

jest.mock('@/lib/browser-timezone', () => ({
  __esModule: true,
  getBrowserTimeZone: () => mockBrowserTimeZone(),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    adjustAdminBillingLedger: jest.fn(),
    getBillingBootstrap: jest.fn(),
    getAdminBillingFocusTeachers: jest.fn(),
    getAdminBillingDailyLedgerSummary: jest.fn(),
    getAdminBillingDomainAudits: jest.fn(),
    getAdminBillingEntitlements: jest.fn(),
    grantAdminBillingEntitlement: jest.fn(),
    getAdminBillingCustomizationDraft: jest.fn(),
    saveAdminBillingCustomizationDraft: jest.fn(),
    deleteAdminBillingCustomizationDraft: jest.fn(),
    getAdminBillingSubscriptions: jest.fn(),
    getAdminBillingOrders: jest.fn(),
    getAdminBillingOpsState: jest.fn(),
    updateAdminBillingConfigStatus: jest.fn(),
    updateAdminBillingExceptionHandled: jest.fn(),
  },
}));

const mockAdjustAdminBillingLedger = api.adjustAdminBillingLedger as jest.Mock;
const mockGetBillingBootstrap = api.getBillingBootstrap as jest.Mock;
const mockGetAdminBillingFocusTeachers =
  api.getAdminBillingFocusTeachers as jest.Mock;
const mockGetAdminBillingDailyLedgerSummary =
  api.getAdminBillingDailyLedgerSummary as jest.Mock;
const mockGetAdminBillingDomainAudits =
  api.getAdminBillingDomainAudits as jest.Mock;
const mockGetAdminBillingEntitlements =
  api.getAdminBillingEntitlements as jest.Mock;
const mockGrantAdminBillingEntitlement =
  api.grantAdminBillingEntitlement as jest.Mock;
const mockGetAdminBillingCustomizationDraft =
  api.getAdminBillingCustomizationDraft as jest.Mock;
const mockSaveAdminBillingCustomizationDraft =
  api.saveAdminBillingCustomizationDraft as jest.Mock;
const mockDeleteAdminBillingCustomizationDraft =
  api.deleteAdminBillingCustomizationDraft as jest.Mock;
const mockGetAdminBillingSubscriptions =
  api.getAdminBillingSubscriptions as jest.Mock;
const mockGetAdminBillingOrders = api.getAdminBillingOrders as jest.Mock;
const mockGetAdminBillingOpsState = api.getAdminBillingOpsState as jest.Mock;
const mockUpdateAdminBillingConfigStatus =
  api.updateAdminBillingConfigStatus as jest.Mock;
const mockUpdateAdminBillingExceptionHandled =
  api.updateAdminBillingExceptionHandled as jest.Mock;

describe('AdminBillingOperationsConsole', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    window.localStorage.clear();
    applyAdminBillingOpsState({ config_status: {}, exception_handled: {} });
    mockBrowserTimeZone.mockReturnValue('America/Los_Angeles');
    mockEnvState.billingEnabled = 'true';
    mockEnvState.runtimeConfigLoaded = true;
    mockAdjustAdminBillingLedger.mockReset();
    mockGetBillingBootstrap.mockReset();
    mockGetAdminBillingFocusTeachers.mockReset();
    mockGetAdminBillingDailyLedgerSummary.mockReset();
    mockGetAdminBillingDomainAudits.mockReset();
    mockGetAdminBillingEntitlements.mockReset();
    mockGrantAdminBillingEntitlement.mockReset();
    mockGetAdminBillingCustomizationDraft.mockReset();
    mockSaveAdminBillingCustomizationDraft.mockReset();
    mockDeleteAdminBillingCustomizationDraft.mockReset();
    mockGetAdminBillingSubscriptions.mockReset();
    mockGetAdminBillingOrders.mockReset();
    mockGetAdminBillingOpsState.mockReset();
    mockUpdateAdminBillingConfigStatus.mockReset();
    mockUpdateAdminBillingExceptionHandled.mockReset();
    mockGetAdminBillingOpsState.mockResolvedValue({
      config_status: {},
      exception_handled: {},
    });
    mockUpdateAdminBillingConfigStatus.mockResolvedValue({});
    mockUpdateAdminBillingExceptionHandled.mockResolvedValue({});
    mockGetAdminBillingCustomizationDraft.mockResolvedValue({
      creator_mobile: '',
      branding_enabled: false,
      custom_domain_enabled: false,
      custom_wechat_enabled: false,
      custom_payment_enabled: false,
      config_status: 'pending',
      note: '',
      branding: { logo_wide_url: '', logo_square_url: '' },
      domain: { host: '' },
      integrations: {
        wechat_oauth: { public_config: {}, secret_config: {} },
        pingxx: { public_config: {}, secret_config: {} },
        stripe: { public_config: {}, secret_config: {} },
        alipay: { public_config: {}, secret_config: {} },
        wechatpay: { public_config: {}, secret_config: {} },
      },
    });
    mockSaveAdminBillingCustomizationDraft.mockResolvedValue({});
    mockDeleteAdminBillingCustomizationDraft.mockResolvedValue({
      status: 'deleted',
    });

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
          creator_mobile: '13800138002',
          creator_nickname: 'Teacher Two',
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
          creator_mobile: '13800138002',
          creator_nickname: 'Teacher Two',
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
          custom_wechat_enabled: false,
          custom_payment_enabled: false,
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
    mockGrantAdminBillingEntitlement.mockResolvedValue({
      creator_bid: 'creator-2',
      branding_enabled: true,
      custom_domain_enabled: true,
      custom_wechat_enabled: true,
      custom_payment_enabled: true,
    });
    mockGetAdminBillingFocusTeachers.mockResolvedValue({
      items: [
        {
          creator_bid: 'creator-2',
          creator_mobile: '13800138002',
          creator_nickname: 'Teacher Two',
          credits_7d: 12.5,
          credits_30d: 18.5,
          record_count_7d: 6,
          active_days_7d: 4,
          production_credits_30d: 8.5,
          debug_preview_credits_30d: 10,
          total_credits_30d: 18.5,
          production_ratio_30d: 0.4595,
          latest_usage_at: '2026-04-07T00:00:00Z',
          attention_reasons: ['rapid_growth', 'high_consumption'],
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
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
        <AdminBillingOperationsConsole />
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
        <AdminBillingOperationsConsole />
      </SWRConfig>,
    );

    expect(
      screen.getByTestId('admin-billing-console-page'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'module.billing.admin.title',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('tab', {
        name: 'module.billing.admin.tabs.subscriptions',
      }),
    ).toHaveAttribute('data-state', 'active');
    expect(mockGetAdminBillingSubscriptions).toHaveBeenCalledWith(
      {
        page_index: 1,
        page_size: 10,
        attention_only: true,
      },
      { skipErrorToast: true },
    );
    expect(mockGetAdminBillingSubscriptions).toHaveBeenCalledWith(
      {
        page_index: 1,
        page_size: 1,
        attention_only: true,
      },
      { skipErrorToast: true },
    );
    expect(mockGetAdminBillingOrders).toHaveBeenCalledWith(
      {
        page_index: 1,
        page_size: 1,
      },
      { skipErrorToast: true },
    );
    await waitFor(() => {
      expect(
        within(
          screen.getByRole('tab', {
            name: 'module.billing.admin.tabs.exceptions',
          }),
        ).getByText('2'),
      ).toBeInTheDocument();
    });
    expect(await screen.findByText('Teacher Two')).toBeInTheDocument();
    expect(screen.queryByText('-')).not.toBeInTheDocument();
    expect(screen.queryByText('sub-past-due')).not.toBeInTheDocument();
    expect(screen.getAllByText('2026-03-31 17:00:00').length).toBeGreaterThan(
      0,
    );
    expect(screen.queryByText('2026-04-01T00:00:00Z')).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'module.billing.admin.subscriptions.results.renewalFailedWithError',
      ),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.orders',
        }),
      );
    });

    expect(await screen.findByText('Card was declined')).toBeInTheDocument();
    expect(screen.getByText('2026-04-03 00:55:00')).toBeInTheDocument();
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
    expect(screen.getAllByText('Teacher Two').length).toBeGreaterThan(0);
    expect(screen.getByText('Card was declined')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.billing.admin.exceptions.types.subscription')
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText('module.billing.admin.exceptions.types.order').length,
    ).toBeGreaterThan(0);

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
    expect(
      screen.getAllByRole('button', {
        name: 'module.billing.admin.entitlements.actions.viewDetail',
      }).length,
    ).toBeGreaterThan(0);

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
    expect(mockGetAdminBillingFocusTeachers).toHaveBeenNthCalledWith(
      1,
      {
        page_index: 1,
        page_size: 1,
      },
      { skipErrorToast: true },
    );
    expect(mockGetAdminBillingFocusTeachers).toHaveBeenNthCalledWith(
      2,
      {
        page_index: 1,
        page_size: 1,
      },
      { skipErrorToast: true },
    );
    expect(
      screen.getByText('module.billing.admin.reports.sections.usage.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.admin.reports.summary.totalCredits'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('13800138002').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Teacher Two').length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        'module.billing.admin.reports.attentionReasons.rapid_growth',
      ),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'common.core.more',
        }),
      );
    });

    await act(async () => {
      await user.click(
        screen.getByText('module.billing.admin.reports.actions.viewOrders'),
      );
    });

    expect(mockPush).toHaveBeenCalledWith(
      '/admin/operations/orders?tab=credits&creator_keyword=13800138002',
    );

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.admin.reports.filters.rapid_growth',
        }),
      );
    });

    expect(
      screen.getByText(
        'module.billing.admin.reports.attentionReasons.rapid_growth',
      ),
    ).toBeInTheDocument();
  });

  test('grants creator customization entitlements from the admin console', async () => {
    const user = userEvent.setup();

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingOperationsConsole />
      </SWRConfig>,
    );

    await user.click(
      screen.getByRole('tab', {
        name: 'module.billing.admin.tabs.entitlements',
      }),
    );
    await user.click(
      await screen.findByRole('button', {
        name: 'module.billing.admin.entitlements.actions.viewDetail',
      }),
    );

    expect(
      screen.getByLabelText(
        'module.billing.admin.entitlements.grant.fields.creatorMobile',
      ),
    ).toHaveValue('creator-2');

    await user.click(
      screen.getByRole('switch', {
        name: 'module.billing.admin.entitlements.grant.fields.custom_domain_enabled',
      }),
    );
    await user.click(
      screen.getByRole('switch', {
        name: 'module.billing.admin.entitlements.grant.fields.custom_payment_enabled',
      }),
    );
    await user.click(
      screen.getByRole('button', {
        name: 'module.billing.admin.entitlements.grant.submit',
      }),
    );

    await waitFor(() =>
      expect(mockGrantAdminBillingEntitlement).toHaveBeenCalledWith({
        creator_bid: 'creator-2',
        branding_enabled: true,
        custom_domain_enabled: true,
        custom_wechat_enabled: false,
        custom_payment_enabled: false,
      }),
    );
  });

  test('waits for handled exception state before showing the exception badge', async () => {
    let resolveOpsState: (value: {
      config_status: Record<string, never>;
      exception_handled: Record<string, boolean>;
    }) => void = () => {};
    mockGetAdminBillingOpsState.mockReturnValue(
      new Promise(resolve => {
        resolveOpsState = resolve;
      }),
    );

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingOperationsConsole />
      </SWRConfig>,
    );

    const exceptionsTab = screen.getByRole('tab', {
      name: 'module.billing.admin.tabs.exceptions',
    });

    await waitFor(() => {
      expect(mockGetAdminBillingSubscriptions).toHaveBeenCalledWith(
        {
          page_index: 1,
          page_size: 1,
          attention_only: true,
        },
        { skipErrorToast: true },
      );
      expect(mockGetAdminBillingOrders).toHaveBeenCalledWith(
        {
          page_index: 1,
          page_size: 1,
        },
        { skipErrorToast: true },
      );
    });

    expect(within(exceptionsTab).queryByText('2')).not.toBeInTheDocument();

    await act(async () => {
      resolveOpsState({
        config_status: {},
        exception_handled: {
          'subscription:sub-past-due': true,
        },
      });
    });

    await waitFor(() => {
      expect(within(exceptionsTab).getByText('1')).toBeInTheDocument();
    });
    expect(within(exceptionsTab).queryByText('2')).not.toBeInTheDocument();
  });

  test('submits a manual ledger adjustment and revalidates admin billing data', async () => {
    const user = userEvent.setup();

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingOperationsConsole />
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
      screen.getByLabelText('module.billing.admin.adjust.fields.creatorMobile'),
    ).toHaveValue('13800138002');

    await act(async () => {
      await user.type(
        screen.getByLabelText('module.billing.admin.adjust.fields.amount'),
        '12.50',
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
      amount: '12.50',
      note: 'manual recovery',
    });
    expect(readAdminBillingExceptionHandledMap()).toMatchObject({
      'subscription:sub-past-due': true,
    });
    expect(mockUpdateAdminBillingExceptionHandled).toHaveBeenCalledWith({
      row_key: 'subscription:sub-past-due',
      handled: true,
    });

    await screen.findByText('module.billing.admin.exceptions.title');
    expect(mockGetAdminBillingSubscriptions.mock.calls.length).toBeGreaterThan(
      initialSubscriptionCalls,
    );
    expect(mockGetAdminBillingOrders.mock.calls.length).toBeGreaterThan(
      initialOrderCalls,
    );
    expect(
      screen.getByRole('button', {
        name: 'module.billing.admin.exceptions.processingStatus.done',
      }),
    ).toHaveAttribute('aria-pressed', 'true');
  });

  test('toggles exception processing status with a lightweight clickable control', async () => {
    const user = userEvent.setup();

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingOperationsConsole />
      </SWRConfig>,
    );

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.exceptions',
        }),
      );
    });

    const pendingButton = (
      await screen.findAllByRole('button', {
        name: 'module.billing.admin.exceptions.processingStatus.pending',
      })
    )[0];
    expect(pendingButton).toHaveAttribute('aria-pressed', 'false');

    await act(async () => {
      await user.click(pendingButton);
    });

    expect(
      screen.getByRole('button', {
        name: 'module.billing.admin.exceptions.processingStatus.done',
      }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(readAdminBillingExceptionHandledMap()).toMatchObject({
      'subscription:sub-past-due': true,
    });
    expect(mockUpdateAdminBillingExceptionHandled).toHaveBeenCalledWith({
      row_key: 'subscription:sub-past-due',
      handled: true,
    });
  });

  test('renders a clean empty state when there are no abnormal orders', async () => {
    const user = userEvent.setup();

    mockGetAdminBillingOrders.mockResolvedValue({
      items: [],
      page: 1,
      page_count: 0,
      page_size: 10,
      total: 0,
    });

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingOperationsConsole />
      </SWRConfig>,
    );

    await act(async () => {
      await user.click(
        screen.getByRole('tab', {
          name: 'module.billing.admin.tabs.orders',
        }),
      );
    });

    expect(
      await screen.findByText('module.billing.admin.orders.empty'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.billing.admin.pagination.page'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.dashboard.pagination.prev',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.dashboard.pagination.next',
      }),
    ).not.toBeInTheDocument();
  });
});

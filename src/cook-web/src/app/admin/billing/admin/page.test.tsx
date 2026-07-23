import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';

import { AdminBillingOperationsConsole } from '@/app/admin/operations/billing/AdminBillingOperationsConsole';
import { applyAdminBillingOpsState } from '@/components/billing/AdminBillingShared';
import type { AdminBillingSubscriptionItem } from '@/types/billing';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockEnvState = {
  billingEnabled: 'true',
  loginMethodsEnabled: ['phone'],
  defaultLoginMethod: 'phone',
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
    getBillingBootstrap: jest.fn(),
    getAdminBillingFocusTeachers: jest.fn(),
    getAdminBillingDailyLedgerSummary: jest.fn(),
    getAdminBillingEntitlements: jest.fn(),
    grantAdminBillingEntitlement: jest.fn(),
    getAdminBillingCustomizationDraft: jest.fn(),
    saveAdminBillingCustomizationDraft: jest.fn(),
    deleteAdminBillingCustomizationDraft: jest.fn(),
    getAdminBillingSubscriptions: jest.fn(),
    getAdminBillingOpsState: jest.fn(),
    updateAdminBillingConfigStatus: jest.fn(),
  },
}));

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => undefined;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => undefined;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => undefined;
}

const mockGetBillingBootstrap = api.getBillingBootstrap as jest.Mock;
const mockGetAdminBillingFocusTeachers =
  api.getAdminBillingFocusTeachers as jest.Mock;
const mockGetAdminBillingDailyLedgerSummary =
  api.getAdminBillingDailyLedgerSummary as jest.Mock;
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
const mockGetAdminBillingOpsState = api.getAdminBillingOpsState as jest.Mock;
const mockUpdateAdminBillingConfigStatus =
  api.updateAdminBillingConfigStatus as jest.Mock;

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('AdminBillingOperationsConsole', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    window.localStorage.clear();
    applyAdminBillingOpsState({ config_status: {} });
    mockBrowserTimeZone.mockReturnValue('America/Los_Angeles');
    mockEnvState.billingEnabled = 'true';
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockEnvState.defaultLoginMethod = 'phone';
    mockEnvState.runtimeConfigLoaded = true;
    mockGetBillingBootstrap.mockReset();
    mockGetAdminBillingFocusTeachers.mockReset();
    mockGetAdminBillingDailyLedgerSummary.mockReset();
    mockGetAdminBillingEntitlements.mockReset();
    mockGrantAdminBillingEntitlement.mockReset();
    mockGetAdminBillingCustomizationDraft.mockReset();
    mockSaveAdminBillingCustomizationDraft.mockReset();
    mockDeleteAdminBillingCustomizationDraft.mockReset();
    mockGetAdminBillingSubscriptions.mockReset();
    mockGetAdminBillingOpsState.mockReset();
    mockUpdateAdminBillingConfigStatus.mockReset();
    mockGetAdminBillingOpsState.mockResolvedValue({
      config_status: {},
    });
    mockUpdateAdminBillingConfigStatus.mockResolvedValue({});
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

  test('renders admin billing tabs and loads active billing operation sections', async () => {
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
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(mockGetAdminBillingSubscriptions).toHaveBeenCalledWith(
      {
        page_index: 1,
        page_size: 10,
        attention_only: true,
        creator_keyword: '',
        status: '',
      },
      { skipErrorToast: true },
    );
    expect(await screen.findByText('Teacher Two')).toBeInTheDocument();

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
  });

  test('searches subscription follow-up rows by creator keyword', async () => {
    const user = userEvent.setup();
    mockGetAdminBillingSubscriptions.mockImplementation(
      async ({ page_index, creator_keyword }) => ({
        items:
          creator_keyword === '13800138002'
            ? [
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
              ]
            : page_index === 2
              ? [
                  {
                    subscription_bid: 'sub-active',
                    creator_bid: 'creator-1',
                    creator_mobile: '13800138001',
                    creator_nickname: 'Teacher One',
                    product_bid: 'bill-product-plan-monthly',
                    product_code: 'creator-plan-monthly',
                    status: 'active',
                    billing_provider: 'stripe',
                    current_period_start_at: '2026-04-01T00:00:00Z',
                    current_period_end_at: '2026-05-01T00:00:00Z',
                    grace_period_end_at: null,
                    cancel_at_period_end: false,
                    next_product_bid: null,
                    next_product_code: '',
                    last_renewed_at: '2026-04-01T00:00:00Z',
                    last_failed_at: null,
                    wallet: {
                      available_credits: 12,
                      reserved_credits: 0,
                      lifetime_granted_credits: 20,
                      lifetime_consumed_credits: 8,
                    },
                    latest_renewal_event: null,
                    has_attention: false,
                  },
                ]
              : [
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
        page: creator_keyword === '13800138002' ? 1 : page_index,
        page_count: creator_keyword === '13800138002' ? 1 : 2,
        page_size: 10,
        total: creator_keyword === '13800138002' ? 1 : 2,
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

    expect(await screen.findByText('Teacher Two')).toBeInTheDocument();
    await user.click(
      screen.getByRole('link', {
        name: 'module.dashboard.pagination.next',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminBillingSubscriptions).toHaveBeenLastCalledWith(
        {
          page_index: 2,
          page_size: 10,
          attention_only: true,
          creator_keyword: '',
          status: '',
        },
        { skipErrorToast: true },
      );
    });

    await user.type(
      screen.getByPlaceholderText(
        'module.billing.admin.subscriptions.filters.searchPlaceholderPhone',
      ),
      '13800138002',
    );
    await user.click(
      screen.getByRole('button', {
        name: 'module.billing.admin.subscriptions.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminBillingSubscriptions).toHaveBeenLastCalledWith(
        {
          page_index: 1,
          page_size: 10,
          attention_only: true,
          creator_keyword: '13800138002',
          status: '',
        },
        { skipErrorToast: true },
      );
    });

    expect(
      screen.getByText('module.billing.admin.pagination.total'),
    ).toBeInTheDocument();
  });

  test('filters subscription follow-up rows by subscription status on query', async () => {
    const user = userEvent.setup();
    mockGetAdminBillingSubscriptions.mockImplementation(
      async ({ page_index, status }) => ({
        items:
          status === 'past_due'
            ? [
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
              ]
            : page_index === 2
              ? [
                  {
                    subscription_bid: 'sub-active',
                    creator_bid: 'creator-1',
                    creator_mobile: '13800138001',
                    creator_nickname: 'Teacher One',
                    product_bid: 'bill-product-plan-monthly',
                    product_code: 'creator-plan-monthly',
                    status: 'active',
                    billing_provider: 'stripe',
                    current_period_start_at: '2026-04-01T00:00:00Z',
                    current_period_end_at: '2026-05-01T00:00:00Z',
                    grace_period_end_at: null,
                    cancel_at_period_end: false,
                    next_product_bid: null,
                    next_product_code: '',
                    last_renewed_at: '2026-04-01T00:00:00Z',
                    last_failed_at: null,
                    wallet: {
                      available_credits: 12,
                      reserved_credits: 0,
                      lifetime_granted_credits: 20,
                      lifetime_consumed_credits: 8,
                    },
                    latest_renewal_event: null,
                    has_attention: false,
                  },
                ]
              : [
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
        page: status === 'past_due' ? 1 : page_index,
        page_count: status === 'past_due' ? 1 : 2,
        page_size: 10,
        total: status === 'past_due' ? 1 : 2,
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

    expect(await screen.findByText('Teacher Two')).toBeInTheDocument();
    await user.click(
      screen.getByRole('link', {
        name: 'module.dashboard.pagination.next',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminBillingSubscriptions).toHaveBeenLastCalledWith(
        {
          page_index: 2,
          page_size: 10,
          attention_only: true,
          creator_keyword: '',
          status: '',
        },
        { skipErrorToast: true },
      );
    });

    await user.click(
      screen.getByRole('combobox', {
        name: 'module.billing.admin.subscriptions.filters.status',
      }),
    );
    await user.click(
      screen.getAllByText('module.billing.status.pastDue').at(-1)!,
    );
    await user.click(
      screen.getByRole('button', {
        name: 'module.billing.admin.subscriptions.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminBillingSubscriptions).toHaveBeenLastCalledWith(
        {
          page_index: 1,
          page_size: 10,
          attention_only: true,
          creator_keyword: '',
          status: 'past_due',
        },
        { skipErrorToast: true },
      );
    });
  });

  test('keeps the requested subscriptions page while the next page is loading', async () => {
    const user = userEvent.setup();
    const secondPage = createDeferred<{
      items: Array<AdminBillingSubscriptionItem>;
      page: number;
      page_count: number;
      page_size: number;
      total: number;
    }>();

    mockGetAdminBillingSubscriptions.mockImplementation(({ page_index }) => {
      if (page_index === 2) {
        return secondPage.promise;
      }

      return Promise.resolve({
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
        page: page_index,
        page_count: 2,
        page_size: 10,
        total: 2,
      });
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

    expect(await screen.findByText('Teacher Two')).toBeInTheDocument();

    await user.click(
      screen.getByRole('link', {
        name: 'module.dashboard.pagination.next',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminBillingSubscriptions).toHaveBeenCalledWith(
        {
          page_index: 2,
          page_size: 10,
          attention_only: true,
          creator_keyword: '',
          status: '',
        },
        { skipErrorToast: true },
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(
      mockGetAdminBillingSubscriptions.mock.calls.filter(
        ([params]) => params.page_index === 1,
      ),
    ).toHaveLength(1);

    await act(async () => {
      secondPage.resolve({
        items: [
          {
            subscription_bid: 'sub-active',
            creator_bid: 'creator-1',
            creator_mobile: '13800138001',
            creator_nickname: 'Teacher One',
            product_bid: 'bill-product-plan-monthly',
            product_code: 'creator-plan-monthly',
            status: 'active',
            billing_provider: 'stripe',
            current_period_start_at: '2026-04-01T00:00:00Z',
            current_period_end_at: '2026-05-01T00:00:00Z',
            grace_period_end_at: null,
            cancel_at_period_end: false,
            next_product_bid: null,
            next_product_code: '',
            last_renewed_at: '2026-04-01T00:00:00Z',
            last_failed_at: null,
            wallet: {
              available_credits: 12,
              reserved_credits: 0,
              lifetime_granted_credits: 20,
              lifetime_consumed_credits: 8,
            },
            latest_renewal_event: null,
            has_attention: false,
          },
        ],
        page: 2,
        page_count: 2,
        page_size: 10,
        total: 2,
      });
      await secondPage.promise;
    });

    expect(await screen.findByText('Teacher One')).toBeInTheDocument();
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
        custom_payment_enabled: true,
      }),
    );
  });
});

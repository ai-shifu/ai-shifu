import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { BillingRecentActivitySection } from './BillingRecentActivitySection';

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
    getBillingLedger: jest.fn(),
    getBillingOrderDetail: jest.fn(),
    getBillingOrders: jest.fn(),
  },
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

const mockGetBillingLedger = api.getBillingLedger as jest.Mock;
const mockGetBillingOrderDetail = api.getBillingOrderDetail as jest.Mock;
const mockGetBillingOrders = api.getBillingOrders as jest.Mock;

function renderSection() {
  return render(
    <SWRConfig
      value={{
        provider: () => new Map(),
      }}
    >
      <BillingRecentActivitySection />
    </SWRConfig>,
  );
}

describe('BillingRecentActivitySection', () => {
  beforeEach(() => {
    mockGetBillingLedger.mockReset();
    mockGetBillingOrderDetail.mockReset();
    mockGetBillingOrders.mockReset();

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
      page_size: 4,
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
      page_size: 4,
      total: 1,
    });
    mockGetBillingOrderDetail.mockResolvedValue({
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
      failed_at: null,
      refunded_at: null,
      failure_code: '',
      metadata: {},
    });
  });

  test('loads recent ledger and orders summaries with compact page sizes', async () => {
    renderSection();

    await waitFor(() => {
      expect(mockGetBillingLedger).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 4,
      });
      expect(mockGetBillingOrders).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 4,
      });
    });

    expect(await screen.findByText('usage-1')).toBeInTheDocument();
    expect(
      await screen.findByText('module.billing.orders.type.subscriptionStart'),
    ).toBeInTheDocument();
  });

  test('opens usage and order detail sheets from the recent activity cards', async () => {
    const user = userEvent.setup();
    renderSection();

    expect(await screen.findByText('usage-1')).toBeInTheDocument();
    expect(
      await screen.findByText('module.billing.orders.type.subscriptionStart'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.ledger.table.detail',
        }),
      );
    });

    expect(
      screen.getByText('module.billing.ledger.detail.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.detail.usageBid'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.orders.table.order',
        }),
      );
    });

    await waitFor(() => {
      expect(mockGetBillingOrderDetail).toHaveBeenCalledWith({
        billing_order_bid: 'order-1',
      });
    });

    expect(
      screen.getByText('module.billing.orders.detail.title'),
    ).toBeInTheDocument();
  });
});

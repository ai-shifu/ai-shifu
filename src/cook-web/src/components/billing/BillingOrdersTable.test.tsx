import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import { openBillingPaymentWindow } from '@/lib/billing';

import { BillingOrdersTable } from './BillingOrdersTable';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (options?.status) {
        return `${key}:${options.status}`;
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
    checkoutBillingOrder: jest.fn(),
    getBillingOrderDetail: jest.fn(),
    getBillingOrders: jest.fn(),
    syncBillingOrder: jest.fn(),
  },
}));

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  toast: jest.fn(),
}));

jest.mock('@/lib/billing', () => {
  const actual = jest.requireActual('@/lib/billing');
  return {
    ...actual,
    openBillingPaymentWindow: jest.fn(),
  };
});

const mockCheckoutBillingOrder = api.checkoutBillingOrder as jest.Mock;
const mockGetBillingOrderDetail = api.getBillingOrderDetail as jest.Mock;
const mockGetBillingOrders = api.getBillingOrders as jest.Mock;
const mockSyncBillingOrder = api.syncBillingOrder as jest.Mock;
const mockOpenBillingPaymentWindow = openBillingPaymentWindow as jest.Mock;
const mockToast = toast as jest.Mock;

describe('BillingOrdersTable', () => {
  beforeEach(() => {
    mockCheckoutBillingOrder.mockReset();
    mockCheckoutBillingOrder.mockResolvedValue({
      billing_order_bid: 'order-2',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      payment_payload: {
        credential: {
          wx_pub_qr: 'https://pingxx.test/wechat-qr',
        },
      },
    });
    mockGetBillingOrderDetail.mockReset();
    mockGetBillingOrderDetail.mockResolvedValue({
      billing_order_bid: 'order-1',
      creator_bid: 'creator-1',
      product_bid: 'billing-product-plan-monthly',
      subscription_bid: 'sub-1',
      order_type: 'subscription_start',
      status: 'failed',
      payment_provider: 'stripe',
      payment_mode: 'subscription',
      payable_amount: 9900,
      paid_amount: 0,
      currency: 'CNY',
      provider_reference_id: 'cs_test_1',
      failure_message: 'declined',
      failure_code: 'card_declined',
      created_at: '2026-04-05T12:00:00Z',
      paid_at: null,
      failed_at: '2026-04-05T12:05:00Z',
      refunded_at: null,
      metadata: {
        event_type: 'checkout.session.completed',
      },
    });
    mockGetBillingOrders.mockResolvedValue({
      items: [
        {
          billing_order_bid: 'order-1',
          creator_bid: 'creator-1',
          product_bid: 'billing-product-plan-monthly',
          subscription_bid: 'sub-1',
          order_type: 'subscription_start',
          status: 'failed',
          payment_provider: 'stripe',
          payment_mode: 'subscription',
          payable_amount: 9900,
          paid_amount: 0,
          currency: 'CNY',
          provider_reference_id: 'cs_test_1',
          failure_message: 'declined',
          created_at: '2026-04-05T12:00:00Z',
          paid_at: null,
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });
    mockSyncBillingOrder.mockResolvedValue({
      billing_order_bid: 'order-1',
      status: 'paid',
    });
    mockOpenBillingPaymentWindow.mockReset();
    mockToast.mockReset();
  });

  test('renders creator billing orders, opens detail sheet, and supports manual sync', async () => {
    const user = userEvent.setup();

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <BillingOrdersTable />
      </SWRConfig>,
    );

    expect(await screen.findByText('order-1')).toBeInTheDocument();
    expect(mockGetBillingOrders).toHaveBeenCalledTimes(1);

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.orders.actions.sync',
        }),
      );
    });

    await waitFor(() => {
      expect(mockSyncBillingOrder).toHaveBeenCalledWith({
        billing_order_bid: 'order-1',
      });
    });

    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title:
          'module.billing.orders.syncSuccess:module.billing.orders.status.paid',
      }),
    );

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: /module\.billing\.orders\.type\.subscriptionStart/,
        }),
      );
    });

    await waitFor(() => {
      expect(mockGetBillingOrderDetail).toHaveBeenCalledWith({
        billing_order_bid: 'order-1',
      });
    });

    expect(
      await screen.findByText('module.billing.orders.detail.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('card_declined')).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === 'PRE' &&
          String(element.textContent || '').includes(
            'checkout.session.completed',
          ),
      ),
    ).toBeInTheDocument();
  });

  test('continues payment for pending Pingxx subscription orders', async () => {
    const user = userEvent.setup();
    mockGetBillingOrders.mockResolvedValue({
      items: [
        {
          billing_order_bid: 'order-2',
          creator_bid: 'creator-1',
          product_bid: 'billing-product-plan-monthly',
          subscription_bid: 'sub-2',
          order_type: 'subscription_renewal',
          status: 'pending',
          payment_provider: 'pingxx',
          payment_mode: 'subscription',
          payable_amount: 9900,
          paid_amount: 0,
          currency: 'CNY',
          provider_reference_id: '',
          failure_message: '',
          created_at: '2026-04-06T12:00:00Z',
          paid_at: null,
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <BillingOrdersTable />
      </SWRConfig>,
    );

    expect(await screen.findByText('order-2')).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.orders.actions.continuePayment',
        }),
      );
    });

    await waitFor(() => {
      expect(mockCheckoutBillingOrder).toHaveBeenCalledWith({
        billing_order_bid: 'order-2',
        channel: 'wx_pub_qr',
      });
    });

    expect(screen.getByTestId('billing-pingxx-qr-code')).toBeInTheDocument();
    expect(mockOpenBillingPaymentWindow).not.toHaveBeenCalled();

    mockCheckoutBillingOrder.mockResolvedValueOnce({
      billing_order_bid: 'order-2',
      provider: 'pingxx',
      payment_mode: 'subscription',
      status: 'pending',
      payment_payload: {
        credential: {
          alipay_qr: 'https://pingxx.test/alipay-qr',
        },
      },
    });

    await act(async () => {
      await user.click(screen.getByTestId('billing-pingxx-channel-alipay_qr'));
    });

    await waitFor(() => {
      expect(mockCheckoutBillingOrder).toHaveBeenLastCalledWith({
        billing_order_bid: 'order-2',
        channel: 'alipay_qr',
      });
    });
  });
});

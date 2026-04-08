import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { toast } from '@/hooks/useToast';

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
    getBillingOrders: jest.fn(),
    syncBillingOrder: jest.fn(),
  },
}));

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  toast: jest.fn(),
}));

const mockGetBillingOrders = api.getBillingOrders as jest.Mock;
const mockSyncBillingOrder = api.syncBillingOrder as jest.Mock;
const mockToast = toast as jest.Mock;

describe('BillingOrdersTable', () => {
  beforeEach(() => {
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
    mockToast.mockReset();
  });

  test('renders creator billing orders and supports manual sync', async () => {
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
  });
});

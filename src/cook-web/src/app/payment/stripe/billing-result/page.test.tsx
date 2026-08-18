import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import StripeBillingResultPage from './page';
import request from '@/lib/request';
import { consumeStripeCheckoutSession } from '@/lib/stripe-storage';

const mockPush = jest.fn();
const mockSearchParams = new URLSearchParams();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
  useSearchParams: () => ({
    get: (key: string) => mockSearchParams.get(key),
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: { seconds?: number }) => {
      if (params?.seconds !== undefined) {
        return `${key}:${params.seconds}`;
      }

      const labels: Record<string, string> = {
        'module.billing.result.errorTitle': 'Billing sync failed',
        'module.billing.result.missingOrder': 'Missing billing order',
        'module.billing.result.openBilling': 'Open billing center',
        'module.billing.result.pending': 'Payment is still processing',
        'module.billing.result.pendingTitle':
          'Waiting for billing confirmation',
        'module.billing.result.processing': 'Syncing payment status',
        'module.billing.result.retry': 'Retry sync',
        'module.billing.result.success': 'Payment confirmed',
        'module.billing.result.successTitle': 'Billing updated',
      };

      return labels[key] || key;
    },
  }),
}));

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    post: jest.fn(),
  },
}));

jest.mock('@/lib/stripe-storage', () => ({
  consumeStripeCheckoutSession: jest.fn(),
}));

const mockRequestPost = request.post as jest.Mock;
const mockConsumeStripeCheckoutSession =
  consumeStripeCheckoutSession as jest.Mock;

describe('StripeBillingResultPage', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockRequestPost.mockReset();
    mockConsumeStripeCheckoutSession.mockReset();
    mockSearchParams.forEach((_, key) => mockSearchParams.delete(key));
    jest.useRealTimers();
  });

  test('syncs the billing order and redirects to billing center on success', async () => {
    jest.useFakeTimers();
    mockSearchParams.set('bill_order_bid', 'bill-order-1');
    mockSearchParams.set('session_id', 'sess-1');
    mockRequestPost.mockResolvedValue({ status: 'paid' });

    render(<StripeBillingResultPage />);

    await waitFor(() => {
      expect(mockRequestPost).toHaveBeenCalledWith(
        '/api/billing/orders/bill-order-1/sync',
        {
          session_id: 'sess-1',
        },
      );
    });

    expect(await screen.findByText('Billing updated')).toBeInTheDocument();
    expect(
      await screen.findByText('module.billing.result.countdown:3'),
    ).toBeInTheDocument();

    await act(async () => {
      jest.advanceTimersByTime(3000);
    });

    expect(mockPush).toHaveBeenCalledWith('/admin/billing');
  });

  test('shows an error when no billing order can be recovered', async () => {
    mockConsumeStripeCheckoutSession.mockReturnValue(null);

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByText('Missing billing order'),
    ).toBeInTheDocument();
  });

  test('allows retry when sync returns pending', async () => {
    mockSearchParams.set('bill_order_bid', 'bill-order-2');
    mockRequestPost.mockResolvedValue({ status: 'pending' });

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByText('Waiting for billing confirmation'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry sync' }));

    await waitFor(() => {
      expect(mockRequestPost).toHaveBeenCalledTimes(2);
    });
  });
});

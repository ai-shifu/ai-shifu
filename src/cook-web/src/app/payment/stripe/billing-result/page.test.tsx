import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import StripeBillingResultPage from './page';
import api from '@/api';
import { buildBillingSwrKey } from '@/lib/billing';
import request from '@/lib/request';
import { consumeStripeCheckoutSession } from '@/lib/stripe-storage';

const mockPush = jest.fn();
const mockSearchParams = new URLSearchParams();
const mockMutateSWRCache = jest.fn(
  async (...args: [unknown, unknown?, unknown?]) => {
    const [, fetcher] = args;
    if (typeof fetcher === 'function') {
      return (fetcher as () => Promise<unknown>)();
    }
    return fetcher;
  },
);

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

jest.mock('swr', () => ({
  mutate: (key: unknown, fetcher?: unknown, options?: unknown) =>
    mockMutateSWRCache(key, fetcher, options),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getBillingOverview: jest.fn(),
    getBillingWalletBuckets: jest.fn(),
    getBillingLedger: jest.fn(),
  },
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
const mockGetBillingOverview = api.getBillingOverview as jest.Mock;
const mockGetBillingWalletBuckets = api.getBillingWalletBuckets as jest.Mock;
const mockGetBillingLedger = api.getBillingLedger as jest.Mock;
const mockConsumeStripeCheckoutSession =
  consumeStripeCheckoutSession as jest.Mock;

describe('StripeBillingResultPage', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockRequestPost.mockReset();
    mockMutateSWRCache.mockClear();
    mockGetBillingOverview.mockReset();
    mockGetBillingWalletBuckets.mockReset();
    mockGetBillingLedger.mockReset();
    mockConsumeStripeCheckoutSession.mockReset();
    mockGetBillingOverview.mockResolvedValue({});
    mockGetBillingWalletBuckets.mockResolvedValue({});
    mockGetBillingLedger.mockResolvedValue({ items: [] });
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
    expect(await screen.findByText('Payment confirmed')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockMutateSWRCache).toHaveBeenCalledTimes(3);
    });
    expect(mockMutateSWRCache).toHaveBeenCalledWith(
      buildBillingSwrKey('creator-billing-overview'),
      expect.any(Function),
      { revalidate: false },
    );
    expect(mockMutateSWRCache).toHaveBeenCalledWith(
      buildBillingSwrKey('billing-wallet-buckets'),
      expect.any(Function),
      { revalidate: false },
    );
    expect(mockMutateSWRCache).toHaveBeenCalledWith(
      buildBillingSwrKey('billing-ledger-recent', 1, 20),
      expect.any(Function),
      { revalidate: false },
    );
    expect(mockGetBillingOverview).toHaveBeenCalledWith(
      {},
      { skipErrorToast: true },
    );
    expect(mockGetBillingWalletBuckets).toHaveBeenCalledWith(
      {},
      { skipErrorToast: true },
    );
    expect(mockGetBillingLedger).toHaveBeenCalledWith(
      { page_index: 1, page_size: 20 },
      { skipErrorToast: true },
    );
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
    expect(
      await screen.findByText('Payment is still processing'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry sync' }));

    await waitFor(() => {
      expect(mockRequestPost).toHaveBeenCalledTimes(2);
    });
  });

  test.each(['failed', 'canceled', 'timeout', 'refunded', 'unknown'])(
    'does not show success when sync returns %s',
    async status => {
      jest.useFakeTimers();
      mockSearchParams.set('bill_order_bid', `bill-order-${status}`);
      mockSearchParams.set('session_id', `sess-${status}`);
      mockRequestPost.mockResolvedValue({ status });

      render(<StripeBillingResultPage />);

      expect(
        await screen.findByRole('heading', { name: 'Billing sync failed' }),
      ).toBeInTheDocument();
      expect(screen.queryByText('Billing updated')).not.toBeInTheDocument();
      expect(screen.queryByText('Payment confirmed')).not.toBeInTheDocument();
      expect(mockMutateSWRCache).not.toHaveBeenCalled();

      await act(async () => {
        jest.advanceTimersByTime(3000);
      });

      expect(mockPush).not.toHaveBeenCalled();
    },
  );
});

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
const mockTrackEvent = jest.fn();
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

// next/navigation memoizes both hooks, so their return values keep a stable
// identity across renders. Returning a fresh object per render makes every
// effect that depends on them re-run on every render.
const mockRouter = { push: mockPush };
const mockReadonlySearchParams = {
  get: (key: string) => mockSearchParams.get(key),
};

jest.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockReadonlySearchParams,
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
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
    mockTrackEvent.mockReset();
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
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_result',
      {
        payment_provider: 'stripe',
        source_surface: 'stripe_return',
        bill_order_bid: 'bill-order-1',
        outcome: 'success',
      },
    );
    const resultPayload = mockTrackEvent.mock.calls[0]?.[1];
    expect(resultPayload).not.toHaveProperty('session_id');
    expect(resultPayload).not.toHaveProperty('redirect_url');
    expect(resultPayload).not.toHaveProperty('raw_error');
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
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_result',
      {
        payment_provider: 'stripe',
        source_surface: 'stripe_return',
        outcome: 'failed',
        failure_category: 'missing_order',
      },
    );
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
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_status',
      {
        payment_provider: 'stripe',
        source_surface: 'stripe_return',
        bill_order_bid: 'bill-order-2',
        status: 'pending',
      },
    );
  });

  test('records a cancelled Stripe return after preserving order sync', async () => {
    mockSearchParams.set('bill_order_bid', 'private-person@example.test');
    mockSearchParams.set('session_id', 'sess-secret');
    mockSearchParams.set('canceled', '1');
    mockRequestPost.mockResolvedValue({ status: 'canceled' });

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByRole('heading', { name: 'Billing sync failed' }),
    ).toBeInTheDocument();
    expect(mockRequestPost).toHaveBeenCalledWith(
      '/api/billing/orders/private-person@example.test/sync',
      { session_id: 'sess-secret' },
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_result',
      {
        payment_provider: 'stripe',
        source_surface: 'stripe_return',
        outcome: 'cancelled',
      },
    );
    expect(mockTrackEvent.mock.calls[0]?.[1]).not.toHaveProperty('session_id');
    expect(mockTrackEvent.mock.calls[0]?.[1]).not.toHaveProperty('canceled');
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-person@example.test',
    );
  });

  test('records a cancelled result without changing pending return behavior', async () => {
    mockSearchParams.set('bill_order_bid', 'private-person@example.test');
    mockSearchParams.set('session_id', 'sess-secret');
    mockSearchParams.set('canceled', '1');
    mockRequestPost.mockResolvedValue({ status: 'pending' });

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByText('Waiting for billing confirmation'),
    ).toBeInTheDocument();
    expect(
      await screen.findByText('Payment is still processing'),
    ).toBeInTheDocument();
    expect(mockRequestPost).toHaveBeenCalledWith(
      '/api/billing/orders/private-person@example.test/sync',
      { session_id: 'sess-secret' },
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_result',
      {
        payment_provider: 'stripe',
        source_surface: 'stripe_return',
        outcome: 'cancelled',
      },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-person@example.test',
    );
  });

  test('keeps a sync failure non-terminal and reports one result after retry', async () => {
    mockSearchParams.set('bill_order_bid', 'bill-order-rejected');
    mockRequestPost
      .mockRejectedValueOnce(
        new Error('customer person@example.test could not be synced'),
      )
      .mockResolvedValueOnce({ status: 'paid' });

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByRole('heading', { name: 'Billing sync failed' }),
    ).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_status',
      {
        payment_provider: 'stripe',
        source_surface: 'stripe_return',
        status: 'confirmation_failed',
      },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'person@example.test',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Retry sync' }));

    expect(await screen.findByText('Billing updated')).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_result',
      expect.objectContaining({
        bill_order_bid: 'bill-order-rejected',
        outcome: 'success',
      }),
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'creator_billing_checkout_result',
      ),
    ).toHaveLength(1);
  });

  test('omits an unconfirmed query order from sync-failure analytics', async () => {
    mockSearchParams.set('bill_order_bid', 'private-person@example.test');
    mockRequestPost.mockRejectedValue(new Error('private provider response'));

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByRole('heading', { name: 'Billing sync failed' }),
    ).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_status',
      {
        payment_provider: 'stripe',
        source_surface: 'stripe_return',
        status: 'confirmation_failed',
      },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private-person@example.test',
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private provider response',
    );
  });

  test('keeps a paid return successful when tracking throws', async () => {
    mockSearchParams.set('bill_order_bid', 'bill-order-fail-open');
    mockRequestPost.mockResolvedValue({ status: 'paid' });
    mockTrackEvent.mockImplementation(() => {
      throw new Error('tracking unavailable');
    });

    render(<StripeBillingResultPage />);

    expect(await screen.findByText('Billing updated')).toBeInTheDocument();
    expect(await screen.findByText('Payment confirmed')).toBeInTheDocument();
  });

  test('reports refunded as a terminal failure', async () => {
    mockSearchParams.set('bill_order_bid', 'bill-order-refunded');
    mockSearchParams.set('session_id', 'sess-refunded');
    mockRequestPost.mockResolvedValue({ status: 'refunded' });

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByRole('heading', { name: 'Billing sync failed' }),
    ).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_result',
      expect.objectContaining({
        bill_order_bid: 'bill-order-refunded',
        outcome: 'failed',
        failure_category: 'payment_failed',
      }),
    );
  });

  test.each(['failed', 'canceled', 'timeout', 'unknown'])(
    'keeps the recoverable %s state non-terminal',
    async status => {
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
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_billing_checkout_status',
        {
          payment_provider: 'stripe',
          source_surface: 'stripe_return',
          bill_order_bid: `bill-order-${status}`,
          status: 'confirmation_failed',
        },
      );
      expect(
        mockTrackEvent.mock.calls.filter(
          ([eventName]) => eventName === 'creator_billing_checkout_result',
        ),
      ).toHaveLength(0);
      expect(
        screen.getByRole('button', { name: 'Retry sync' }),
      ).toBeInTheDocument();
      expect(mockPush).not.toHaveBeenCalled();
    },
  );

  test('reports one terminal success when a recoverable provider state becomes paid', async () => {
    mockSearchParams.set('bill_order_bid', 'bill-order-recovered');
    mockRequestPost
      .mockResolvedValueOnce({ status: 'failed' })
      .mockResolvedValueOnce({ status: 'paid' });

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByRole('heading', { name: 'Billing sync failed' }),
    ).toBeInTheDocument();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_checkout_status',
      expect.objectContaining({
        bill_order_bid: 'bill-order-recovered',
        status: 'confirmation_failed',
      }),
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'creator_billing_checkout_result',
      ),
    ).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'Retry sync' }));

    expect(await screen.findByText('Billing updated')).toBeInTheDocument();
    const terminalResults = mockTrackEvent.mock.calls.filter(
      ([eventName]) => eventName === 'creator_billing_checkout_result',
    );
    expect(terminalResults).toHaveLength(1);
    expect(terminalResults[0]?.[1]).toEqual(
      expect.objectContaining({
        bill_order_bid: 'bill-order-recovered',
        outcome: 'success',
      }),
    );
  });
});

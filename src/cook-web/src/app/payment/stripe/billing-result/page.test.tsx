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
  async (_key: unknown, fetcher?: unknown, _options?: unknown) => {
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
    t: (key: string, params?: { seconds?: number }) =>
      params?.seconds !== undefined ? `${key}:${params.seconds}` : key,
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

    expect(
      await screen.findByText('module.billing.result.successTitle'),
    ).toBeInTheDocument();
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
      await screen.findByText('module.billing.result.missingOrder'),
    ).toBeInTheDocument();
  });

  test('allows retry when sync returns pending', async () => {
    mockSearchParams.set('bill_order_bid', 'bill-order-2');
    mockRequestPost.mockResolvedValue({ status: 'pending' });

    render(<StripeBillingResultPage />);

    expect(
      await screen.findByText('module.billing.result.pendingTitle'),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'module.billing.result.retry' }),
    );

    await waitFor(() => {
      expect(mockRequestPost).toHaveBeenCalledTimes(2);
    });
  });
});

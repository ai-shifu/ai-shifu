import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { useBillingOverview } from '@/hooks/useBillingOverview';

import AdminBillingPage from './page';

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
    getBillingCatalog: jest.fn(),
    getBillingWalletBuckets: jest.fn(),
  },
}));

jest.mock('@/hooks/useBillingOverview', () => ({
  __esModule: true,
  useBillingOverview: jest.fn(),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      paymentChannels: string[];
      runtimeConfigLoaded: boolean;
      stripeEnabled: string;
    }) => unknown,
  ) =>
    selector({
      paymentChannels: ['stripe', 'pingxx'],
      runtimeConfigLoaded: true,
      stripeEnabled: 'true',
    }),
}));

const mockGetBillingCatalog = api.getBillingCatalog as jest.Mock;
const mockGetBillingWalletBuckets = api.getBillingWalletBuckets as jest.Mock;
const mockUseBillingOverview = useBillingOverview as jest.Mock;

describe('AdminBillingPage', () => {
  beforeEach(() => {
    mockGetBillingCatalog.mockResolvedValue({
      plans: [],
      topups: [],
    });
    mockGetBillingWalletBuckets.mockResolvedValue([
      {
        wallet_bucket_bid: 'bucket-free',
        category: 'free',
        source_type: 'gift',
        source_bid: 'grant-1',
        available_credits: 80,
        effective_from: '2026-03-01T00:00:00Z',
        effective_to: '2026-05-01T00:00:00Z',
        priority: 10,
        status: 'active',
      },
    ]);
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 120.5,
          reserved_credits: 0,
          lifetime_granted_credits: 500,
          lifetime_consumed_credits: 379.5,
        },
        subscription: null,
        billing_alerts: [],
      },
      error: undefined,
      isLoading: false,
    });
  });

  test('renders the three billing center tabs and switches content', async () => {
    const user = userEvent.setup();

    render(
      <SWRConfig
        value={{
          provider: () => new Map(),
        }}
      >
        <AdminBillingPage />
      </SWRConfig>,
    );

    expect(screen.getByTestId('admin-billing-page')).toBeInTheDocument();
    expect(screen.getByText('module.billing.page.title')).toBeInTheDocument();
    expect(
      screen.getByRole('tab', { name: 'module.billing.page.tabs.plans' }),
    ).toHaveAttribute('data-state', 'active');
    expect(
      screen.getByText('module.billing.overview.walletTitle'),
    ).toBeInTheDocument();
    expect(mockGetBillingWalletBuckets).not.toHaveBeenCalled();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', { name: 'module.billing.page.tabs.ledger' }),
      );
    });

    expect(screen.getByText('module.billing.ledger.title')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.entriesTitle'),
    ).toBeInTheDocument();
    expect(await screen.findByText('grant-1')).toBeInTheDocument();
    expect(mockGetBillingWalletBuckets).toHaveBeenCalledTimes(1);

    await act(async () => {
      await user.click(
        screen.getByRole('tab', { name: 'module.billing.page.tabs.orders' }),
      );
    });

    expect(screen.getByText('module.billing.orders.title')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.orders.description'),
    ).toBeInTheDocument();
  });
});

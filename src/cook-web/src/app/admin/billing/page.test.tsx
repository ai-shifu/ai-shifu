import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
const mockUseBillingOverview = useBillingOverview as jest.Mock;

describe('AdminBillingPage', () => {
  beforeEach(() => {
    mockGetBillingCatalog.mockResolvedValue({
      plans: [],
      topups: [],
    });
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

    render(<AdminBillingPage />);

    expect(screen.getByTestId('admin-billing-page')).toBeInTheDocument();
    expect(screen.getByText('module.billing.page.title')).toBeInTheDocument();
    expect(
      screen.getByRole('tab', { name: 'module.billing.page.tabs.plans' }),
    ).toHaveAttribute('data-state', 'active');
    expect(
      screen.getByText('module.billing.overview.walletTitle'),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole('tab', { name: 'module.billing.page.tabs.ledger' }),
      );
    });

    expect(screen.getByText('module.billing.ledger.title')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.ledger.description'),
    ).toBeInTheDocument();

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

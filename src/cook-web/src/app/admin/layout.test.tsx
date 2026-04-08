import React from 'react';
import { render, screen } from '@testing-library/react';

import MainInterface from './layout';
import { useBillingOverview } from '@/hooks/useBillingOverview';

jest.mock('next/image', () => {
  const MockImage = () => <span data-testid='mock-next-image' />;
  MockImage.displayName = 'MockImage';
  return MockImage;
});

jest.mock('next/navigation', () => ({
  usePathname: () => '/admin',
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
  useEnvStore: (selector: (state: { logoWideUrl: string }) => unknown) =>
    selector({
      logoWideUrl: '',
    }),
}));

jest.mock('@/app/c/[[...id]]/Components/NavDrawer/NavFooter', () => {
  return React.forwardRef(function MockNavFooter(_props: unknown, ref: any) {
    return (
      <div
        ref={ref}
        data-testid='mock-admin-nav-footer'
      />
    );
  });
});

jest.mock('@/app/c/[[...id]]/Components/NavDrawer/MainMenuModal', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/hooks/useBillingOverview', () => ({
  __esModule: true,
  useBillingOverview: jest.fn(),
}));

const mockUseBillingOverview = useBillingOverview as jest.Mock;

describe('Admin layout sidebar', () => {
  beforeEach(() => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        creator_bid: 'creator-1',
        wallet: {
          available_credits: 12500,
          reserved_credits: 0,
          lifetime_granted_credits: 20000,
          lifetime_consumed_credits: 7500,
        },
        subscription: {
          subscription_bid: 'sub-1',
          product_bid: 'plan-1',
          product_code: 'creator-plan-monthly',
          status: 'active',
          billing_provider: 'stripe',
          current_period_start_at: '2026-04-01T00:00:00Z',
          current_period_end_at: '2026-05-01T00:00:00Z',
          grace_period_end_at: null,
          cancel_at_period_end: false,
          next_product_bid: null,
          last_renewed_at: null,
          last_failed_at: null,
        },
        billing_alerts: [],
      },
      error: undefined,
      isLoading: false,
    });
  });

  test('renders the billing navigation entry and membership card', () => {
    render(
      <MainInterface>
        <div data-testid='child-content' />
      </MainInterface>,
    );

    expect(
      screen.getByTestId('admin-billing-sidebar-card'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.sidebar.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.sidebar.totalCreditsLabel'),
    ).toBeInTheDocument();
    expect(screen.getByText('12,500')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.sidebar.subscriptionStatusLabel'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.status.active'),
    ).toBeInTheDocument();

    const billingNavLink = screen.getByTestId('admin-nav-billing');
    expect(billingNavLink).toHaveAttribute('href', '/admin/billing');
    expect(billingNavLink).toHaveTextContent('module.billing.navTitle');

    expect(
      screen.getByRole('link', {
        name: 'module.billing.sidebar.cta',
      }),
    ).toHaveAttribute('href', '/admin/billing');
  });
});

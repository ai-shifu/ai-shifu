import React from 'react';
import { render, screen } from '@testing-library/react';

import MainInterface from './layout';

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

describe('Admin layout sidebar', () => {
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
    expect(
      screen.getByText('module.billing.sidebar.subscriptionStatusLabel'),
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

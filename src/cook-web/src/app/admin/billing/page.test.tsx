import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import AdminBillingPage from './page';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('AdminBillingPage', () => {
  test('renders the three billing center tabs and switches content', async () => {
    const user = userEvent.setup();

    render(<AdminBillingPage />);

    expect(screen.getByTestId('admin-billing-page')).toBeInTheDocument();
    expect(screen.getByText('module.billing.page.title')).toBeInTheDocument();
    expect(
      screen.getByRole('tab', { name: 'module.billing.page.tabs.plans' }),
    ).toHaveAttribute('data-state', 'active');
    expect(
      screen.getByText('module.billing.overview.subscriptionTitle'),
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

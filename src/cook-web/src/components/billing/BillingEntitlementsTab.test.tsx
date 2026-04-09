import React from 'react';
import { render, screen } from '@testing-library/react';
import { SWRConfig } from 'swr';
import api from '@/api';
import { BillingEntitlementsTab } from './BillingEntitlementsTab';

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
    getBillingEntitlements: jest.fn(),
  },
}));

const mockGetBillingEntitlements = api.getBillingEntitlements as jest.Mock;

function renderComponent() {
  return render(
    <SWRConfig
      value={{
        provider: () => new Map(),
      }}
    >
      <BillingEntitlementsTab />
    </SWRConfig>,
  );
}

describe('BillingEntitlementsTab', () => {
  beforeEach(() => {
    mockGetBillingEntitlements.mockReset();
    mockGetBillingEntitlements.mockResolvedValue({
      branding_enabled: true,
      custom_domain_enabled: true,
      priority_class: 'priority',
      max_concurrency: 3,
      analytics_tier: 'advanced',
      support_tier: 'business_hours',
    });
  });

  test('renders the entitlement metrics and feature flags', async () => {
    renderComponent();

    expect(
      screen.getByText('module.billing.entitlements.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.entitlements.runtimeNote'),
    ).toBeInTheDocument();
    expect(
      await screen.findByText('module.billing.entitlements.priority.priority'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.entitlements.analytics.advanced'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.entitlements.support.businessHours'),
    ).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.billing.entitlements.flags.enabled').length,
    ).toBeGreaterThanOrEqual(2);
  });
});

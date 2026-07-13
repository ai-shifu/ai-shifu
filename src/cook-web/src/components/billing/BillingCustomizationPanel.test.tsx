import { render, screen } from '@testing-library/react';
import { BillingCustomizationPanel } from './BillingCustomizationPanel';
import { useBillingCustomization } from '@/hooks/useBillingData';

jest.mock('@/hooks/useBillingData', () => ({
  useBillingCustomization: jest.fn(),
}));
jest.mock('@/api', () => ({}));
jest.mock('@/lib/file', () => ({ uploadFile: jest.fn() }));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const mockUseBillingCustomization = useBillingCustomization as jest.Mock;

test('renders entitlement locks and never renders stored secrets', () => {
  mockUseBillingCustomization.mockReturnValue({
    isLoading: false,
    mutate: jest.fn(),
    data: {
      enabled: true,
      creator_bid: 'creator-1',
      capabilities: {
        branding: true,
        custom_domain: false,
        custom_wechat: true,
        custom_payment: true,
      },
      branding: { logo_wide_url: '', logo_square_url: '' },
      domains: { custom_domain_enabled: false, items: [] },
      integrations: [
        {
          provider: 'stripe',
          status: 'verified',
          public_config: { publishable_key: 'pk_owner' },
          secret_configured: true,
          callback_url: 'https://api.example.com/callback-token',
        },
      ],
    },
  });

  render(<BillingCustomizationPanel />);

  expect(screen.getByTestId('billing-customization-panel')).toBeInTheDocument();
  expect(
    screen.getByText('module.billing.customization.locked'),
  ).toBeInTheDocument();
  expect(screen.getByDisplayValue('pk_owner')).toBeInTheDocument();
  expect(screen.queryByDisplayValue(/secret/i)).not.toBeInTheDocument();
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BillingCustomizationPanel } from './BillingCustomizationPanel';
import { useBillingCustomization } from '@/hooks/useBillingData';

jest.mock('@/hooks/useBillingData', () => ({
  useBillingCustomization: jest.fn(),
}));
const mockUploadFile = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    updateBillingBranding: jest.fn(),
  },
}));
jest.mock('@/lib/file', () => ({
  uploadFile: (...args: unknown[]) => mockUploadFile(...args),
}));
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

test('uploads logos through the managed branding OSS endpoint', async () => {
  mockUploadFile.mockResolvedValue({
    ok: true,
    json: async () => ({
      code: 0,
      data: 'https://courses-oss.example.com/creator-branding/wide.png',
    }),
  });
  mockUseBillingCustomization.mockReturnValue({
    isLoading: false,
    mutate: jest.fn(),
    data: {
      enabled: true,
      creator_bid: 'creator-1',
      capabilities: {
        branding: true,
        custom_domain: false,
        custom_wechat: false,
        custom_payment: false,
      },
      branding: { logo_wide_url: '', logo_square_url: '' },
      domains: { custom_domain_enabled: false, items: [] },
      integrations: [],
    },
  });

  render(<BillingCustomizationPanel />);
  const file = new File(['png'], 'wide.png', { type: 'image/png' });
  fireEvent.change(
    screen.getByLabelText('module.billing.customization.branding.uploadWide'),
    { target: { files: [file] } },
  );

  await waitFor(() =>
    expect(mockUploadFile).toHaveBeenCalledWith(
      file,
      '/api/billing/customization/branding/logo',
    ),
  );
  expect(
    await screen.findByDisplayValue(
      'https://courses-oss.example.com/creator-branding/wide.png',
    ),
  ).toBeInTheDocument();
});

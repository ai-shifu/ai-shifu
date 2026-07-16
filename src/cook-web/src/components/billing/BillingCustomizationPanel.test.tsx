import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { BillingCustomizationPanel } from './BillingCustomizationPanel';

const mockMutateCache = jest.fn();
const mockUseSWR = jest.fn();
const mockUploadFile = jest.fn();

jest.mock('swr', () => {
  const actual = jest.requireActual('swr');
  return {
    __esModule: true,
    ...actual,
    default: (...args: unknown[]) => mockUseSWR(...args),
    useSWRConfig: () => ({
      mutate: mockMutateCache,
    }),
  };
});

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getBillingCustomization: jest.fn(),
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

const mockGetBillingCustomization = api.getBillingCustomization as jest.Mock;

function buildCustomizationData(overrides: Record<string, unknown> = {}) {
  return {
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
        provider: 'alipay',
        status: 'verified',
        public_config: { app_id: 'alipay_owner_app' },
        secret_configured: true,
        callback_url: 'https://api.example.com/alipay-callback-token',
      },
      {
        provider: 'stripe',
        status: 'verified',
        public_config: { publishable_key: 'pk_owner' },
        secret_configured: true,
        callback_url: 'https://api.example.com/callback-token',
      },
    ],
    ...overrides,
  };
}

describe('BillingCustomizationPanel', () => {
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  const OriginalImage = global.Image;

  beforeEach(() => {
    mockUseSWR.mockReset();
    mockMutateCache.mockReset();
    mockUploadFile.mockReset();
    mockGetBillingCustomization.mockReset();

    mockUseSWR.mockReturnValue({
      data: buildCustomizationData(),
      isLoading: false,
      mutate: jest.fn(),
    });
    mockGetBillingCustomization.mockResolvedValue(buildCustomizationData());

    URL.createObjectURL = jest.fn(() => 'blob:logo-preview');
    URL.revokeObjectURL = jest.fn();

    class MockImage {
      onload: null | (() => void) = null;
      onerror: null | (() => void) = null;
      naturalWidth = 220;
      naturalHeight = 32;

      set src(_value: string) {
        Promise.resolve().then(() => this.onload?.());
      }
    }

    global.Image = MockImage as unknown as typeof Image;
  });

  afterAll(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    global.Image = OriginalImage;
  });

  test('renders entitlement locks and never renders stored secrets', () => {
    mockUseSWR.mockReturnValue({
      data: buildCustomizationData({
        capabilities: {
          branding: true,
          custom_domain: false,
          custom_wechat: true,
          custom_payment: true,
        },
      }),
      isLoading: false,
      mutate: jest.fn(),
    });

    render(<BillingCustomizationPanel />);

    expect(
      screen.getByTestId('billing-customization-panel'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.customization.locked'),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue('alipay_owner_app')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('pk_owner')).not.toBeInTheDocument();
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

    render(<BillingCustomizationPanel />);

    const file = new File(['png'], 'wide.png', { type: 'image/png' });
    const uploadInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement | null;
    expect(uploadInput).not.toBeNull();
    fireEvent.change(uploadInput as HTMLInputElement, {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(mockUploadFile).toHaveBeenCalledWith(
        file,
        '/api/billing/customization/branding/logo',
        { target: 'wide' },
      ),
    );

    expect(
      await screen.findByDisplayValue(
        'https://courses-oss.example.com/creator-branding/wide.png',
      ),
    ).toBeInTheDocument();
  });
});

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
    saveBillingIntegration: jest.fn(),
    updateBillingBranding: jest.fn(),
    verifyBillingIntegration: jest.fn(),
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
const mockSaveBillingIntegration = api.saveBillingIntegration as jest.Mock;
const mockVerifyBillingIntegration = api.verifyBillingIntegration as jest.Mock;

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
    mockSaveBillingIntegration.mockReset();
    mockVerifyBillingIntegration.mockReset();
    mockSaveBillingIntegration.mockResolvedValue({
      integration_bid: 'integration-1',
    });
    mockVerifyBillingIntegration.mockResolvedValue({ status: 'verified' });

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

  test('does not preselect a payment provider when no payment integration exists', () => {
    mockUseSWR.mockReturnValue({
      data: buildCustomizationData({
        integrations: [
          {
            provider: 'alipay',
            status: 'unconfigured',
            public_config: {},
            secret_configured: false,
            callback_url: '',
          },
          {
            provider: 'wechatpay',
            status: 'unconfigured',
            public_config: {},
            secret_configured: false,
            callback_url: '',
          },
        ],
      }),
      isLoading: false,
      mutate: jest.fn(),
    });

    render(<BillingCustomizationPanel />);

    expect(screen.queryByText('app_private_key')).not.toBeInTheDocument();
    expect(screen.queryByText('api_v3_key')).not.toBeInTheDocument();
  });

  test('saves payment settings without auto-verifying them', async () => {
    mockUseSWR.mockReturnValue({
      data: buildCustomizationData({
        integrations: [
          {
            provider: 'wechatpay',
            status: 'draft',
            public_config: { app_id: 'wx_old' },
            secret_configured: false,
            callback_url: '',
          },
        ],
      }),
      isLoading: false,
      mutate: jest.fn(),
    });

    render(<BillingCustomizationPanel />);

    fireEvent.change(screen.getByDisplayValue('wx_old'), {
      target: { value: 'wx_new' },
    });
    fireEvent.click(
      screen.getByText('module.billing.customization.actions.saveIntegration'),
    );

    await waitFor(() => expect(mockSaveBillingIntegration).toHaveBeenCalled());
    expect(mockSaveBillingIntegration).toHaveBeenCalledWith({
      provider: 'wechatpay',
      public_config: { app_id: 'wx_new' },
      secret_config: {},
    });
    expect(mockVerifyBillingIntegration).not.toHaveBeenCalled();
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

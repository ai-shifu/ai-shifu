import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import api from '@/api';
import { toast } from '@/hooks/useToast';
import { BillingDomainsTab } from './BillingDomainsTab';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/lib/browser-timezone', () => ({
  __esModule: true,
  getBrowserTimeZone: () => 'Asia/Shanghai',
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getBillingEntitlements: jest.fn(),
    getAdminBillingDomainBindings: jest.fn(),
    bindAdminBillingDomain: jest.fn(),
  },
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      logoWideUrl: string;
      logoSquareUrl: string;
      faviconUrl: string;
      homeUrl: string;
    }) => unknown,
  ) =>
    selector({
      logoWideUrl: 'https://cdn.example.com/logo-wide.png',
      logoSquareUrl: 'https://cdn.example.com/logo-square.png',
      faviconUrl: 'https://cdn.example.com/favicon.ico',
      homeUrl: 'https://creator.example.com',
    }),
}));

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  toast: jest.fn(),
}));

const mockGetBillingEntitlements = api.getBillingEntitlements as jest.Mock;
const mockGetAdminBillingDomainBindings =
  api.getAdminBillingDomainBindings as jest.Mock;
const mockBindAdminBillingDomain = api.bindAdminBillingDomain as jest.Mock;
const mockToast = toast as jest.Mock;

function renderComponent() {
  return render(
    <SWRConfig
      value={{
        provider: () => new Map(),
      }}
    >
      <BillingDomainsTab />
    </SWRConfig>,
  );
}

describe('BillingDomainsTab', () => {
  beforeEach(() => {
    mockGetBillingEntitlements.mockReset();
    mockGetAdminBillingDomainBindings.mockReset();
    mockBindAdminBillingDomain.mockReset();
    mockToast.mockReset();

    mockGetBillingEntitlements.mockResolvedValue({
      branding_enabled: true,
      custom_domain_enabled: true,
      priority_class: 'priority',
      max_concurrency: 3,
      analytics_tier: 'advanced',
      support_tier: 'business_hours',
    });
    mockGetAdminBillingDomainBindings.mockResolvedValue({
      creator_bid: 'creator-1',
      custom_domain_enabled: true,
      items: [
        {
          domain_binding_bid: 'domain-1',
          creator_bid: 'creator-1',
          host: 'creator.example.com',
          status: 'verified',
          verification_method: 'dns_txt',
          verification_token: 'verify-token-1',
          verification_record_name: '_ai-shifu.creator.example.com',
          verification_record_value: 'verify-token-1',
          last_verified_at: '2026-04-08T10:00:00Z',
          ssl_status: 'issued',
          is_effective: true,
          metadata: {},
        },
      ],
    });
    mockBindAdminBillingDomain.mockResolvedValue({
      action: 'bind',
      binding: {
        domain_binding_bid: 'domain-2',
        creator_bid: 'creator-1',
        host: 'new.example.com',
        status: 'pending',
        verification_method: 'dns_txt',
        verification_token: 'verify-token-2',
        verification_record_name: '_ai-shifu.new.example.com',
        verification_record_value: 'verify-token-2',
        last_verified_at: null,
        ssl_status: 'not_requested',
        is_effective: false,
        metadata: {},
      },
    });
  });

  test('renders branding snapshot and existing domain bindings', async () => {
    renderComponent();

    expect(mockGetBillingEntitlements).toHaveBeenCalledWith({
      timezone: 'Asia/Shanghai',
    });
    expect(mockGetAdminBillingDomainBindings).toHaveBeenCalledWith({
      timezone: 'Asia/Shanghai',
    });

    expect(
      screen.getByText('module.billing.domains.branding.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('https://cdn.example.com/logo-wide.png'),
    ).toBeInTheDocument();
    expect(await screen.findByText('creator.example.com')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.domains.records.effective'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('_ai-shifu.creator.example.com'),
    ).toBeInTheDocument();
  });

  test('binds a new host and can disable an existing binding', async () => {
    const user = userEvent.setup();

    renderComponent();

    await screen.findByText('creator.example.com');

    await act(async () => {
      await user.type(
        screen.getByLabelText('module.billing.domains.form.hostLabel'),
        'new.example.com',
      );
      await user.click(
        screen.getByRole('button', {
          name: 'module.billing.domains.actions.bind',
        }),
      );
    });

    expect(mockBindAdminBillingDomain).toHaveBeenCalledWith({
      action: 'bind',
      host: 'new.example.com',
    });

    await act(async () => {
      await user.click(
        screen.getAllByRole('button', {
          name: 'module.billing.domains.actions.disable',
        })[1],
      );
    });

    expect(mockBindAdminBillingDomain).toHaveBeenCalledWith({
      action: 'disable',
      domain_binding_bid: 'domain-1',
      host: 'creator.example.com',
    });
    expect(mockToast).toHaveBeenCalled();
  });
});

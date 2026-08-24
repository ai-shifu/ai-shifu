import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import api from '@/api';
import { AdminBillingProviderPricesPanel } from './AdminBillingProviderPricesPanel';

const mockToast = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options?.productName ? `${key}:${options.productName}` : key,
    i18n: { language: 'en-US' },
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  toast: (...args: unknown[]) => mockToast(...args),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminBillingProviderPrices: jest.fn(),
    createAdminBillingProviderPrice: jest.fn(),
    validateAdminBillingProviderPrice: jest.fn(),
    activateAdminBillingProviderPrice: jest.fn(),
    retireAdminBillingProviderPrice: jest.fn(),
  },
}));

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}));

jest.mock('@/components/ui/AlertDialog', () => ({
  AlertDialog: ({
    open,
    children,
  }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  AlertDialogAction: ({
    children,
    onClick,
  }: React.PropsWithChildren<{
    onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  }>) => (
    <button
      type='button'
      onClick={onClick}
    >
      {children}
    </button>
  ),
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => (
    <button type='button'>{children}</button>
  ),
  AlertDialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => (
    <h2>{children}</h2>
  ),
}));

jest.mock('@/components/ui/DropdownMenu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuItem: ({
    children,
    onSelect,
    disabled,
  }: React.PropsWithChildren<{
    onSelect?: () => void;
    disabled?: boolean;
  }>) => (
    <button
      type='button'
      disabled={disabled}
      onClick={onSelect}
    >
      {children}
    </button>
  ),
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/ui/Select', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const SelectContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({ value: '', onValueChange: () => undefined });

  return {
    __esModule: true,
    Select: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange: (value: string) => void;
    }>) => (
      <SelectContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    SelectValue: ({ placeholder }: { placeholder?: string }) => (
      <span>{placeholder}</span>
    ),
    SelectContent: ({ children }: React.PropsWithChildren) => (
      <div>{children}</div>
    ),
    SelectItem: ({
      value,
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(SelectContext);
      return (
        <button
          type='button'
          onClick={() => context.onValueChange(value)}
        >
          {children}
        </button>
      );
    },
  };
});

const mockGetAdminBillingProviderPrices =
  api.getAdminBillingProviderPrices as jest.Mock;
const mockCreateAdminBillingProviderPrice =
  api.createAdminBillingProviderPrice as jest.Mock;
const mockValidateAdminBillingProviderPrice =
  api.validateAdminBillingProviderPrice as jest.Mock;
const mockActivateAdminBillingProviderPrice =
  api.activateAdminBillingProviderPrice as jest.Mock;
const mockRetireAdminBillingProviderPrice =
  api.retireAdminBillingProviderPrice as jest.Mock;

const renderPanel = () =>
  render(
    <SWRConfig value={{ provider: () => new Map() }}>
      <AdminBillingProviderPricesPanel />
    </SWRConfig>,
  );

describe('AdminBillingProviderPricesPanel', () => {
  beforeEach(() => {
    mockToast.mockReset();
    mockGetAdminBillingProviderPrices.mockReset();
    mockCreateAdminBillingProviderPrice.mockReset();
    mockValidateAdminBillingProviderPrice.mockReset();
    mockActivateAdminBillingProviderPrice.mockReset();
    mockRetireAdminBillingProviderPrice.mockReset();
    mockGetAdminBillingProviderPrices.mockResolvedValue({
      products: [
        {
          product_bid: 'bill-product-global-scale-monthly',
          product_code: 'creator-global-scale-monthly',
          product_type: 'plan',
          display_name: 'module.billing.catalog.scale.title',
          description: '',
          currency: 'USD',
          price_amount: 9900,
          credit_amount: 100,
          billing_interval: 'month',
          billing_interval_count: 1,
          plan_tier: 'scale',
          sort_order: 10,
        },
      ],
      mappings: [],
      active_by_scope: {},
      history_by_product: {},
      status_options: [],
    });
    mockCreateAdminBillingProviderPrice.mockResolvedValue({
      mapping: {
        provider_price_bid: 'provider-price-1',
        product_bid: 'bill-product-global-scale-monthly',
      },
    });
    mockValidateAdminBillingProviderPrice.mockResolvedValue({
      valid: true,
      errors: [],
      warnings: [],
      mapping: null,
    });
    mockActivateAdminBillingProviderPrice.mockResolvedValue({
      valid: true,
      errors: [],
      warnings: [],
      mapping: null,
    });
    mockRetireAdminBillingProviderPrice.mockResolvedValue({});
  });

  test('validates the saved draft automatically', async () => {
    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.billing.admin.providerPrices.actions.create',
      }),
    );
    fireEvent.click(
      screen.getAllByText(/creator-global-scale-monthly/).at(-1)!,
    );
    fireEvent.change(
      screen.getByLabelText(
        'module.billing.admin.providerPrices.fields.productId',
      ),
      { target: { value: 'prod_V6Dk7DvFyxIfOI' } },
    );
    fireEvent.change(
      screen.getByLabelText(
        'module.billing.admin.providerPrices.fields.priceId',
      ),
      { target: { value: 'price_1U61JKJC2CFSg110ua1P6afH' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.billing.admin.providerPrices.actions.saveDraft',
      }),
    );

    await waitFor(() => {
      expect(mockCreateAdminBillingProviderPrice).toHaveBeenCalledWith(
        {
          product_bid: 'bill-product-global-scale-monthly',
          provider_product_id: 'prod_V6Dk7DvFyxIfOI',
          provider_price_id: 'price_1U61JKJC2CFSg110ua1P6afH',
        },
        { skipErrorToast: true },
      );
      expect(mockValidateAdminBillingProviderPrice).toHaveBeenCalledWith(
        {
          provider_price_bid: 'provider-price-1',
        },
        { skipErrorToast: true },
      );
      expect(mockToast).toHaveBeenCalledWith({
        title: 'module.billing.admin.providerPrices.toast.validateSuccess',
        description: undefined,
        variant: undefined,
      });
    });
  });

  test('keeps a draft price visible when the product already has an active price', async () => {
    mockGetAdminBillingProviderPrices.mockResolvedValue({
      products: [
        {
          product_bid: 'bill-product-global-scale-monthly',
          product_code: 'creator-global-scale-monthly',
          product_type: 'plan',
          display_name: 'module.billing.catalog.scale.title',
          description: '',
          currency: 'USD',
          price_amount: 9900,
          credit_amount: 100,
          billing_interval: 'month',
          billing_interval_count: 1,
          plan_tier: 'scale',
          sort_order: 10,
        },
      ],
      mappings: [],
      active_by_scope: {
        'bill-product-global-scale-monthly:stripe:acct_1:test': {
          provider_price_bid: 'provider-price-active',
          product_bid: 'bill-product-global-scale-monthly',
          provider: 'stripe',
          provider_account_id: 'acct_1',
          provider_product_id: 'prod_active',
          provider_price_id: 'price_active',
          livemode: false,
          currency: 'USD',
          unit_amount: 9900,
          billing_mode: 0,
          billing_interval: 0,
          billing_interval_count: 1,
          status: 0,
          status_label: 'active',
        },
      },
      history_by_product: {
        'bill-product-global-scale-monthly': [
          {
            provider_price_bid: 'provider-price-draft',
            product_bid: 'bill-product-global-scale-monthly',
            provider: 'stripe',
            provider_account_id: 'acct_1',
            provider_product_id: 'prod_draft',
            provider_price_id: 'price_draft',
            livemode: false,
            currency: 'USD',
            unit_amount: 9900,
            billing_mode: 0,
            billing_interval: 0,
            billing_interval_count: 1,
            status: 0,
            status_label: 'draft',
          },
          {
            provider_price_bid: 'provider-price-active',
            product_bid: 'bill-product-global-scale-monthly',
            provider: 'stripe',
            provider_account_id: 'acct_1',
            provider_product_id: 'prod_active',
            provider_price_id: 'price_active',
            livemode: false,
            currency: 'USD',
            unit_amount: 9900,
            billing_mode: 0,
            billing_interval: 0,
            billing_interval_count: 1,
            status: 0,
            status_label: 'active',
          },
        ],
      },
      status_options: [],
    });

    renderPanel();

    expect(
      await screen.findByText(
        'module.billing.admin.providerPrices.status.draft',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.admin.providerPrices.status.active'),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.billing.admin.providerPrices.actions.activate',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.confirm',
      }),
    );

    await waitFor(() => {
      expect(mockActivateAdminBillingProviderPrice).toHaveBeenCalledWith(
        {
          provider_price_bid: 'provider-price-draft',
        },
        { skipErrorToast: true },
      );
    });
  });

  test('uses the admin confirmation dialog before disabling a price', async () => {
    const confirmSpy = jest.spyOn(window, 'confirm');
    mockGetAdminBillingProviderPrices.mockResolvedValue({
      products: [
        {
          product_bid: 'bill-product-global-scale-monthly',
          product_code: 'creator-global-scale-monthly',
          product_type: 'plan',
          display_name: 'module.billing.catalog.scale.title',
          description: '',
          currency: 'USD',
          price_amount: 9900,
          credit_amount: 100,
          billing_interval: 'month',
          billing_interval_count: 1,
          plan_tier: 'scale',
          sort_order: 10,
        },
      ],
      mappings: [],
      active_by_scope: {
        'bill-product-global-scale-monthly:stripe:acct_1:test': {
          provider_price_bid: 'provider-price-active',
          product_bid: 'bill-product-global-scale-monthly',
          provider: 'stripe',
          provider_account_id: 'acct_1',
          provider_product_id: 'prod_1',
          provider_price_id: 'price_1',
          livemode: false,
          currency: 'USD',
          unit_amount: 9900,
          billing_mode: 0,
          billing_interval: 0,
          billing_interval_count: 1,
          status: 0,
          status_label: 'active',
        },
      },
      history_by_product: {
        'bill-product-global-scale-monthly': [
          {
            provider_price_bid: 'provider-price-active',
            product_bid: 'bill-product-global-scale-monthly',
            provider: 'stripe',
            provider_account_id: 'acct_1',
            provider_product_id: 'prod_1',
            provider_price_id: 'price_1',
            livemode: false,
            currency: 'USD',
            unit_amount: 9900,
            billing_mode: 0,
            billing_interval: 0,
            billing_interval_count: 1,
            status: 0,
            status_label: 'active',
          },
        ],
      },
      status_options: [],
    });

    renderPanel();

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.billing.admin.providerPrices.actions.retire',
      }),
    );

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        'module.billing.admin.providerPrices.confirm.retire:creator-global-scale-monthly module.billing.admin.providerPrices.billingLabel.monthly',
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.confirm',
      }),
    );

    await waitFor(() => {
      expect(mockRetireAdminBillingProviderPrice).toHaveBeenCalledWith(
        {
          provider_price_bid: 'provider-price-active',
        },
        { skipErrorToast: true },
      );
    });
    confirmSpy.mockRestore();
  });
});

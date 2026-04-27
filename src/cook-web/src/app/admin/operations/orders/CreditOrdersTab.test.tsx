import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import CreditOrdersTab from './CreditOrdersTab';

const translationCache = new Map<string, { t: (key: string) => string }>();
const baseTranslation = (namespace?: string | string[]) => {
  const ns = Array.isArray(namespace) ? namespace[0] : namespace;
  const cacheKey = ns || 'translation';
  if (!translationCache.has(cacheKey)) {
    translationCache.set(cacheKey, {
      t: (key: string, options?: Record<string, unknown>) => {
        if (options && Object.prototype.hasOwnProperty.call(options, 'count')) {
          return `${ns ? `${ns}.` : ''}${key}:${options.count}`;
        }
        if (
          options &&
          Object.prototype.hasOwnProperty.call(options, 'credits')
        ) {
          return `${ns ? `${ns}.` : ''}${key}:${options.credits}`;
        }
        return ns && ns !== 'translation' ? `${ns}.${key}` : key;
      },
    });
  }
  return translationCache.get(cacheKey)!;
};

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    href,
    children,
    ...props
  }: React.PropsWithChildren<{ href: string }>) => (
    <a
      href={href}
      {...props}
    >
      {children}
    </a>
  ),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCreditOrders: jest.fn(),
    getAdminOperationCreditOrderDetail: jest.fn(),
  },
}));

jest.mock('@/lib/request', () => ({
  __esModule: true,
  ErrorWithCode: class MockErrorWithCode extends Error {
    code: number;

    constructor(message: string, code: number) {
      super(message);
      this.code = code;
    }
  },
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      loginMethodsEnabled: string[];
      defaultLoginMethod: string;
    }) => unknown,
  ) =>
    selector({
      loginMethodsEnabled: ['phone'],
      defaultLoginMethod: 'phone',
    }),
}));

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => 'UTC',
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => ({
    ...baseTranslation(namespace),
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage: string }) => (
    <div>{errorMessage}</div>
  ),
}));

jest.mock('@/components/ui/Select', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const SelectContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({
    value: '',
    onValueChange: () => undefined,
  });

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

jest.mock('@/app/admin/components/AdminDateRangeFilter', () => ({
  __esModule: true,
  default: ({ placeholder }: { placeholder: string }) => (
    <div>{placeholder}</div>
  ),
}));

jest.mock('@/components/ui/Dialog', () => ({
  __esModule: true,
  Dialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div role='dialog'>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

const mockGetAdminOperationCreditOrders =
  api.getAdminOperationCreditOrders as jest.Mock;
const mockGetAdminOperationCreditOrderDetail =
  api.getAdminOperationCreditOrderDetail as jest.Mock;

describe('CreditOrdersTab', () => {
  beforeEach(() => {
    mockGetAdminOperationCreditOrders.mockReset();
    mockGetAdminOperationCreditOrderDetail.mockReset();
    window.localStorage.clear();

    mockGetAdminOperationCreditOrders.mockResolvedValue({
      items: [
        {
          bill_order_bid: 'bill-order-1',
          creator_bid: 'creator-1',
          creator_identify: '13800138000',
          creator_mobile: '13800138000',
          creator_email: '',
          creator_nickname: 'Creator One',
          credit_order_kind: 'topup',
          product_bid: 'product-1',
          product_code: 'creator-topup-small',
          product_type: 'topup',
          product_name_key: 'module.billing.catalog.topups.creatorSmall.title',
          credit_amount: 20,
          valid_from: '2026-04-27T10:00:00Z',
          valid_to: '2026-05-27T10:00:00Z',
          order_type: 'topup',
          status: 'paid',
          payment_provider: 'pingxx',
          payment_channel: 'alipay_qr',
          payable_amount: 19900,
          paid_amount: 19900,
          currency: 'CNY',
          provider_reference_id: 'charge_1',
          failure_code: '',
          failure_message: '',
          created_at: '2026-04-27T09:00:00Z',
          paid_at: '2026-04-27T10:00:00Z',
          failed_at: null,
          refunded_at: null,
          has_attention: false,
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    mockGetAdminOperationCreditOrderDetail.mockResolvedValue({
      order: {
        bill_order_bid: 'bill-order-1',
        creator_bid: 'creator-1',
        creator_identify: '13800138000',
        creator_mobile: '13800138000',
        creator_email: '',
        creator_nickname: 'Creator One',
        credit_order_kind: 'topup',
        product_bid: 'product-1',
        product_code: 'creator-topup-small',
        product_type: 'topup',
        product_name_key: 'module.billing.catalog.topups.creatorSmall.title',
        credit_amount: 20,
        valid_from: '2026-04-27T10:00:00Z',
        valid_to: '2026-05-27T10:00:00Z',
        order_type: 'topup',
        status: 'paid',
        payment_provider: 'pingxx',
        payment_channel: 'alipay_qr',
        payable_amount: 19900,
        paid_amount: 19900,
        currency: 'CNY',
        provider_reference_id: 'charge_1',
        failure_code: '',
        failure_message: '',
        created_at: '2026-04-27T09:00:00Z',
        paid_at: '2026-04-27T10:00:00Z',
        failed_at: null,
        refunded_at: null,
        has_attention: false,
      },
      grant: {
        granted_credits: 20,
        valid_from: '2026-04-27T10:00:00Z',
        valid_to: '2026-05-27T10:00:00Z',
        source_type: 'topup',
        source_bid: 'bill-order-1',
      },
      metadata: {
        checkout_type: 'topup',
      },
    });
  });

  test('requests operator credit orders on first render', async () => {
    render(<CreditOrdersTab />);

    await waitFor(() => {
      expect(mockGetAdminOperationCreditOrders).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        creator_keyword: '',
        product_keyword: '',
        bill_order_bid: '',
        credit_order_kind: '',
        status: '',
        payment_provider: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('bill-order-1')).toBeInTheDocument();
    expect(screen.getAllByText('creator-topup-small').length).toBeGreaterThan(
      0,
    );
    expect(
      screen.queryByText('module.billing.catalog.topups.creatorSmall.title'),
    ).not.toBeInTheDocument();
  });

  test('submits filters and opens detail dialog', async () => {
    render(<CreditOrdersTab />);

    await waitFor(() => {
      expect(mockGetAdminOperationCreditOrders).toHaveBeenCalledTimes(1);
    });

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsOrder.creditOrders.filters.creatorKeywordPlaceholderPhone',
      ),
      {
        target: { value: '13800138000' },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.expand',
      }),
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsOrder.creditOrders.filters.productKeywordPlaceholder',
      ),
      {
        target: { value: 'creator-topup-small' },
      },
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsOrder.creditOrders.filters.orderIdPlaceholder',
      ),
      {
        target: { value: 'bill-order-1' },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsOrder.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCreditOrders).toHaveBeenLastCalledWith(
        expect.objectContaining({
          creator_keyword: '13800138000',
          product_keyword: 'creator-topup-small',
          bill_order_bid: 'bill-order-1',
        }),
      );
    });

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.operationsOrder.table.view',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCreditOrderDetail).toHaveBeenCalledWith({
        bill_order_bid: 'bill-order-1',
      });
    });

    expect(
      await screen.findByText(
        'module.operationsOrder.creditOrders.detail.title',
      ),
    ).toBeInTheDocument();
  });

  test('shows detail error state when detail request fails', async () => {
    mockGetAdminOperationCreditOrderDetail.mockRejectedValueOnce(
      new Error('detail failed'),
    );

    render(<CreditOrdersTab />);

    await waitFor(() => {
      expect(mockGetAdminOperationCreditOrders).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.operationsOrder.table.view',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCreditOrderDetail).toHaveBeenCalledWith({
        bill_order_bid: 'bill-order-1',
      });
    });

    expect(await screen.findByText('detail failed')).toBeInTheDocument();
  });
});

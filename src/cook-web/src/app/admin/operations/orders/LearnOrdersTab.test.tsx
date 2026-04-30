import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import LearnOrdersTab from './LearnOrdersTab';

let mockSearchParamsValue = '';
const translationCache = new Map<string, { t: (key: string) => string }>();
const baseTranslation = (namespace?: string | string[]) => {
  const ns = Array.isArray(namespace) ? namespace[0] : namespace;
  const cacheKey = ns || 'translation';
  if (!translationCache.has(cacheKey)) {
    translationCache.set(cacheKey, {
      t: (key: string) => {
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

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(mockSearchParamsValue),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationOrders: jest.fn(),
  },
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      loginMethodsEnabled: string[];
      defaultLoginMethod: string;
      currencySymbol: string;
    }) => unknown,
  ) =>
    selector({
      loginMethodsEnabled: ['phone'],
      defaultLoginMethod: 'phone',
      currencySymbol: '¥',
    }),
}));

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => 'UTC',
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => baseTranslation(namespace),
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

jest.mock('./OperatorOrderDetailSheet', () => ({
  __esModule: true,
  default: ({ open, orderBid }: { open: boolean; orderBid?: string }) => {
    const detailLabel = `detail:${orderBid || ''}`;
    return open ? <div>{detailLabel}</div> : null;
  },
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

const mockGetAdminOperationOrders = api.getAdminOperationOrders as jest.Mock;

describe('LearnOrdersTab', () => {
  beforeEach(() => {
    mockSearchParamsValue = '';
    mockGetAdminOperationOrders.mockReset();
    window.localStorage.clear();
    mockGetAdminOperationOrders.mockResolvedValue({
      items: [
        {
          order_bid: 'order-1',
          shifu_bid: 'course-1',
          shifu_name: 'Course 1',
          user_bid: 'user-1',
          user_mobile: '13800138000',
          user_email: '',
          user_nickname: 'Tester',
          payable_price: '99',
          paid_price: '79',
          discount_amount: '20',
          status: 502,
          status_key: 'server.order.orderStatusSuccess',
          payment_channel: 'stripe',
          payment_channel_key: 'module.order.paymentChannel.stripe',
          order_source: 'user_purchase',
          order_source_key: 'module.operationsOrder.source.userPurchase',
          coupon_codes: ['FREE100'],
          created_at: '2026-04-23T10:00:00Z',
          updated_at: '2026-04-23T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
  });

  test('requests operator orders on first render with default filters', async () => {
    render(<LearnOrdersTab />);

    await waitFor(() => {
      expect(mockGetAdminOperationOrders).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        user_keyword: '',
        order_bid: '',
        shifu_bid: '',
        course_name: '',
        status: '502',
        order_source: '',
        payment_channel: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(await screen.findByText('order-1')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsOrder.totalCount'),
    ).toBeInTheDocument();
  });

  test('hydrates the course filter from the url query', async () => {
    mockSearchParamsValue = 'shifu_bid=course-1';

    render(<LearnOrdersTab />);

    await waitFor(() => {
      expect(mockGetAdminOperationOrders).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        user_keyword: '',
        order_bid: '',
        shifu_bid: 'course-1',
        course_name: '',
        status: '502',
        order_source: '',
        payment_channel: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(screen.getByDisplayValue('course-1')).toBeInTheDocument();
  });

  test('submits filters and opens detail drawer', async () => {
    render(<LearnOrdersTab />);

    await waitFor(() => {
      expect(mockGetAdminOperationOrders).toHaveBeenCalledTimes(1);
    });

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsOrder.filters.userKeywordPlaceholderPhone',
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
        'module.operationsOrder.filters.orderIdPlaceholder',
      ),
      {
        target: { value: 'order-1' },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsOrder.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationOrders).toHaveBeenLastCalledWith(
        expect.objectContaining({
          user_keyword: '13800138000',
          order_bid: 'order-1',
        }),
      );
    });

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.operationsOrder.table.view',
      }),
    );

    expect(await screen.findByText('detail:order-1')).toBeInTheDocument();
  });

  test('shows error UI when getAdminOperationOrders fails', async () => {
    mockGetAdminOperationOrders.mockRejectedValueOnce(new Error('network'));

    render(<LearnOrdersTab />);

    expect(await screen.findByText('network')).toBeInTheDocument();
  });
});

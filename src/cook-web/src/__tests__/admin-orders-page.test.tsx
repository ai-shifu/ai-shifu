import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import api from '@/api';

import OrdersPage from '@/app/admin/orders/page';

const mockReplace = jest.fn();
let mockSearchParamsValue = '';

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
  useSearchParams: () => new URLSearchParams(mockSearchParamsValue),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOrders: jest.fn(),
    getAdminOrderShifus: jest.fn(),
  },
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (
    selector: (state: { isInitialized: boolean; isGuest: boolean }) => unknown,
  ) =>
    selector({
      isInitialized: true,
      isGuest: false,
    }),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      loginMethodsEnabled: string[];
      defaultLoginMethod: string;
      currencySymbol: string;
      payOrderExpireSeconds: number;
    }) => unknown,
  ) =>
    selector({
      loginMethodsEnabled: ['email'],
      defaultLoginMethod: 'email',
      currencySymbol: '¥',
      payOrderExpireSeconds: 600,
    }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/components/order/OrderDetailSheet', () => () => null);
jest.mock('@/components/order/ImportActivationDialog', () => () => null);
jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage: string }) => (
    <div>{errorMessage}</div>
  ),
}));
jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ui/Popover', () => ({
  __esModule: true,
  Popover: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  PopoverTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  PopoverContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/ui/ScrollArea', () => ({
  __esModule: true,
  ScrollArea: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/components/ui/Calendar', () => ({
  __esModule: true,
  Calendar: () => <div />,
}));

jest.mock('@/components/ui/tooltip', () => ({
  __esModule: true,
  TooltipProvider: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  Tooltip: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/ui/Badge', () => ({
  __esModule: true,
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}));

jest.mock('@/components/ui/pagination', () => ({
  __esModule: true,
  Pagination: ({ children }: React.PropsWithChildren) => (
    <nav aria-label='pagination'>{children}</nav>
  ),
  PaginationContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  PaginationEllipsis: () => <span>...</span>,
  PaginationItem: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  PaginationLink: ({
    children,
    href,
    onClick,
  }: React.PropsWithChildren<{
    href?: string;
    onClick?: React.MouseEventHandler;
  }>) => (
    <a
      href={href}
      onClick={onClick}
    >
      {children}
    </a>
  ),
  PaginationNext: ({ children }: React.PropsWithChildren) => (
    <button>{children}</button>
  ),
  PaginationPrevious: ({ children }: React.PropsWithChildren) => (
    <button>{children}</button>
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

const mockGetAdminOrders = api.getAdminOrders as jest.Mock;
const mockGetAdminOrderShifus = api.getAdminOrderShifus as jest.Mock;

const getStatusFilterRow = (): HTMLElement =>
  screen
    .getAllByText('module.order.filters.status')[0]
    .closest('div') as HTMLElement;

describe('OrdersPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockGetAdminOrders.mockReset();
    mockGetAdminOrderShifus.mockReset();
    mockSearchParamsValue = '';
    window.localStorage.clear();

    mockGetAdminOrders.mockResolvedValue({
      items: [],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 0,
    });
    mockGetAdminOrderShifus.mockResolvedValue({
      items: [{ bid: 'shifu-1', name: 'Course 1' }],
    });
  });

  test('defaults to success orders when status is missing from url', async () => {
    render(<OrdersPage />);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
          shifu_bid: '',
          status: '502',
        }),
      );
    });

    expect(mockReplace).toHaveBeenCalledWith('/admin/orders?status=502');
  });

  test('preserves shifu_bid and appends success status when url has no status', async () => {
    mockSearchParamsValue = 'shifu_bid=shifu-1';

    render(<OrdersPage />);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          shifu_bid: 'shifu-1',
          status: '502',
        }),
      );
    });

    expect(mockReplace).toHaveBeenCalledWith(
      '/admin/orders?shifu_bid=shifu-1&status=502',
    );
  });

  test('does not normalize url again when success status is already explicit', async () => {
    mockSearchParamsValue = 'shifu_bid=shifu-1&status=502';

    render(<OrdersPage />);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          shifu_bid: 'shifu-1',
          status: '502',
        }),
      );
    });

    expect(mockReplace).not.toHaveBeenCalled();
  });

  test('reset restores default success status instead of clearing it', async () => {
    mockSearchParamsValue = 'shifu_bid=shifu-1&status=503';

    render(<OrdersPage />);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          shifu_bid: 'shifu-1',
          status: '503',
        }),
      );
    });

    mockGetAdminOrders.mockClear();
    mockReplace.mockClear();

    fireEvent.click(
      await screen.findByRole('button', { name: 'module.order.filters.reset' }),
    );

    expect(mockReplace).toHaveBeenCalledWith('/admin/orders?status=502');

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
          shifu_bid: '',
          status: '502',
        }),
      );
    });
  });

  test('keeps explicit all-status query when user switches status to all', async () => {
    mockSearchParamsValue = 'status=502';

    render(<OrdersPage />);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          status: '502',
        }),
      );
    });

    mockGetAdminOrders.mockClear();
    mockReplace.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'common.core.expand' }));
    fireEvent.click(
      within(getStatusFilterRow()).getByRole('button', {
        name: 'module.order.filters.all',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'module.order.filters.search' }),
    );

    expect(mockReplace).toHaveBeenCalledWith('/admin/orders?status=');

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
          status: '',
        }),
      );
    });
  });
});

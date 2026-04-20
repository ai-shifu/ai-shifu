import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';

import OrdersPage from './page';

const mockReplace = jest.fn();
let mockSearchParamsValue = 'shifu_bid=shifu-1&status=502';

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

const mockGetAdminOrders = api.getAdminOrders as jest.Mock;
const mockGetAdminOrderShifus = api.getAdminOrderShifus as jest.Mock;
const NORMALIZED_JUMP_URL = '/admin/orders?shifu_bid=shifu-1&status=502';

describe('OrdersPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockGetAdminOrders.mockReset();
    mockGetAdminOrderShifus.mockReset();
    mockSearchParamsValue = 'shifu_bid=shifu-1';
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

  test('uses shifu_bid and default success status for the first orders request', async () => {
    render(<OrdersPage />);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
          shifu_bid: 'shifu-1',
          status: '502',
        }),
      );
    });

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith(NORMALIZED_JUMP_URL);
    });
  });

  test('keeps shifu_bid and status in url when searching with initial jump filters', async () => {
    render(<OrdersPage />);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          shifu_bid: 'shifu-1',
          status: '502',
        }),
      );
    });

    mockGetAdminOrders.mockClear();
    mockReplace.mockClear();

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    expect(mockReplace).toHaveBeenCalledWith(NORMALIZED_JUMP_URL);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
          shifu_bid: 'shifu-1',
          status: '502',
        }),
      );
    });
  });

  test('resets to default success status while clearing shifu_bid from url', async () => {
    render(<OrdersPage />);

    await waitFor(() => {
      expect(mockGetAdminOrders).toHaveBeenCalledWith(
        expect.objectContaining({
          shifu_bid: 'shifu-1',
          status: '502',
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
});

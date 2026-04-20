import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import api from '@/api';

import { buildAdminOrdersUrl } from './admin-dashboard-routes';
import AdminDashboardEntryPage from './page';

const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getDashboardEntry: jest.fn(),
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
  useEnvStore: (selector: (state: { currencySymbol: string }) => unknown) =>
    selector({
      currencySymbol: '¥',
    }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

const mockGetDashboardEntry = api.getDashboardEntry as jest.Mock;

describe('AdminDashboardEntryPage', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockGetDashboardEntry.mockReset();
    mockGetDashboardEntry.mockResolvedValue({
      summary: {
        course_count: 1,
        learner_count: 2,
        order_count: 3,
        order_amount: '99.00',
      },
      items: [
        {
          shifu_bid: 'shifu-1',
          shifu_name: 'Course 1',
          learner_count: 2,
          order_count: 3,
          order_amount: '99.00',
          last_active_at: '2026-03-06T08:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
  });

  test('builds orders url with shifu_bid', () => {
    expect(buildAdminOrdersUrl('shifu-1')).toBe(
      '/admin/orders?shifu_bid=shifu-1',
    );
    expect(buildAdminOrdersUrl('   ')).toBeNull();
  });

  test('renders order count button for each dashboard row', async () => {
    render(<AdminDashboardEntryPage />);

    await waitFor(() => {
      expect(mockGetDashboardEntry).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
          keyword: '',
          start_date: '',
          end_date: '',
        }),
      );
    });
    expect(
      await screen.findByRole('button', {
        name: 'module.dashboard.entry.table.orders-shifu-1',
      }),
    ).toBeEnabled();
  });

  test('keeps pagination and scope note outside the list scroll region', async () => {
    mockGetDashboardEntry.mockImplementation(() => new Promise(() => {}));

    render(<AdminDashboardEntryPage />);

    await waitFor(() => {
      expect(mockGetDashboardEntry).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
          keyword: '',
          start_date: '',
          end_date: '',
        }),
      );
    });

    const scrollRegion = screen.getByTestId(
      'dashboard-course-list-scroll-region',
    );
    const footer = screen.getByTestId('dashboard-course-list-footer');
    const pagination = screen.getByRole('navigation', { name: 'pagination' });
    const scopeNote = screen.getByText(
      'module.dashboard.entry.table.scopeNote',
    );

    expect(scrollRegion).not.toContainElement(pagination);
    expect(scrollRegion).not.toContainElement(scopeNote);
    expect(footer).toContainElement(pagination);
    expect(footer).toContainElement(scopeNote);
  });
});

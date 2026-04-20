import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';

import {
  buildAdminDashboardCourseDetailUrl,
  buildAdminOrdersUrl,
} from './admin-dashboard-routes';
import AdminDashboardEntryPage from './page';
import { DashboardCourseTableRow } from './dashboardCourseTableRow';

const mockPush = jest.fn();
const mockTranslate = (key: string) => key;

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
    t: mockTranslate,
  }),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/lib/browser-timezone', () => ({
  __esModule: true,
  getBrowserTimeZone: () => 'Asia/Shanghai',
}));

const mockGetDashboardEntry = api.getDashboardEntry as jest.Mock;
const DASHBOARD_ENTRY_RESPONSE = {
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
      last_active_at_display: '2026-03-06 16:00:00',
    },
  ],
  page: 1,
  page_count: 1,
  page_size: 20,
  total: 1,
};

describe('AdminDashboardEntryPage', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockGetDashboardEntry.mockReset();
    mockGetDashboardEntry.mockResolvedValue(DASHBOARD_ENTRY_RESPONSE);
  });

  test('builds dashboard urls with shifu_bid', () => {
    expect(buildAdminOrdersUrl('shifu-1')).toBe(
      '/admin/orders?shifu_bid=shifu-1',
    );
    expect(buildAdminDashboardCourseDetailUrl('shifu-1')).toBe(
      '/admin/dashboard/shifu-1',
    );
    expect(buildAdminOrdersUrl('   ')).toBeNull();
    expect(buildAdminDashboardCourseDetailUrl('   ')).toBeNull();
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
          timezone: 'Asia/Shanghai',
        }),
      );
    });

    const orderButton = await screen.findByRole('button', {
      name: 'module.dashboard.entry.table.orders-shifu-1',
    });

    expect(orderButton).toBeEnabled();
  });

  test('keeps order click isolated while only the course cell opens detail', () => {
    const onCourseDetailClick = jest.fn();
    const onOrderClick = jest.fn();

    render(
      <table>
        <tbody>
          <DashboardCourseTableRow
            item={DASHBOARD_ENTRY_RESPONSE.items[0]}
            currencySymbol='¥'
            orderButtonLabel='module.dashboard.entry.table.orders-shifu-1'
            onCourseDetailClick={onCourseDetailClick}
            onOrderClick={onOrderClick}
          />
        </tbody>
      </table>,
    );

    const orderButton = screen.getByRole('button', {
      name: 'module.dashboard.entry.table.orders-shifu-1',
    });
    const courseButton = screen.getByRole('button', {
      name: 'Course 1-shifu-1',
    });
    const courseName = screen.getByText('Course 1');
    const courseId = screen.getByText('shifu-1');
    const courseRow = orderButton.closest('tr');

    expect(courseRow).not.toBeNull();
    expect(screen.getByText('2026-03-06 16:00:00')).toBeInTheDocument();
    expect(courseButton).toHaveClass('group');
    expect(courseName).toHaveClass('text-primary');
    expect(courseName).toHaveClass('group-hover:underline');
    expect(courseId).toHaveClass('text-muted-foreground');
    expect(courseId).toHaveClass('group-hover:text-primary/80');

    fireEvent.click(orderButton);

    expect(onOrderClick).toHaveBeenCalledTimes(1);
    expect(onOrderClick).toHaveBeenCalledWith('shifu-1');
    expect(onCourseDetailClick).not.toHaveBeenCalled();

    fireEvent.click(courseRow as HTMLElement);

    expect(onCourseDetailClick).not.toHaveBeenCalled();

    fireEvent.click(courseButton);

    expect(onCourseDetailClick).toHaveBeenCalledTimes(1);
    expect(onCourseDetailClick).toHaveBeenCalledWith('shifu-1');
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
          timezone: 'Asia/Shanghai',
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

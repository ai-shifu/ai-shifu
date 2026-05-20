import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { ErrorWithCode } from '@/lib/request';

import AdminDashboardCourseDetailPage from './page';
import {
  buildAdminDashboardCourseFollowUpsUrl,
  buildAdminDashboardCourseRatingsUrl,
  buildAdminOrdersUrl,
} from '../admin-dashboard-routes';

let mockParams: { shifu_bid?: string | string[] } = {
  shifu_bid: 'shifu-1',
};
const mockPush = jest.fn();

const mockGetDashboardCourseDetail = api.getDashboardCourseDetail as jest.Mock;
const mockGetDashboardCourseLearners =
  api.getDashboardCourseLearners as jest.Mock;
const mockTranslate = (key: string) => key;

const createDetailResponse = (overrides?: Record<string, unknown>) => ({
  basic_info: {
    shifu_bid: 'shifu-1',
    course_name: 'Course 1',
    course_status: 'published',
    created_at: '2025-01-01T08:00:00',
    created_at_display: '2025-01-01 16:00:00',
    chapter_count: 3,
    learner_count: 2,
  },
  metrics: {
    order_count: 3,
    order_amount: '99.00',
    new_learner_count_last_7_days: 1,
    learning_learner_count: 1,
    completed_learner_count: 1,
    completion_rate: '50.00',
    active_learner_count_last_7_days: 1,
    total_follow_up_count: 8,
    rating_score: '4.0',
  },
  ...overrides,
});

const createLearnersResponse = (overrides?: Record<string, unknown>) => ({
  page: 1,
  page_count: 1,
  page_size: 20,
  total: 2,
  items: [
    {
      user_bid: 'user-1',
      mobile: '13800138000',
      email: '',
      nickname: 'Alice',
      learned_lesson_count: 3,
      total_lesson_count: 6,
      learning_status: 'learning',
      follow_up_count: 5,
      last_learning_at: '2025-01-02T08:00:00',
      last_learning_at_display: '2025-01-02 16:00:00',
      joined_at: '2025-01-01T08:00:00',
      joined_at_display: '2025-01-01 16:00:00',
    },
    {
      user_bid: 'user-2',
      mobile: '',
      email: 'bob@example.com',
      nickname: 'Bob',
      learned_lesson_count: 6,
      total_lesson_count: 6,
      learning_status: 'completed',
      follow_up_count: 3,
      last_learning_at: '',
      last_learning_at_display: '',
      joined_at: '2025-01-03T08:00:00',
      joined_at_display: '2025-01-03 16:00:00',
    },
  ],
  ...overrides,
});

jest.mock('next/navigation', () => ({
  useParams: () => mockParams,
  useRouter: () => ({
    push: mockPush,
  }),
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getDashboardCourseDetail: jest.fn(),
    getDashboardCourseLearners: jest.fn(),
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
      currencySymbol: string;
      loginMethodsEnabled: string[];
      defaultLoginMethod: string;
    }) => unknown,
  ) =>
    selector({
      currencySymbol: '¥',
      loginMethodsEnabled: ['phone'],
      defaultLoginMethod: 'phone',
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

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({
    errorMessage,
    onRetry,
  }: {
    errorMessage: string;
    onRetry: () => void;
  }) => (
    <div>
      <div>{errorMessage}</div>
      <button onClick={onRetry}>retry</button>
    </div>
  ),
}));

jest.mock('@/app/admin/components/AdminDateRangeFilter', () => ({
  __esModule: true,
  default: ({
    placeholder,
    onChange,
  }: {
    placeholder: string;
    onChange: (range: { start: string; end: string }) => void;
  }) => (
    <button
      type='button'
      onClick={() => onChange({ start: '2025-01-01', end: '2025-01-02' })}
    >
      {placeholder}
    </button>
  ),
}));

jest.mock('@/components/ui/Select', () => ({
  __esModule: true,
  Select: ({
    value,
    onValueChange,
    children,
  }: React.PropsWithChildren<{
    value?: string;
    onValueChange?: (value: string) => void;
  }>) => (
    <div>
      <button
        type='button'
        onClick={() => onValueChange?.('completed')}
      >
        {value || 'select'}
      </button>
      {children}
    </div>
  ),
  SelectTrigger: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  SelectValue: () => <span>select-value</span>,
  SelectContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  SelectItem: ({
    children,
    value,
  }: React.PropsWithChildren<{ value: string }>) => (
    <div data-value={value}>{children}</div>
  ),
}));

describe('AdminDashboardCourseDetailPage', () => {
  beforeEach(() => {
    mockParams = { shifu_bid: 'shifu-1' };
    mockGetDashboardCourseDetail.mockReset();
    mockGetDashboardCourseLearners.mockReset();
    mockPush.mockReset();
  });

  test('renders course detail data and learner rows from separate requests', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(createDetailResponse());
    mockGetDashboardCourseLearners.mockResolvedValue(createLearnersResponse());

    render(<AdminDashboardCourseDetailPage />);

    await waitFor(() => {
      expect(mockGetDashboardCourseDetail).toHaveBeenCalledWith({
        shifu_bid: 'shifu-1',
        timezone: 'Asia/Shanghai',
      });
    });
    await waitFor(() => {
      expect(mockGetDashboardCourseLearners).toHaveBeenCalledWith({
        shifu_bid: 'shifu-1',
        page_index: 1,
        page_size: 20,
        keyword: '',
        learning_status: '',
        last_learning_start_time: '',
        last_learning_end_time: '',
        timezone: 'Asia/Shanghai',
      });
    });

    expect(screen.getByText('module.dashboard.title')).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.title').closest('a'),
    ).toHaveAttribute('href', '/admin/dashboard');
    expect(screen.getByText('Course 1')).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.dashboard.detail.basicInfo.statusLabels.published',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('¥99.00')).toBeInTheDocument();
    expect(screen.getByText('50.00%')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('13800138000')).toBeInTheDocument();
    expect(screen.getByText('2025-01-02 16:00:00')).toBeInTheDocument();
  });

  test('navigates to order list from order count and order amount', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(createDetailResponse());
    mockGetDashboardCourseLearners.mockResolvedValue(
      createLearnersResponse({ items: [], total: 0, page_count: 0 }),
    );

    render(<AdminDashboardCourseDetailPage />);

    const orderCountButton = await screen.findByRole('button', {
      name: 'module.dashboard.detail.metrics.orderCount-value',
    });
    const orderAmountButton = screen.getByRole('button', {
      name: 'module.dashboard.detail.metrics.orderAmount-value',
    });

    fireEvent.click(orderCountButton);
    fireEvent.click(orderAmountButton);

    expect(mockPush).toHaveBeenCalledTimes(2);
    expect(mockPush).toHaveBeenNthCalledWith(1, buildAdminOrdersUrl('shifu-1'));
    expect(mockPush).toHaveBeenNthCalledWith(2, buildAdminOrdersUrl('shifu-1'));
  });

  test('navigates to full and learner-scoped follow-up pages', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(
      createDetailResponse({
        basic_info: {
          ...createDetailResponse().basic_info,
          learner_count: 1,
        },
      }),
    );
    mockGetDashboardCourseLearners.mockResolvedValue(
      createLearnersResponse({
        total: 1,
        items: [createLearnersResponse().items[0]],
      }),
    );

    render(<AdminDashboardCourseDetailPage />);

    const totalFollowUpButton = await screen.findByRole('button', {
      name: 'module.dashboard.detail.metrics.totalQuestions-value',
    });
    fireEvent.click(totalFollowUpButton);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.detail.learners.viewFollowUpsForLearner',
      }),
    );

    expect(mockPush).toHaveBeenNthCalledWith(
      1,
      buildAdminDashboardCourseFollowUpsUrl('shifu-1'),
    );
    expect(mockPush).toHaveBeenNthCalledWith(
      2,
      buildAdminDashboardCourseFollowUpsUrl('shifu-1', {
        userBid: 'user-1',
        keyword: '13800138000',
      }),
    );
  });

  test('navigates to ratings page from the rating metric card', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(createDetailResponse());
    mockGetDashboardCourseLearners.mockResolvedValue(
      createLearnersResponse({ items: [], total: 0, page_count: 0 }),
    );

    render(<AdminDashboardCourseDetailPage />);

    const ratingButton = await screen.findByRole('button', {
      name: 'module.dashboard.detail.metrics.rating-value',
    });
    fireEvent.click(ratingButton);

    expect(mockPush).toHaveBeenCalledWith(
      buildAdminDashboardCourseRatingsUrl('shifu-1'),
    );
  });

  test('renders detail error state and retries both requests', async () => {
    mockGetDashboardCourseDetail
      .mockRejectedValueOnce(new ErrorWithCode('detail failed', 404))
      .mockResolvedValueOnce(
        createDetailResponse({
          basic_info: {
            ...createDetailResponse().basic_info,
            course_name: 'Recovered Course',
            created_at: '',
            created_at_display: '',
            chapter_count: 0,
            learner_count: 0,
          },
          metrics: {
            ...createDetailResponse().metrics,
            order_count: 0,
            order_amount: '0.00',
            new_learner_count_last_7_days: 0,
            learning_learner_count: 0,
            completed_learner_count: 0,
            completion_rate: '0.00',
            active_learner_count_last_7_days: 0,
            total_follow_up_count: 0,
            rating_score: '',
          },
        }),
      );
    mockGetDashboardCourseLearners.mockResolvedValue(
      createLearnersResponse({ items: [], total: 0, page_count: 0 }),
    );

    render(<AdminDashboardCourseDetailPage />);

    expect(await screen.findByText('detail failed')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'retry' }));

    await waitFor(() => {
      expect(mockGetDashboardCourseDetail).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(mockGetDashboardCourseLearners).toHaveBeenCalledTimes(2);
    });

    expect(await screen.findByText('Recovered Course')).toBeInTheDocument();
  });

  test('submits learner keyword search and resets filters through learners request only', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(createDetailResponse());
    mockGetDashboardCourseLearners
      .mockResolvedValueOnce(createLearnersResponse())
      .mockResolvedValue(createLearnersResponse({ total: 1, items: [] }));

    render(<AdminDashboardCourseDetailPage />);

    await screen.findByText('Course 1');

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.dashboard.detail.learners.searchPlaceholderPhone',
      ),
      {
        target: { value: 'alice@example.com' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.entry.table.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetDashboardCourseLearners).toHaveBeenLastCalledWith({
        shifu_bid: 'shifu-1',
        page_index: 1,
        page_size: 20,
        keyword: 'alice@example.com',
        learning_status: '',
        last_learning_start_time: '',
        last_learning_end_time: '',
        timezone: 'Asia/Shanghai',
      });
    });
    expect(mockGetDashboardCourseDetail).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText('all'));
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.detail.learners.filters.lastLearningTimePlaceholder',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.entry.table.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetDashboardCourseLearners).toHaveBeenLastCalledWith({
        shifu_bid: 'shifu-1',
        page_index: 1,
        page_size: 20,
        keyword: 'alice@example.com',
        learning_status: 'completed',
        last_learning_start_time: '2025-01-01',
        last_learning_end_time: '2025-01-02',
        timezone: 'Asia/Shanghai',
      });
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.entry.table.reset',
      }),
    );

    await waitFor(() => {
      expect(mockGetDashboardCourseLearners).toHaveBeenLastCalledWith({
        shifu_bid: 'shifu-1',
        page_index: 1,
        page_size: 20,
        keyword: '',
        learning_status: '',
        last_learning_start_time: '',
        last_learning_end_time: '',
        timezone: 'Asia/Shanghai',
      });
    });
    expect(mockGetDashboardCourseDetail).toHaveBeenCalledTimes(1);
  });
});

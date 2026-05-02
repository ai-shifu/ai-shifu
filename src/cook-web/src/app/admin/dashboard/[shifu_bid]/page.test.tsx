import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { ErrorWithCode } from '@/lib/request';

import AdminDashboardCourseDetailPage from './page';
import { buildAdminOrdersUrl } from '../admin-dashboard-routes';

let mockParams: { shifu_bid?: string | string[] } = {
  shifu_bid: 'shifu-1',
};
const mockPush = jest.fn();

const mockGetDashboardCourseDetail = api.getDashboardCourseDetail as jest.Mock;
const mockTranslate = (key: string) => key;

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

jest.mock('@/components/charts/EChart', () => ({
  __esModule: true,
  default: ({ option }: { option: unknown }) => (
    <div
      data-testid='section-learning-chart'
      data-option={JSON.stringify(option)}
    />
  ),
}));

const getRenderedChartOption = () =>
  JSON.parse(
    screen.getByTestId('section-learning-chart').dataset.option || '{}',
  );

describe('AdminDashboardCourseDetailPage', () => {
  beforeEach(() => {
    mockParams = { shifu_bid: 'shifu-1' };
    mockGetDashboardCourseDetail.mockReset();
    mockPush.mockReset();
  });

  test('renders real course detail with section learning stacked bar chart', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue({
      basic_info: {
        shifu_bid: 'shifu-1',
        course_name: 'Course 1',
        created_at: '2025-01-01T08:00:00',
        created_at_display: '2025-01-01 16:00:00',
        chapter_count: 3,
        learner_count: 2,
      },
      metrics: {
        order_count: 3,
        order_amount: '99.00',
        completed_learner_count: 1,
        completion_rate: '50.00',
        active_learner_count_last_7_days: 1,
        total_follow_up_count: 8,
        avg_follow_up_count_per_learner: '4.00',
        avg_learning_duration_seconds: 3661,
      },
      charts: {
        sections: [
          {
            chapter_outline_item_bid: 'chapter-1',
            chapter_title: 'Chapter 1',
            section_outline_item_bid: 'lesson-1',
            section_title: 'Lesson 1',
            position: '1.1',
            learning_user_count: 10,
            learning_record_count: 25,
            follow_up_user_count: 3,
            follow_up_question_count: 8,
          },
          {
            chapter_outline_item_bid: 'chapter-1',
            chapter_title: 'Chapter 1',
            section_outline_item_bid: 'lesson-2',
            section_title: 'Lesson 2',
            position: '1.2',
            learning_user_count: 5,
            learning_record_count: 12,
            follow_up_user_count: 0,
            follow_up_question_count: 0,
          },
        ],
      },
    });

    render(<AdminDashboardCourseDetailPage />);

    await waitFor(() => {
      expect(mockGetDashboardCourseDetail).toHaveBeenCalledWith({
        shifu_bid: 'shifu-1',
        timezone: 'Asia/Shanghai',
      });
    });

    expect(screen.getByText('module.dashboard.title')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.dashboard.detail.title').length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('Course 1')).toBeInTheDocument();
    expect(screen.getByText('2025-01-01 16:00:00')).toBeInTheDocument();
    expect(screen.getByText('¥99.00')).toBeInTheDocument();
    expect(screen.getByText('50.00%')).toBeInTheDocument();
    expect(screen.getByText('4.00')).toBeInTheDocument();
    expect(screen.getByText('01:01:01')).toBeInTheDocument();

    expect(
      screen.getByText('module.dashboard.detail.metrics.orderCount'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.metrics.orderAmount'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.metrics.avgLearningDuration'),
    ).toBeInTheDocument();

    expect(
      screen.getByText('module.dashboard.detail.charts.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.charts.sectionLearningTitle'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('section-learning-chart')).toBeInTheDocument();

    const option = getRenderedChartOption();
    expect(option.series).toHaveLength(4);
    expect(option.series[0].name).toBe(
      'module.dashboard.detail.charts.learningUserCount',
    );
    expect(option.series[1].name).toBe(
      'module.dashboard.detail.charts.learningRecordCount',
    );
    expect(option.series[2].name).toBe(
      'module.dashboard.detail.charts.followUpUserCount',
    );
    expect(option.series[3].name).toBe(
      'module.dashboard.detail.charts.followUpQuestionCount',
    );
    expect(option.series[0].data).toEqual([10, 5]);
    expect(option.series[1].data).toEqual([25, 12]);
    expect(option.series[2].data).toEqual([3, 0]);
    expect(option.series[3].data).toEqual([8, 0]);
    expect(option.xAxis.data).toEqual(['Lesson 1', 'Lesson 2']);
    expect(option.series[0].stack).toBe('total');
    expect(option.series[1].stack).toBe('total');
    expect(option.series[2].stack).toBe('total');
    expect(option.series[3].stack).toBe('total');

    expect(
      screen.getByText('module.dashboard.detail.learners.empty'),
    ).toBeInTheDocument();
  });

  test('navigates to order list from order count and order amount', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue({
      basic_info: {
        shifu_bid: 'shifu-1',
        course_name: 'Course 1',
        created_at: '2025-01-01T08:00:00',
        created_at_display: '2025-01-01 16:00:00',
        chapter_count: 3,
        learner_count: 2,
      },
      metrics: {
        order_count: 3,
        order_amount: '99.00',
        completed_learner_count: 1,
        completion_rate: '50.00',
        active_learner_count_last_7_days: 1,
        total_follow_up_count: 8,
        avg_follow_up_count_per_learner: '4.00',
        avg_learning_duration_seconds: 3661,
      },
      charts: {
        sections: [],
      },
    });

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

  test('renders error state and retries fetching detail', async () => {
    mockGetDashboardCourseDetail
      .mockRejectedValueOnce(new ErrorWithCode('detail failed', 404))
      .mockResolvedValueOnce({
        basic_info: {
          shifu_bid: 'shifu-1',
          course_name: 'Recovered Course',
          created_at: '',
          created_at_display: '',
          chapter_count: 0,
          learner_count: 0,
        },
        metrics: {
          order_count: 0,
          order_amount: '0.00',
          completed_learner_count: 0,
          completion_rate: '0.00',
          active_learner_count_last_7_days: 0,
          total_follow_up_count: 0,
          avg_follow_up_count_per_learner: '0.00',
          avg_learning_duration_seconds: 0,
        },
        charts: {
          sections: [],
        },
      });

    render(<AdminDashboardCourseDetailPage />);

    expect(await screen.findByText('detail failed')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'retry' }));

    await waitFor(() => {
      expect(mockGetDashboardCourseDetail).toHaveBeenCalledTimes(2);
    });

    expect(await screen.findByText('Recovered Course')).toBeInTheDocument();
  });
});

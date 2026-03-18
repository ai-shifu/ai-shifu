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
const mockTranslate = (
  key: string,
  options?: Record<string, string | number>,
) => {
  if (!options || Object.keys(options).length === 0) {
    return key;
  }
  if ('count' in options) {
    return `${key}:${options.count}`;
  }
  return `${key}:${JSON.stringify(options)}`;
};
const mockEChart = jest.fn();
const RETRY_LABEL = 'retry';

const buildDetailResponse = (
  overrides: Partial<Record<string, unknown>> = {},
) => ({
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
    questions_by_chapter: [
      { outline_item_bid: 'lesson-1', title: 'Lesson 1', ask_count: 5 },
      { outline_item_bid: 'lesson-2', title: 'Lesson 2', ask_count: 3 },
      { outline_item_bid: 'lesson-3', title: 'Lesson 3', ask_count: 0 },
    ],
    questions_by_time: [],
    learning_activity_trend: [],
    chapter_progress_distribution: [],
  },
  learners: {
    page: 1,
    page_size: 20,
    total: 2,
    items: [],
  },
  applied_range: {
    start_date: '',
    end_date: '',
  },
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

jest.mock('@/components/charts/EChart', () => ({
  __esModule: true,
  default: (props: { option: any; className?: string }) => {
    mockEChart(props);
    const xAxis = Array.isArray(props.option?.xAxis)
      ? props.option.xAxis[0]
      : props.option?.xAxis;
    const yAxis = Array.isArray(props.option?.yAxis)
      ? props.option.yAxis[0]
      : props.option?.yAxis;
    const series = Array.isArray(props.option?.series)
      ? props.option.series[0]
      : props.option?.series;
    const categoryAxis = xAxis?.type === 'category' ? xAxis : yAxis;
    const valueAxis = xAxis?.type === 'value' ? xAxis : yAxis;
    const seriesValues = Array.isArray(series?.data)
      ? series.data.map((item: any) =>
          item && typeof item === 'object' && 'value' in item
            ? item.value
            : item,
        )
      : [];
    const highlightedBarCount = Array.isArray(series?.data)
      ? series.data.filter(
          (item: any) =>
            item &&
            typeof item === 'object' &&
            item.itemStyle?.color === '#f59e0b',
        ).length
      : 0;
    const tooltipPreview =
      typeof props.option?.tooltip?.formatter === 'function'
        ? props.option.tooltip.formatter({ dataIndex: 0 })
        : '';
    return (
      <div data-testid='questions-by-chapter-chart'>
        {JSON.stringify({
          seriesType: series?.type || '',
          categories: categoryAxis?.data || [],
          values: seriesValues,
          valueAxisMin: valueAxis?.min ?? null,
          valueAxisMax: valueAxis?.max ?? null,
          valueAxisMinInterval: valueAxis?.minInterval ?? null,
          highlightedBarCount,
          showBackground: Boolean(series?.showBackground),
          tooltipPreview,
        })}
      </div>
    );
  },
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
      <button onClick={onRetry}>{RETRY_LABEL}</button>
    </div>
  ),
}));

describe('AdminDashboardCourseDetailPage', () => {
  const manyChapterItems = [
    { outline_item_bid: 'lesson-a', title: 'Lesson A', ask_count: 2 },
    { outline_item_bid: 'lesson-b', title: 'Lesson B', ask_count: 10 },
    { outline_item_bid: 'lesson-c', title: 'Lesson C', ask_count: 4 },
    { outline_item_bid: 'lesson-d', title: 'Lesson D', ask_count: 10 },
    { outline_item_bid: 'lesson-e', title: 'Lesson E', ask_count: 1 },
    { outline_item_bid: 'lesson-f', title: 'Lesson F', ask_count: 8 },
    { outline_item_bid: 'lesson-g', title: 'Lesson G', ask_count: 0 },
    { outline_item_bid: 'lesson-h', title: 'Lesson H', ask_count: 6 },
    { outline_item_bid: 'lesson-i', title: 'Lesson I', ask_count: 3 },
    { outline_item_bid: 'lesson-j', title: 'Lesson J', ask_count: 9 },
    { outline_item_bid: 'lesson-k', title: 'Lesson K', ask_count: 5 },
    { outline_item_bid: 'lesson-l', title: 'Lesson L', ask_count: 7 },
  ];

  beforeEach(() => {
    mockParams = { shifu_bid: 'shifu-1' };
    mockGetDashboardCourseDetail.mockReset();
    mockPush.mockReset();
    mockEChart.mockReset();
  });

  test('renders real course detail data and charts with a single detail request', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(buildDetailResponse());

    render(<AdminDashboardCourseDetailPage />);

    await waitFor(() => {
      expect(mockGetDashboardCourseDetail).toHaveBeenCalledWith({
        shifu_bid: 'shifu-1',
        timezone: 'Asia/Shanghai',
      });
    });
    expect(mockGetDashboardCourseDetail).toHaveBeenCalledTimes(1);

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
      await screen.findByTestId('questions-by-chapter-chart'),
    ).toHaveTextContent(
      JSON.stringify({
        seriesType: 'bar',
        categories: ['Lesson 1', 'Lesson 2', 'Lesson 3'],
        values: [5, 3, 0],
        valueAxisMin: 0,
        valueAxisMax: null,
        valueAxisMinInterval: 1,
        highlightedBarCount: 2,
        showBackground: true,
        tooltipPreview: 'Lesson 1<br/>module.dashboard.detail.charts.questionCount: 5',
      }),
    );
    expect(
      screen.getByText('module.dashboard.detail.charts.title'),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('module.dashboard.detail.charts.placeholder').length,
    ).toBe(3);
    expect(
      screen.queryByRole('button', {
        name: 'module.dashboard.detail.charts.viewAllChapters',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.learners.empty'),
    ).toBeInTheDocument();
  });

  test('navigates to order list from order count and order amount', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(buildDetailResponse());

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
      .mockResolvedValueOnce(
        buildDetailResponse({
          basic_info: {
            shifu_bid: 'shifu-1',
            course_name: 'Recovered Course',
            created_at: '',
            created_at_display: '',
            chapter_count: 0,
            learner_count: 0,
          },
        }),
      );

    render(<AdminDashboardCourseDetailPage />);

    expect(await screen.findByText('detail failed')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: RETRY_LABEL }));

    await waitFor(() => {
      expect(mockGetDashboardCourseDetail).toHaveBeenCalledTimes(2);
    });

    expect(await screen.findByText('Recovered Course')).toBeInTheDocument();
  });

  test('renders zero state chart when questions by chapter are all zero', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(
      buildDetailResponse({
        charts: {
          questions_by_chapter: [
            { outline_item_bid: 'lesson-1', title: 'Lesson 1', ask_count: 0 },
            { outline_item_bid: 'lesson-2', title: 'Lesson 2', ask_count: 0 },
          ],
          questions_by_time: [],
          learning_activity_trend: [],
          chapter_progress_distribution: [],
        },
      }),
    );

    render(<AdminDashboardCourseDetailPage />);

    expect(
      await screen.findByTestId('questions-by-chapter-chart'),
    ).toHaveTextContent(
      JSON.stringify({
        seriesType: 'bar',
        categories: ['Lesson 1', 'Lesson 2'],
        values: [0, 0],
        valueAxisMin: 0,
        valueAxisMax: 1,
        valueAxisMinInterval: 1,
        highlightedBarCount: 0,
        showBackground: true,
        tooltipPreview: 'Lesson 1<br/>module.dashboard.detail.charts.questionCount: 0',
      }),
    );
    expect(
      screen.getAllByText('module.dashboard.detail.charts.placeholder').length,
    ).toBe(3);
  });

  test('renders top 10 chapters by descending ask count and opens all chapters dialog', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(
      buildDetailResponse({
        charts: {
          questions_by_chapter: manyChapterItems,
          questions_by_time: [],
          learning_activity_trend: [],
          chapter_progress_distribution: [],
        },
      }),
    );

    render(<AdminDashboardCourseDetailPage />);

    expect(
      await screen.findByTestId('questions-by-chapter-chart'),
    ).toHaveTextContent(
      JSON.stringify({
        seriesType: 'bar',
        categories: [
          'Lesson B',
          'Lesson D',
          'Lesson J',
          'Lesson F',
          'Lesson L',
          'Lesson H',
          'Lesson K',
          'Lesson C',
          'Lesson I',
          'Lesson A',
        ],
        values: [10, 10, 9, 8, 7, 6, 5, 4, 3, 2],
        valueAxisMin: 0,
        valueAxisMax: null,
        valueAxisMinInterval: 1,
        highlightedBarCount: 3,
        showBackground: true,
        tooltipPreview:
          'Lesson B<br/>module.dashboard.detail.charts.questionCount: 10',
      }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.detail.charts.viewAllChapters',
      }),
    );

    expect(
      await screen.findByText(
        'module.dashboard.detail.charts.allChaptersDialogTitle',
      ),
    ).toBeInTheDocument();

    const chartInstances = await screen.findAllByTestId(
      'questions-by-chapter-chart',
    );

    expect(chartInstances).toHaveLength(2);
    expect(chartInstances[1]).toHaveTextContent(
      JSON.stringify({
        seriesType: 'bar',
        categories: [
          'Lesson B',
          'Lesson D',
          'Lesson J',
          'Lesson F',
          'Lesson L',
          'Lesson H',
          'Lesson K',
          'Lesson C',
          'Lesson I',
          'Lesson A',
          'Lesson E',
          'Lesson G',
        ],
        values: [10, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
        valueAxisMin: 0,
        valueAxisMax: null,
        valueAxisMinInterval: 1,
        highlightedBarCount: 3,
        showBackground: true,
        tooltipPreview:
          'Lesson B<br/>module.dashboard.detail.charts.questionCount: 10',
      }),
    );
  });

  test('falls back to placeholder when questions by chapter data is empty', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue(
      buildDetailResponse({
        charts: {
          questions_by_chapter: [],
          questions_by_time: [],
          learning_activity_trend: [],
          chapter_progress_distribution: [],
        },
      }),
    );

    render(<AdminDashboardCourseDetailPage />);

    await waitFor(() => {
      expect(mockGetDashboardCourseDetail).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getAllByText('module.dashboard.detail.charts.placeholder').length,
    ).toBe(4);
    expect(
      screen.queryByTestId('questions-by-chapter-chart'),
    ).not.toBeInTheDocument();
  });
});

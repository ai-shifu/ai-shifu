import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { ErrorWithCode } from '@/lib/request';

import AdminDashboardCourseDetailPage from './page';

let mockParams: { shifu_bid?: string | string[] } = {
  shifu_bid: 'shifu-1',
};

const mockGetDashboardCourseDetail = api.getDashboardCourseDetail as jest.Mock;
const mockTranslate = (key: string) => key;

jest.mock('next/navigation', () => ({
  useParams: () => mockParams,
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

describe('AdminDashboardCourseDetailPage', () => {
  const dateToLocaleStringSpy = jest.spyOn(Date.prototype, 'toLocaleString');

  beforeEach(() => {
    mockParams = { shifu_bid: 'shifu-1' };
    mockGetDashboardCourseDetail.mockReset();
    dateToLocaleStringSpy.mockReturnValue('formatted-date');
  });

  afterAll(() => {
    dateToLocaleStringSpy.mockRestore();
  });

  test('renders real course detail data and keeps placeholder sections', async () => {
    mockGetDashboardCourseDetail.mockResolvedValue({
      basic_info: {
        shifu_bid: 'shifu-1',
        course_name: 'Course 1',
        created_at: '2025-01-01T08:00:00',
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
    });

    render(<AdminDashboardCourseDetailPage />);

    await waitFor(() => {
      expect(mockGetDashboardCourseDetail).toHaveBeenCalledWith({
        shifu_bid: 'shifu-1',
      });
    });

    expect(screen.getByText('module.dashboard.title')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.dashboard.detail.title').length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('Course 1')).toBeInTheDocument();
    expect(screen.getByText('formatted-date')).toBeInTheDocument();
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
      screen.getAllByText('module.dashboard.detail.charts.placeholder').length,
    ).toBe(4);
    expect(
      screen.getByText('module.dashboard.detail.learners.empty'),
    ).toBeInTheDocument();
  });

  test('renders error state and retries fetching detail', async () => {
    mockGetDashboardCourseDetail
      .mockRejectedValueOnce(new ErrorWithCode('detail failed', 404))
      .mockResolvedValueOnce({
        basic_info: {
          shifu_bid: 'shifu-1',
          course_name: 'Recovered Course',
          created_at: '',
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

import React from 'react';
import { render, screen } from '@testing-library/react';

import AdminDashboardCourseDetailPage from './page';

let mockParams: { shifu_bid?: string | string[] } = {
  shifu_bid: 'shifu-1',
};

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

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

describe('AdminDashboardCourseDetailPage', () => {
  beforeEach(() => {
    mockParams = { shifu_bid: 'shifu-1' };
  });

  test('renders the course detail shell sections', () => {
    render(<AdminDashboardCourseDetailPage />);

    expect(screen.getByText('module.dashboard.title')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.dashboard.detail.title').length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText('module.dashboard.detail.courseIdLabel'),
    ).toBeInTheDocument();
    expect(screen.getByText('shifu-1')).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.subtitle'),
    ).toBeInTheDocument();

    expect(
      screen.getByText('module.dashboard.detail.basicInfo.title'),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('module.dashboard.detail.placeholderValue').length,
    ).toBeGreaterThan(0);

    expect(
      screen.getByText('module.dashboard.detail.metrics.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.metrics.totalLearners'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.metrics.completionRate'),
    ).toBeInTheDocument();

    expect(
      screen.getByText('module.dashboard.detail.charts.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.charts.questionsByChapter'),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('module.dashboard.detail.charts.placeholder').length,
    ).toBe(4);

    expect(
      screen.getByText('module.dashboard.detail.learners.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.learners.columns.name'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.learners.empty'),
    ).toBeInTheDocument();
  });
});

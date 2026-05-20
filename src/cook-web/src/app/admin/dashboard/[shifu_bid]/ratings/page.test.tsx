import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AdminDashboardCourseRatingsPage from './page';

const mockGetDashboardCourseRatings = jest.fn();
const mockTranslationCache = new Map<
  string,
  {
    t: (key: string, options?: { count?: number; score?: number }) => string;
    i18n: { language: string };
  }
>();
const mockBrowserTimeZone = jest.fn(() => 'Asia/Shanghai');
const mockEnvState = {
  loginMethodsEnabled: ['phone'],
  defaultLoginMethod: 'phone',
};
const mockUserState = {
  isInitialized: true,
  isGuest: false,
};

jest.mock('next/navigation', () => ({
  useParams: () => ({
    shifu_bid: 'course-1',
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
    getDashboardCourseRatings: (...args: unknown[]) =>
      mockGetDashboardCourseRatings(...args),
  },
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserState) => unknown) =>
    selector(mockUserState),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      loginMethodsEnabled: string[];
      defaultLoginMethod: string;
    }) => unknown,
  ) => selector(mockEnvState),
}));

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => mockBrowserTimeZone(),
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => {
    const ns = Array.isArray(namespace) ? namespace[0] : namespace;
    const cacheKey = ns || 'translation';
    if (!mockTranslationCache.has(cacheKey)) {
      mockTranslationCache.set(cacheKey, {
        t: (key: string, options?: { count?: number; score?: number }) => {
          if (typeof options?.count === 'number') {
            return `${key}:${options.count}`;
          }
          if (typeof options?.score === 'number') {
            return `${key}:${options.score}`;
          }
          return ns && ns !== 'translation' ? `${ns}.${key}` : key;
        },
        i18n: { language: 'en-US' },
      });
    }
    return mockTranslationCache.get(cacheKey)!;
  },
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/app/admin/components/AdminTooltipText', () => ({
  __esModule: true,
  default: ({ text, emptyValue }: { text?: string; emptyValue: string }) => (
    <span>{text || emptyValue}</span>
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
      onClick={() => onChange({ start: '2026-04-05', end: '2026-04-06' })}
    >
      {placeholder}
    </button>
  ),
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
        onClick={() => onValueChange?.('5')}
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

describe('AdminDashboardCourseRatingsPage', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    mockGetDashboardCourseRatings.mockReset();
    mockBrowserTimeZone.mockReset();
    mockBrowserTimeZone.mockReturnValue('Asia/Shanghai');
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockEnvState.defaultLoginMethod = 'phone';
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockGetDashboardCourseRatings.mockResolvedValue({
      summary: {
        average_score: '4.0',
        rating_count: 2,
        user_count: 2,
        latest_rated_at: '2026-04-06 17:05:00',
      },
      items: [
        {
          lesson_feedback_bid: 'feedback-2',
          progress_record_bid: 'progress-2',
          user_bid: 'user-2',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_title: 'Chapter 2',
          lesson_title: 'Lesson 2',
          score: 4,
          comment: 'Helpful examples',
          rated_at: '2026-04-06 17:05:00',
        },
      ],
      page: 1,
      page_size: 20,
      total: 2,
      page_count: 1,
    });

    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        href: 'http://localhost/admin/dashboard/course-1/ratings',
        pathname: '/admin/dashboard/course-1/ratings',
        search: '',
      },
    });
  });

  afterAll(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  test('renders ratings list with breadcrumbs back to dashboard and course detail', async () => {
    render(<AdminDashboardCourseRatingsPage />);

    expect(
      (await screen.findAllByText('module.dashboard.detail.ratings.title'))
        .length,
    ).toBeGreaterThan(0);

    await waitFor(() => {
      expect(mockGetDashboardCourseRatings).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page_index: 1,
        page_size: 20,
        keyword: '',
        chapter_keyword: '',
        score: '',
        has_comment: '',
        start_time: '',
        end_time: '',
        timezone: 'Asia/Shanghai',
      });
    });

    expect(
      screen.getByText('module.dashboard.title').closest('a'),
    ).toHaveAttribute('href', '/admin/dashboard');
    expect(
      screen.getByText('module.dashboard.detail.title').closest('a'),
    ).toHaveAttribute('href', '/admin/dashboard/course-1');
    expect(
      screen.getByText('module.dashboard.detail.ratings.summary.averageScore'),
    ).toBeInTheDocument();
    expect(screen.getByText('4.0')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Lesson 2')).toBeInTheDocument();
    expect(screen.getByText('Chapter 2')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.dashboard.detail.ratings.scoreValue:4')
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('Helpful examples')).toBeInTheDocument();
  });

  test('supports rating filters and email placeholder mode', async () => {
    mockEnvState.loginMethodsEnabled = ['email'];
    mockEnvState.defaultLoginMethod = 'email';

    render(<AdminDashboardCourseRatingsPage />);

    expect(
      (await screen.findAllByText('module.dashboard.detail.ratings.title'))
        .length,
    ).toBeGreaterThan(0);

    expect(
      screen.getByPlaceholderText(
        'module.dashboard.detail.ratings.filters.userKeywordPlaceholderEmail',
      ),
    ).toBeInTheDocument();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.dashboard.detail.ratings.filters.userKeywordPlaceholderEmail',
      ),
      { target: { value: 'alice@example.com' } },
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.dashboard.detail.ratings.filters.chapterKeywordPlaceholder',
      ),
      { target: { value: 'Chapter 1' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.detail.ratings.filters.timePlaceholder',
      }),
    );
    fireEvent.click(screen.getAllByText('all')[0]);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.detail.ratings.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetDashboardCourseRatings).toHaveBeenLastCalledWith({
        shifu_bid: 'course-1',
        page_index: 1,
        page_size: 20,
        keyword: 'alice@example.com',
        chapter_keyword: 'Chapter 1',
        score: '5',
        has_comment: '',
        start_time: '2026-04-05',
        end_time: '2026-04-06',
        timezone: 'Asia/Shanghai',
      });
    });
  });

  test('redirects guests to login instead of staying on the loading state', async () => {
    mockUserState.isGuest = true;

    render(<AdminDashboardCourseRatingsPage />);

    await waitFor(() => {
      expect(window.location.href).toBe(
        '/login?redirect=%2Fadmin%2Fdashboard%2Fcourse-1%2Fratings',
      );
    });

    expect(mockGetDashboardCourseRatings).not.toHaveBeenCalled();
  });
});

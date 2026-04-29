import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AdminOperationCourseRatingsPage from './page';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockGetAdminOperationCourseRatings = jest.fn();
const mockTranslationCache = new Map<string, { t: (key: string) => string }>();
const mockEnvState = {
  loginMethodsEnabled: ['phone'],
  defaultLoginMethod: 'phone',
};
const mockUserState = {
  isInitialized: true,
  isGuest: false,
  userInfo: {
    is_operator: true,
  },
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
    push: mockPush,
  }),
  useParams: () => ({
    shifu_bid: 'course-1',
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCourseRatings: (...args: unknown[]) =>
      mockGetAdminOperationCourseRatings(...args),
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

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => {
    const ns = Array.isArray(namespace) ? namespace[0] : namespace;
    const cacheKey = ns || 'translation';
    if (!mockTranslationCache.has(cacheKey)) {
      mockTranslationCache.set(cacheKey, {
        t: (key: string) => (ns && ns !== 'translation' ? `${ns}.${key}` : key),
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

describe('AdminOperationCourseRatingsPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    mockGetAdminOperationCourseRatings.mockReset();
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockEnvState.defaultLoginMethod = 'phone';
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = {
      is_operator: true,
    };
    mockGetAdminOperationCourseRatings.mockResolvedValue({
      summary: {
        average_score: '4.5',
        rating_count: 2,
        user_count: 1,
        latest_rated_at: '2026-04-05T11:02:00Z',
      },
      items: [
        {
          lesson_feedback_bid: 'feedback-2',
          progress_record_bid: 'progress-1',
          user_bid: 'student-1',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          score: 5,
          comment: 'Very helpful lesson',
          mode: 'read',
          rated_at: '2026-04-05T11:02:00Z',
        },
        {
          lesson_feedback_bid: 'feedback-1',
          progress_record_bid: 'progress-2',
          user_bid: 'student-1',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          score: 4,
          comment: '',
          mode: 'listen',
          rated_at: '2026-04-04T11:02:00Z',
        },
      ],
      page: 1,
      page_size: 20,
      total: 2,
      page_count: 1,
    });
  });

  test('renders rating list and can return to course detail', async () => {
    render(<AdminOperationCourseRatingsPage />);

    expect(
      await screen.findByText('module.operationsCourse.detail.ratings.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCourse.detail.ratings.summary.scopeHint',
      ),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetAdminOperationCourseRatings).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        keyword: '',
        chapter_keyword: '',
        score: '',
        mode: '',
        has_comment: '',
        sort_by: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(screen.getByText('Very helpful lesson')).toBeInTheDocument();
    expect(screen.getAllByText('13900001235').length).toBeGreaterThan(0);
    expect(
      screen.getAllByText('module.operationsCourse.detail.ratings.scoreValue')
        .length,
    ).toBeGreaterThan(0);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.ratings.back',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith('/admin/operations/course-1');
  });

  test('submits search filters including score, mode, comment filter, sort, and rating time', async () => {
    render(<AdminOperationCourseRatingsPage />);

    await screen.findByText('Very helpful lesson');

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.ratings.filters.userKeywordPlaceholderPhone',
      ),
      {
        target: { value: '13900001235' },
      },
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.ratings.filters.chapterKeywordPlaceholder',
      ),
      {
        target: { value: 'Chapter 1' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.ratings.filters.timePlaceholder',
      }),
    );
    fireEvent.click(
      screen.getAllByText(
        'module.operationsCourse.detail.ratings.scoreValue',
      )[0],
    );
    fireEvent.click(
      screen.getAllByText(
        'module.operationsCourse.detail.ratings.modes.read',
      )[0],
    );
    fireEvent.click(
      screen.getByText(
        'module.operationsCourse.detail.ratings.filters.commentStatusCommented',
      ),
    );
    fireEvent.click(
      screen.getByText(
        'module.operationsCourse.detail.ratings.filters.sortByLowScore',
      ),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.ratings.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCourseRatings).toHaveBeenLastCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        keyword: '13900001235',
        chapter_keyword: 'Chapter 1',
        score: '5',
        mode: 'read',
        has_comment: 'true',
        sort_by: 'score_asc',
        start_time: '2026-04-05',
        end_time: '2026-04-06',
      });
    });
  });

  test('uses email-specific placeholder when email login is preferred', async () => {
    mockEnvState.loginMethodsEnabled = ['email'];
    mockEnvState.defaultLoginMethod = 'email';

    render(<AdminOperationCourseRatingsPage />);

    await screen.findByText('module.operationsCourse.detail.ratings.title');

    expect(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.ratings.filters.userKeywordPlaceholderEmail',
      ),
    ).toBeInTheDocument();
  });

  test('shows guest label when user has no contact info', async () => {
    mockGetAdminOperationCourseRatings.mockResolvedValueOnce({
      summary: {
        average_score: '4.0',
        rating_count: 1,
        user_count: 1,
        latest_rated_at: '2026-04-05T11:02:00Z',
      },
      items: [
        {
          lesson_feedback_bid: 'feedback-guest-1',
          progress_record_bid: 'progress-guest-1',
          user_bid: 'guest-1',
          mobile: '',
          email: '',
          nickname: '',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          score: 4,
          comment: 'Guest rating',
          mode: 'read',
          rated_at: '2026-04-05T11:02:00Z',
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
      page_count: 1,
    });

    render(<AdminOperationCourseRatingsPage />);

    await screen.findByText('Guest rating');

    expect(
      screen.getByText(
        'module.operationsCourse.detail.ratings.table.guestUser',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('--')).not.toBeInTheDocument();
  });
});

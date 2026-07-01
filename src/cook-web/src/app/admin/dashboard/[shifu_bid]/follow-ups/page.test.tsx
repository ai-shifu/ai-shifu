import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import AdminDashboardCourseFollowUpsPage from './page';

const mockGetDashboardCourseFollowUps = jest.fn();
const mockGetDashboardCourseFollowUpDetail = jest.fn();
const mockTranslationCache = new Map<
  string,
  { t: (key: string, options?: { count?: number }) => string }
>();
const mockBrowserTimeZone = jest.fn(() => 'Asia/Shanghai');
let mockSearchParams = new URLSearchParams();
const SHEET_CLOSE_LABEL = 'close-sheet';
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
  useSearchParams: () => mockSearchParams,
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
    getDashboardCourseFollowUps: (...args: unknown[]) =>
      mockGetDashboardCourseFollowUps(...args),
    getDashboardCourseFollowUpDetail: (...args: unknown[]) =>
      mockGetDashboardCourseFollowUpDetail(...args),
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
        t: (key: string, options?: { count?: number }) => {
          if (typeof options?.count === 'number') {
            return `${key}:${options.count}`;
          }
          return ns && ns !== 'translation' ? `${ns}.${key}` : key;
        },
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

jest.mock('@/components/ui/Sheet', () => ({
  __esModule: true,
  Sheet: ({
    open,
    onOpenChange,
    children,
  }: React.PropsWithChildren<{
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
  }>) =>
    open ? (
      <div>
        <button
          type='button'
          onClick={() => onOpenChange?.(false)}
        >
          {SHEET_CLOSE_LABEL}
        </button>
        {children}
      </div>
    ) : null,
  SheetContent: ({ children }: React.PropsWithChildren) => (
    <div role='dialog'>{children}</div>
  ),
  SheetHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SheetTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
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

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('AdminDashboardCourseFollowUpsPage', () => {
  beforeEach(() => {
    mockGetDashboardCourseFollowUps.mockReset();
    mockGetDashboardCourseFollowUpDetail.mockReset();
    mockBrowserTimeZone.mockReset();
    mockBrowserTimeZone.mockReturnValue('Asia/Shanghai');
    mockSearchParams = new URLSearchParams();
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockEnvState.defaultLoginMethod = 'phone';
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockGetDashboardCourseFollowUps.mockResolvedValue({
      summary: {
        follow_up_count: 2,
        user_count: 1,
        lesson_count: 1,
        latest_follow_up_at: '2026-04-05T11:02:00Z',
      },
      items: [
        {
          generated_block_bid: 'ask-2',
          progress_record_bid: 'progress-1',
          user_bid: 'student-1',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_title: 'Chapter 1',
          lesson_title: 'Lesson 1',
          follow_up_content: 'Second follow-up question',
          has_source_output: true,
          turn_index: 2,
          created_at: '2026-04-05T11:02:00Z',
        },
        {
          generated_block_bid: 'ask-3',
          progress_record_bid: 'progress-1',
          user_bid: 'student-1',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_title: 'Chapter 1',
          lesson_title: 'Lesson 2',
          follow_up_content: 'Third follow-up question',
          has_source_output: false,
          turn_index: 3,
          created_at: '2026-04-05 19:05:00',
        },
      ],
      page: 1,
      page_size: 20,
      total: 2,
      page_count: 1,
    });
    mockGetDashboardCourseFollowUpDetail.mockImplementation(
      async ({ generated_block_bid }: { generated_block_bid: string }) => {
        if (generated_block_bid === 'ask-3') {
          return {
            basic_info: {
              generated_block_bid: 'ask-3',
              progress_record_bid: 'progress-1',
              user_bid: 'student-1',
              mobile: '13900001235',
              email: '',
              nickname: 'Bob',
              chapter_title: 'Chapter 1',
              lesson_title: 'Lesson 2',
              created_at: '2026-04-05T11:05:00Z',
              turn_index: 3,
            },
            current_record: {
              follow_up_content: 'Third follow-up question',
              answer_content: 'Third follow-up answer',
            },
            timeline: [
              {
                role: 'student',
                content: 'Third follow-up question',
                created_at: '2026-04-05T11:05:00Z',
                is_current: true,
              },
              {
                role: 'teacher',
                content: 'Third follow-up answer',
                created_at: '2026-04-05T11:05:08Z',
                is_current: true,
              },
            ],
          };
        }
        return {
          basic_info: {
            generated_block_bid: 'ask-2',
            progress_record_bid: 'progress-1',
            user_bid: 'student-1',
            mobile: '13900001235',
            email: '',
            nickname: 'Bob',
            chapter_title: 'Chapter 1',
            lesson_title: 'Lesson 1',
            created_at: '2026-04-05T11:02:00Z',
            turn_index: 2,
          },
          current_record: {
            follow_up_content: 'Second follow-up question',
            answer_content: 'Second follow-up answer',
          },
          timeline: [
            {
              role: 'student',
              content: 'Second follow-up question',
              created_at: '2026-04-05T11:02:00Z',
              is_current: true,
            },
            {
              role: 'teacher',
              content: 'Second follow-up answer',
              created_at: '2026-04-05T11:02:10Z',
              is_current: true,
            },
          ],
        };
      },
    );
  });

  test('renders follow-up list with breadcrumbs back to dashboard and course detail', async () => {
    render(<AdminDashboardCourseFollowUpsPage />);

    expect(
      (await screen.findAllByText('module.dashboard.detail.followUps.title'))
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText('module.dashboard.detail.followUps.turnIndexHelp'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.dashboard.detail.followUps.summary.scopeHint'),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetDashboardCourseFollowUps).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page_index: 1,
        page_size: 20,
        user_bid: '',
        keyword: '',
        chapter_keyword: '',
        source_status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(
      screen.getByText('module.dashboard.title').closest('a'),
    ).toHaveAttribute('href', '/admin/dashboard');
    expect(
      screen.getAllByText('module.dashboard.detail.title')[0].closest('a'),
    ).toHaveAttribute('href', '/admin/dashboard/course-1');
    expect(screen.getByText('Second follow-up question')).toBeInTheDocument();
    expect(screen.getAllByText('13900001235').length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        'module.dashboard.detail.followUps.table.sourceResolved',
      ),
    ).toBeInTheDocument();
  });

  test('submits filters and opens the detail drawer', async () => {
    render(<AdminDashboardCourseFollowUpsPage />);

    await screen.findByText('Second follow-up question');
    mockGetDashboardCourseFollowUps.mockClear();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.dashboard.detail.followUps.filters.userKeywordPlaceholderPhone',
      ),
      {
        target: { value: 'student' },
      },
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.dashboard.detail.followUps.filters.chapterKeywordPlaceholder',
      ),
      {
        target: { value: 'Lesson 1' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.detail.followUps.filters.sourceStatusMissing',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.detail.followUps.filters.timePlaceholder',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.dashboard.detail.followUps.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetDashboardCourseFollowUps).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page_index: 1,
        page_size: 20,
        user_bid: '',
        keyword: 'student',
        chapter_keyword: 'Lesson 1',
        source_status: 'missing',
        start_time: '2026-04-05',
        end_time: '2026-04-06',
      });
    });

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.dashboard.detail.followUps.table.detailAction',
      })[0],
    );

    expect(
      await screen.findByText('module.dashboard.detail.followUps.drawer.title'),
    ).toBeInTheDocument();
    expect(mockGetDashboardCourseFollowUpDetail).toHaveBeenCalledWith({
      shifu_bid: 'course-1',
      generated_block_bid: 'ask-2',
    });
    expect(
      screen.getByText(
        'module.dashboard.detail.followUps.drawer.currentRecordHint',
      ),
    ).toBeInTheDocument();
    expect((await screen.findAllByText('Second follow-up answer')).length).toBe(
      2,
    );
    expect(
      screen.getAllByText(
        'module.dashboard.detail.followUps.drawer.timeline.current',
      ).length,
    ).toBeGreaterThan(0);
  });

  test('ignores a late detail response after the drawer is closed', async () => {
    const deferredDetail =
      createDeferred<
        Awaited<ReturnType<typeof mockGetDashboardCourseFollowUpDetail>>
      >();
    mockGetDashboardCourseFollowUpDetail.mockReset();
    mockGetDashboardCourseFollowUpDetail.mockImplementationOnce(
      () => deferredDetail.promise,
    );

    render(<AdminDashboardCourseFollowUpsPage />);

    await screen.findByText('Second follow-up question');

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.dashboard.detail.followUps.table.detailAction',
      })[0],
    );

    expect(await screen.findByTestId('loading-indicator')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: SHEET_CLOSE_LABEL }));

    await act(async () => {
      deferredDetail.resolve({
        basic_info: {
          generated_block_bid: 'ask-2',
          progress_record_bid: 'progress-1',
          user_bid: 'student-1',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_title: 'Chapter 1',
          lesson_title: 'Lesson 1',
          created_at: '2026-04-05T11:02:00Z',
          turn_index: 2,
        },
        current_record: {
          follow_up_content: 'Stale follow-up question',
          answer_content: 'Stale follow-up answer',
        },
        timeline: [],
      });
      await deferredDetail.promise;
    });

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(
      screen.queryByText('Stale follow-up answer'),
    ).not.toBeInTheDocument();
  });

  test('reuses cached detail when reopening the same follow-up', async () => {
    render(<AdminDashboardCourseFollowUpsPage />);

    await screen.findByText('Second follow-up question');

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.dashboard.detail.followUps.table.detailAction',
      })[0],
    );

    expect((await screen.findAllByText('Second follow-up answer')).length).toBe(
      2,
    );
    expect(mockGetDashboardCourseFollowUpDetail).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: SHEET_CLOSE_LABEL }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.dashboard.detail.followUps.table.detailAction',
      })[0],
    );

    expect((await screen.findAllByText('Second follow-up answer')).length).toBe(
      2,
    );
    expect(mockGetDashboardCourseFollowUpDetail).toHaveBeenCalledTimes(1);
  });

  test('fetches a new detail payload when opening a different follow-up', async () => {
    render(<AdminDashboardCourseFollowUpsPage />);

    await screen.findByText('Third follow-up question');

    const detailButtons = screen.getAllByRole('button', {
      name: 'module.dashboard.detail.followUps.table.detailAction',
    });

    fireEvent.click(detailButtons[0]);
    expect((await screen.findAllByText('Second follow-up answer')).length).toBe(
      2,
    );

    fireEvent.click(screen.getByRole('button', { name: SHEET_CLOSE_LABEL }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    fireEvent.click(detailButtons[1]);
    expect((await screen.findAllByText('Third follow-up answer')).length).toBe(
      2,
    );

    expect(mockGetDashboardCourseFollowUpDetail).toHaveBeenCalledTimes(2);
    expect(mockGetDashboardCourseFollowUpDetail).toHaveBeenNthCalledWith(2, {
      shifu_bid: 'course-1',
      generated_block_bid: 'ask-3',
      timezone: 'Asia/Shanghai',
    });
  });

  test('applies learner-scoped query filters from the url', async () => {
    mockSearchParams = new URLSearchParams({
      user_bid: 'student-1',
      keyword: '13900001235',
    });

    render(<AdminDashboardCourseFollowUpsPage />);

    await waitFor(() => {
      expect(mockGetDashboardCourseFollowUps).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page_index: 1,
        page_size: 20,
        user_bid: 'student-1',
        keyword: '13900001235',
        chapter_keyword: '',
        source_status: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(screen.getByDisplayValue('13900001235')).toBeInTheDocument();
  });
});

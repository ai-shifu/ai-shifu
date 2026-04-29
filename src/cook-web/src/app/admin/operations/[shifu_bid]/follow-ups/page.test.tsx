import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import AdminOperationCourseFollowUpsPage from './page';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockGetAdminOperationCourseFollowUps = jest.fn();
const mockGetAdminOperationCourseFollowUpDetail = jest.fn();
const mockTranslationCache = new Map<string, { t: (key: string) => string }>();
const mockBrowserTimeZone = jest.fn(() => 'UTC');
const SHEET_CLOSE_LABEL = 'close-sheet';
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
    getAdminOperationCourseFollowUps: (...args: unknown[]) =>
      mockGetAdminOperationCourseFollowUps(...args),
    getAdminOperationCourseFollowUpDetail: (...args: unknown[]) =>
      mockGetAdminOperationCourseFollowUpDetail(...args),
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

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('AdminOperationCourseFollowUpsPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    mockGetAdminOperationCourseFollowUps.mockReset();
    mockGetAdminOperationCourseFollowUpDetail.mockReset();
    mockBrowserTimeZone.mockReset();
    mockBrowserTimeZone.mockReturnValue('UTC');
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockEnvState.defaultLoginMethod = 'phone';
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = {
      is_operator: true,
    };
    mockGetAdminOperationCourseFollowUps.mockResolvedValue({
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
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          follow_up_content: 'Second follow-up question',
          turn_index: 2,
          created_at: '2026-04-05T11:02:00Z',
        },
        {
          generated_block_bid: 'ask-1',
          progress_record_bid: 'progress-1',
          user_bid: 'student-1',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          follow_up_content: 'First follow-up question',
          turn_index: 1,
          created_at: '2026-04-05T11:01:00Z',
        },
      ],
      page: 1,
      page_size: 20,
      total: 2,
      page_count: 1,
    });
    mockGetAdminOperationCourseFollowUpDetail.mockResolvedValue({
      basic_info: {
        generated_block_bid: 'ask-2',
        progress_record_bid: 'progress-1',
        user_bid: 'student-1',
        mobile: '13900001235',
        email: '',
        nickname: 'Bob',
        course_name: 'Course One',
        shifu_bid: 'course-1',
        chapter_title: 'Chapter 1',
        lesson_title: 'Lesson 1',
        created_at: '2026-04-05T11:02:00Z',
        turn_index: 2,
      },
      current_record: {
        source_output_content: 'Please tell me your current understanding.',
        source_output_type: 'interaction',
        source_position: 2,
        source_element_bid: '',
        source_element_type: '',
        follow_up_content: 'Second follow-up question',
        answer_content: 'Second follow-up answer',
      },
      timeline: [
        {
          role: 'student',
          content: 'First follow-up question',
          created_at: '2026-04-05T11:01:00Z',
          is_current: false,
        },
        {
          role: 'teacher',
          content: 'Second follow-up answer',
          created_at: '2026-04-05T11:02:02Z',
          is_current: true,
        },
      ],
    });
  });

  test('renders follow-up list and can return to course detail', async () => {
    render(<AdminOperationCourseFollowUpsPage />);

    expect(
      await screen.findByText('module.operationsCourse.detail.followUps.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.timezoneHint'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCourse.detail.followUps.summary.scopeHint',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCourse.detail.followUps.turnIndexHelp',
      ),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(mockGetAdminOperationCourseFollowUps).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        keyword: '',
        chapter_keyword: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(screen.getByText('Second follow-up question')).toBeInTheDocument();
    expect(screen.getAllByText('13900001235').length).toBeGreaterThan(0);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.followUps.back',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith('/admin/operations/course-1');
  });

  test('submits filters and opens the detail drawer', async () => {
    render(<AdminOperationCourseFollowUpsPage />);

    await screen.findByText('Second follow-up question');
    mockGetAdminOperationCourseFollowUps.mockClear();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.followUps.filters.userKeywordPlaceholderPhone',
      ),
      {
        target: { value: 'student' },
      },
    );
    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.followUps.filters.chapterKeywordPlaceholder',
      ),
      {
        target: { value: 'Lesson 1' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.followUps.filters.timeRangePlaceholder',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.followUps.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCourseFollowUps).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        keyword: 'student',
        chapter_keyword: 'Lesson 1',
        start_time: '2026-04-05',
        end_time: '2026-04-06',
      });
    });

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.operationsCourse.detail.followUps.table.detailAction',
      })[0],
    );

    expect(
      await screen.findByText(
        'module.operationsCourse.detail.followUps.drawer.title',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText('module.operationsCourse.timezoneHint'),
    ).toHaveLength(2);
    expect(
      screen.getByText(
        'module.operationsCourse.detail.followUps.drawer.currentRecordHint',
      ),
    ).toBeInTheDocument();
    expect(mockGetAdminOperationCourseFollowUpDetail).toHaveBeenCalledWith({
      shifu_bid: 'course-1',
      generated_block_bid: 'ask-2',
    });
    await waitFor(() => {
      expect(
        screen.getAllByText('Second follow-up question').length,
      ).toBeGreaterThan(0);
      expect(
        screen.getAllByText('Please tell me your current understanding.')
          .length,
      ).toBeGreaterThan(0);
      expect(
        screen.getAllByText('Second follow-up answer').length,
      ).toBeGreaterThan(0);
    });
    expect(
      screen.getByText(
        'module.operationsCourse.detail.followUps.drawer.timeline.current',
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText('Lesson 1').length).toBeGreaterThan(0);
  });

  test('shows a descriptive source fallback when original output cannot be resolved', async () => {
    mockGetAdminOperationCourseFollowUpDetail.mockResolvedValueOnce({
      basic_info: {
        generated_block_bid: 'ask-2',
        progress_record_bid: 'progress-1',
        user_bid: 'student-1',
        mobile: '13900001235',
        email: '',
        nickname: 'Bob',
        course_name: 'Course One',
        shifu_bid: 'course-1',
        chapter_title: '',
        lesson_title: 'Lesson 1',
        created_at: '2026-04-05T11:02:00Z',
        turn_index: 2,
      },
      current_record: {
        source_output_content: '',
        source_output_type: '',
        source_position: 0,
        source_element_bid: '',
        source_element_type: '',
        follow_up_content: 'Second follow-up question',
        answer_content: 'Second follow-up answer',
      },
      timeline: [],
    });

    render(<AdminOperationCourseFollowUpsPage />);

    await screen.findByText('Second follow-up question');

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.operationsCourse.detail.followUps.table.detailAction',
      })[0],
    );

    expect(
      await screen.findByText(
        'module.operationsCourse.detail.followUps.drawer.sourceUnavailable',
      ),
    ).toBeInTheDocument();
  });

  test('renders summary time in the viewer timezone when UTC crosses local day boundaries', async () => {
    mockBrowserTimeZone.mockReturnValue('America/Los_Angeles');
    mockGetAdminOperationCourseFollowUps.mockResolvedValueOnce({
      summary: {
        follow_up_count: 1,
        user_count: 1,
        lesson_count: 1,
        latest_follow_up_at: '2026-04-05T01:30:00Z',
      },
      items: [
        {
          generated_block_bid: 'ask-1',
          progress_record_bid: 'progress-1',
          user_bid: 'student-1',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          follow_up_content: 'Cross-day follow-up question',
          turn_index: 1,
          created_at: '2026-04-05T01:30:00Z',
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
      page_count: 1,
    });

    render(<AdminOperationCourseFollowUpsPage />);

    await screen.findByText('Cross-day follow-up question');

    expect(screen.getByText('2026-04-04')).toBeInTheDocument();
    expect(screen.getByText('18:30:00')).toBeInTheDocument();
  });

  test('ignores a late detail response after the drawer is closed', async () => {
    const deferredDetail =
      createDeferred<
        Awaited<ReturnType<typeof mockGetAdminOperationCourseFollowUpDetail>>
      >();
    mockGetAdminOperationCourseFollowUpDetail.mockReset();
    mockGetAdminOperationCourseFollowUpDetail.mockImplementationOnce(
      () => deferredDetail.promise,
    );

    render(<AdminOperationCourseFollowUpsPage />);

    await screen.findByText('Second follow-up question');

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.operationsCourse.detail.followUps.table.detailAction',
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
          course_name: 'Course One',
          shifu_bid: 'course-1',
          chapter_title: 'Chapter 1',
          lesson_title: 'Lesson 1',
          created_at: '2026-04-05T11:02:00Z',
          turn_index: 2,
        },
        current_record: {
          source_output_content: 'Stale source output',
          source_output_type: 'interaction',
          source_position: 2,
          source_element_bid: '',
          source_element_type: '',
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

  test('does not open the detail drawer for a blank generated block bid', async () => {
    mockGetAdminOperationCourseFollowUps.mockResolvedValueOnce({
      summary: {
        follow_up_count: 1,
        user_count: 1,
        lesson_count: 1,
        latest_follow_up_at: '2026-04-05T11:02:00Z',
      },
      items: [
        {
          generated_block_bid: '   ',
          progress_record_bid: 'progress-1',
          user_bid: 'student-1',
          mobile: '13900001235',
          email: '',
          nickname: 'Bob',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          follow_up_content: 'Question without a valid block bid',
          turn_index: 1,
          created_at: '2026-04-05T11:02:00Z',
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
      page_count: 1,
    });

    render(<AdminOperationCourseFollowUpsPage />);

    await screen.findByText('Question without a valid block bid');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.followUps.table.detailAction',
      }),
    );

    expect(mockGetAdminOperationCourseFollowUpDetail).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('loading-indicator')).not.toBeInTheDocument();
  });

  test('redirects non-operators back to admin', async () => {
    mockUserState.userInfo = {
      is_operator: false,
    };

    render(<AdminOperationCourseFollowUpsPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
  });
});

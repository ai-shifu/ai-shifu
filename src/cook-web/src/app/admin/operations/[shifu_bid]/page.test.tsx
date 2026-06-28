import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import AdminOperationCourseDetailPage from './page';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockGetAdminOperationCourseDetail = jest.fn();
const mockGetAdminOperationCourseUsers = jest.fn();
const mockGetAdminOperationCourseCreditUsages = jest.fn();
const mockGetAdminOperationCourseCreditUsageDetails = jest.fn();
const mockGetAdminOperationCourseChapterDetail = jest.fn();
const mockBrowserTimeZone = jest.fn(() => 'UTC');
const mockCopyText = jest.fn();
const mockToastShow = jest.fn();
const mockToastFail = jest.fn();
const mockScrollIntoView = jest.fn();
const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
const mockTranslationCache = new Map<string, { t: (key: string) => string }>();
let mockLanguage = 'en-US';
let mockSearchParams = new URLSearchParams();
const mockEnvState = {
  currencySymbol: '¥',
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
  useSearchParams: () => mockSearchParams,
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    href,
    children,
    ...props
  }: React.PropsWithChildren<{ href: string }>) => (
    <a
      href={href}
      {...props}
    >
      {children}
    </a>
  ),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCourseDetail: (...args: unknown[]) =>
      mockGetAdminOperationCourseDetail(...args),
    getAdminOperationCourseUsers: (...args: unknown[]) =>
      mockGetAdminOperationCourseUsers(...args),
    getAdminOperationCourseCreditUsages: (...args: unknown[]) =>
      mockGetAdminOperationCourseCreditUsages(...args),
    getAdminOperationCourseCreditUsageDetails: (...args: unknown[]) =>
      mockGetAdminOperationCourseCreditUsageDetails(...args),
    getAdminOperationCourseChapterDetail: (...args: unknown[]) =>
      mockGetAdminOperationCourseChapterDetail(...args),
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
      currencySymbol: string;
      loginMethodsEnabled: string[];
      defaultLoginMethod: string;
    }) => unknown,
  ) => selector(mockEnvState),
}));

jest.mock('@/c-utils/textutils', () => ({
  __esModule: true,
  copyText: (...args: unknown[]) => mockCopyText(...args),
}));

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  fail: (...args: unknown[]) => mockToastFail(...args),
  show: (...args: unknown[]) => mockToastShow(...args),
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
    return {
      ...mockTranslationCache.get(cacheKey)!,
      i18n: {
        get language() {
          return mockLanguage;
        },
      },
    };
  },
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ui/Dialog', () => ({
  __esModule: true,
  Dialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div role='dialog'>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/ui/Tabs', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const TabsContext = ReactModule.createContext<{
    value: string;
    onValueChange?: (value: string) => void;
  }>({
    value: '',
  });

  return {
    __esModule: true,
    Tabs: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange?: (value: string) => void;
    }>) => (
      <TabsContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </TabsContext.Provider>
    ),
    TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
    TabsTrigger: ({
      value,
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(TabsContext);
      return (
        <button
          role='tab'
          type='button'
          aria-selected={context.value === value}
          onClick={() => context.onValueChange?.(value)}
        >
          {children}
        </button>
      );
    },
    TabsContent: ({
      value,
      children,
      className,
    }: React.PropsWithChildren<{
      value: string;
      className?: string;
    }>) => {
      const context = ReactModule.useContext(TabsContext);
      if (context.value !== value) {
        return null;
      }
      return <div className={className}>{children}</div>;
    },
  };
});

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

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('AdminOperationCourseDetailPage', () => {
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: mockScrollIntoView,
    });
  });

  afterAll(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: originalScrollIntoView,
    });
  });

  const openUsersTab = async () => {
    fireEvent.click(
      await screen.findByRole('tab', {
        name: /module\.operationsCourse\.detail\.users/,
      }),
    );
    await screen.findByRole('button', {
      name: 'module.order.filters.search',
    });
  };

  const openCreditUsageTab = async () => {
    fireEvent.click(
      await screen.findByRole('tab', {
        name: /module\.operationsCourse\.detail\.creditUsageTab/,
      }),
    );
    await screen.findByRole('button', {
      name: 'module.order.filters.search',
    });
  };

  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    mockBrowserTimeZone.mockReset();
    mockBrowserTimeZone.mockReturnValue('UTC');
    mockGetAdminOperationCourseDetail.mockReset();
    mockGetAdminOperationCourseUsers.mockReset();
    mockGetAdminOperationCourseCreditUsages.mockReset();
    mockGetAdminOperationCourseCreditUsageDetails.mockReset();
    mockGetAdminOperationCourseChapterDetail.mockReset();
    mockCopyText.mockReset();
    mockToastShow.mockReset();
    mockToastFail.mockReset();
    mockScrollIntoView.mockReset();
    mockSearchParams = new URLSearchParams();
    mockLanguage = 'en-US';
    mockEnvState.currencySymbol = '¥';
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockEnvState.defaultLoginMethod = 'phone';
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = {
      is_operator: true,
    };
    mockCopyText.mockResolvedValue(undefined);
    mockGetAdminOperationCourseChapterDetail.mockResolvedValue({
      outline_item_bid: 'lesson-1',
      title: 'Lesson 1',
      content: 'lesson content',
      llm_system_prompt: 'lesson system prompt',
      llm_system_prompt_source: 'chapter',
    });
    mockGetAdminOperationCourseUsers.mockResolvedValue({
      items: [
        {
          user_bid: 'student-1',
          mobile: '13900001234',
          email: '',
          nickname: 'Bob',
          user_role: 'student',
          learned_lesson_count: 1,
          total_lesson_count: 3,
          learning_status: 'learning',
          is_paid: true,
          total_paid_amount: '88',
          last_learning_at: '2026-04-08T11:30:00Z',
          joined_at: '2026-04-07T09:00:00Z',
          last_login_at: '2026-04-08T12:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetAdminOperationCourseCreditUsages.mockResolvedValue({
      view: 'grouped',
      items: [
        {
          group_key: 'progress-1:learn',
          usage_bid: 'usage-2',
          progress_record_bid: 'progress-1',
          generated_block_bid: '',
          user_bid: 'student-1',
          mobile: '13900001234',
          email: '',
          nickname: 'Bob',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          usage_scene: 'learning',
          usage_mode: 'learn',
          provider: 'qwen',
          model: 'qwen/deepseek-v4-a',
          usage_count: 2,
          model_variant_count: 2,
          consumed_credits: 17,
          created_at: '2026-04-08T12:30:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetAdminOperationCourseCreditUsageDetails.mockResolvedValue({
      items: [
        {
          usage_bid: 'usage-1',
          consumed_credits: 7,
          input_tokens: 1200,
          output_tokens: 80,
          word_count: 0,
          duration_ms: 0,
          segment_count: 0,
          output_summary: 'First generated output summary',
          created_at: '2026-04-08T12:20:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
    });
    mockGetAdminOperationCourseDetail.mockResolvedValue({
      basic_info: {
        shifu_bid: 'course-1',
        course_name: 'Course One',
        course_status: 'published',
        creator_user_bid: 'creator-1',
        creator_mobile: '13800001234',
        creator_email: '',
        creator_nickname: 'Alice',
        created_at: '2026-04-08T10:00:00Z',
        updated_at: '2026-04-08T11:00:00Z',
      },
      metrics: {
        visit_count_30d: 34,
        learner_count: 12,
        order_count: 4,
        order_amount: '88',
        follow_up_count: 9,
        rating_score: '4.2',
        credit_consumed_total: 120,
        credit_usage_count: 18,
        credit_user_count: 6,
        completed_credit_user_count: 3,
        completed_user_avg_credits: 20,
      },
      chapters: [
        {
          outline_item_bid: 'chapter-1',
          title: 'Chapter 1',
          parent_bid: '',
          position: '1',
          node_type: 'chapter',
          learning_permission: 'guest',
          is_visible: true,
          content_status: 'empty',
          follow_up_count: 3,
          rating_score: '',
          rating_count: 2,
          modifier_user_bid: 'creator-1',
          modifier_mobile: '13800001234',
          modifier_email: '',
          modifier_nickname: 'Alice',
          updated_at: '2026-04-08T11:00:00Z',
          children: [
            {
              outline_item_bid: 'lesson-1',
              title: 'Lesson 1',
              parent_bid: 'chapter-1',
              position: '1.1',
              node_type: 'lesson',
              learning_permission: 'paid',
              is_visible: false,
              content_status: 'has',
              follow_up_count: 3,
              rating_score: '4.5',
              rating_count: 2,
              modifier_user_bid: 'modifier-1',
              modifier_mobile: '13900001234',
              modifier_email: '',
              modifier_nickname: 'Bob',
              updated_at: '2026-04-08T11:00:00Z',
              children: [],
            },
          ],
        },
      ],
    });
  });

  test('renders course detail data with breadcrumb navigation', async () => {
    render(<AdminOperationCourseDetailPage />);

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: 'module.operationsCourse.detail.title',
      }),
    ).toBeInTheDocument();
    expect(mockGetAdminOperationCourseDetail).toHaveBeenCalledWith({
      shifu_bid: 'course-1',
    });
    expect(mockGetAdminOperationCourseUsers).not.toHaveBeenCalled();

    expect(screen.getByText('Course One')).toBeInTheDocument();
    expect(screen.getAllByText('13800001234').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Alice').length).toBeGreaterThan(0);
    expect(
      screen.queryByText(
        'module.operationsCourse.detail.metricsLabels.visitCount30d',
      ),
    ).not.toBeInTheDocument();
    const creditsMetricCard = screen
      .getByText(
        'module.operationsCourse.detail.metricsLabels.creditConsumedTotal',
      )
      .closest('.rounded-lg');
    expect(creditsMetricCard).not.toBeNull();
    expect(
      within(creditsMetricCard as HTMLElement).getByText('120'),
    ).toBeInTheDocument();
    expect(screen.getByText('¥88')).toBeInTheDocument();
    expect(screen.getByText('4.2')).toBeInTheDocument();
    expect(screen.getByText('Chapter 1')).toBeInTheDocument();
    expect(screen.getByText('Lesson 1')).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCourse.detail.learningPermission.guest',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.detail.visibility.hidden'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.detail.contentStatus.has'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('13900001234').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Bob').length).toBeGreaterThan(0);
    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    expect(screen.getByText('4.5')).toBeInTheDocument();
    const chapterRow = screen.getByText('Chapter 1').closest('tr');
    expect(chapterRow).not.toBeNull();
    expect(
      within(chapterRow as HTMLElement).getAllByText('--').length,
    ).toBeGreaterThanOrEqual(3);
    await openUsersTab();
    const bobRow = screen.getAllByText('13900001234').at(-1)?.closest('tr');
    expect(bobRow).not.toBeNull();
    expect(within(bobRow as HTMLElement).getByText('Bob')).toBeInTheDocument();
    expect(within(bobRow as HTMLElement).getByText('88')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.operationsCourse.detail.userRole.student')
        .length,
    ).toBeGreaterThan(0);

    expect(
      screen.getByRole('link', {
        name: 'module.operationsCourse.title',
      }),
    ).toHaveAttribute('href', '/admin/operations');
  });

  test('converts course detail metadata timestamps to the browser timezone', async () => {
    mockGetAdminOperationCourseDetail.mockResolvedValueOnce({
      basic_info: {
        shifu_bid: 'course-1',
        course_name: 'Course One',
        course_status: 'published',
        creator_user_bid: 'creator-1',
        creator_mobile: '13800001234',
        creator_email: '',
        creator_nickname: 'Alice',
        created_at: '2026-06-09T12:01:50+08:00',
        updated_at: '2026-06-09T13:01:50+08:00',
      },
      metrics: {
        visit_count_30d: 34,
        learner_count: 12,
        order_count: 4,
        order_amount: '88',
        follow_up_count: 9,
        rating_score: '4.2',
        credit_consumed_total: 120,
        credit_usage_count: 18,
        credit_user_count: 6,
        completed_credit_user_count: 3,
        completed_user_avg_credits: 20,
      },
      chapters: [
        {
          outline_item_bid: 'chapter-timezone',
          title: 'Timezone Chapter',
          parent_bid: '',
          position: '1',
          node_type: 'chapter',
          learning_permission: 'guest',
          is_visible: true,
          content_status: 'empty',
          follow_up_count: 0,
          rating_score: '',
          rating_count: 0,
          modifier_user_bid: 'creator-1',
          modifier_mobile: '13800001234',
          modifier_email: '',
          modifier_nickname: 'Alice',
          updated_at: '2026-06-09T13:01:50+08:00',
          children: [],
        },
      ],
    });

    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Timezone Chapter');

    expect(screen.getByText('2026-06-09 04:01:50')).toBeInTheDocument();
    expect(screen.getAllByText('2026-06-09 05:01:50').length).toBeGreaterThan(
      0,
    );
    expect(screen.queryByText('2026-06-09 12:01:50')).not.toBeInTheDocument();
  });

  test('converts course user activity timestamps to the browser timezone', async () => {
    mockBrowserTimeZone.mockReturnValue('America/Los_Angeles');
    mockGetAdminOperationCourseUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'student-1',
          mobile: '13900001234',
          email: '',
          nickname: 'Bob',
          user_role: 'student',
          learned_lesson_count: 1,
          total_lesson_count: 3,
          learning_status: 'learning',
          is_paid: true,
          total_paid_amount: '88',
          last_learning_at: '2026-04-08T11:30:00Z',
          joined_at: '2026-04-07T09:00:00Z',
          last_login_at: '2026-04-08T12:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationCourseDetailPage />);

    await openUsersTab();

    expect(screen.getByText('2026-04-08 04:30:00')).toBeInTheDocument();
    expect(screen.getByText('2026-04-08 05:00:00')).toBeInTheDocument();
    expect(screen.getByText('2026-04-07 02:00:00')).toBeInTheDocument();
    expect(screen.queryByText('2026-04-08 11:30:00')).not.toBeInTheDocument();
    expect(screen.queryByText('2026-04-08 12:00:00')).not.toBeInTheDocument();
    expect(screen.queryByText('2026-04-07 09:00:00')).not.toBeInTheDocument();
  });

  test('converts course credit usage created_at values to the browser timezone', async () => {
    mockBrowserTimeZone.mockReturnValue('America/Los_Angeles');
    mockGetAdminOperationCourseCreditUsages.mockResolvedValueOnce({
      view: 'grouped',
      items: [
        {
          group_key: 'student-1:lesson-1:learning:listen',
          usage_bid: 'usage-listen',
          progress_record_bid: 'progress-1',
          generated_block_bid: '',
          user_bid: 'student-1',
          mobile: '13900001234',
          email: '',
          nickname: 'Bob',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          usage_scene: 'learning',
          usage_mode: 'listen',
          provider: 'volcengine',
          model: 'cancan-2.0',
          usage_count: 1,
          model_variant_count: 1,
          consumed_credits: 2,
          created_at: '2026-04-08T12:30:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetAdminOperationCourseCreditUsageDetails.mockResolvedValueOnce({
      page: 1,
      page_count: 1,
      page_size: 10,
      total: 1,
      items: [
        {
          usage_bid: 'usage-detail-1',
          created_at: '2026-04-08T12:20:00Z',
          content: 'Listen detail content',
          consumed_credits: 2,
          input_tokens: 0,
          output_tokens: 0,
          word_count: 180,
          duration_ms: 30000,
          segment_count: 1,
        },
      ],
    });

    render(<AdminOperationCourseDetailPage />);

    await openCreditUsageTab();

    expect(screen.getByText('2026-04-08 05:30:00')).toBeInTheDocument();
    expect(screen.queryByText('2026-04-08 12:30:00')).not.toBeInTheDocument();

    const usageRow = (await screen.findByText('Lesson 1')).closest('tr');
    expect(usageRow).not.toBeNull();
    fireEvent.click(
      within(usageRow as HTMLElement).getByRole('button', {
        name: 'module.operationsCourse.detail.creditUsage.details.openUsageDetails',
      }),
    );

    const dialog = await screen.findByRole('dialog');
    await waitFor(() => {
      expect(
        within(dialog).getByText('2026-04-08 05:20:00'),
      ).toBeInTheDocument();
    });
    expect(
      within(dialog).queryByText('2026-04-08 12:20:00'),
    ).not.toBeInTheDocument();
  });

  test('loads credit usage tab on demand and renders credit rows', async () => {
    render(<AdminOperationCourseDetailPage />);

    expect(mockGetAdminOperationCourseCreditUsages).not.toHaveBeenCalled();

    await openCreditUsageTab();

    await waitFor(() => {
      expect(mockGetAdminOperationCourseCreditUsages).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        view: 'grouped',
        keyword: '',
        usage_scene: '',
        mode: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(
      screen.getByText(
        'module.operationsCourse.detail.creditUsage.filters.userKeyword',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        'module.operationsCourse.detail.creditUsage.scenes.learning',
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(
        'module.operationsCourse.detail.creditUsage.modelSummary.multiple',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCourse.detail.creditUsage.table.usageCount',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('17')).toBeInTheDocument();
  });

  test('opens credit usage tab from tab query parameter', async () => {
    mockSearchParams = new URLSearchParams('tab=creditUsage');

    render(<AdminOperationCourseDetailPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationCourseCreditUsages).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        view: 'grouped',
        keyword: '',
        usage_scene: '',
        mode: '',
        start_time: '',
        end_time: '',
      });
    });
    expect(
      screen.getByText(
        'module.operationsCourse.detail.creditUsage.filters.userKeyword',
      ),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(mockScrollIntoView).toHaveBeenCalledWith({
        behavior: 'smooth',
        block: 'start',
      });
    });
  });

  test('opens credit usage detail dialog from usage count', async () => {
    render(<AdminOperationCourseDetailPage />);

    await openCreditUsageTab();

    const usageRow = (await screen.findByText('Lesson 1')).closest('tr');
    expect(usageRow).not.toBeNull();
    fireEvent.click(
      within(usageRow as HTMLElement).getByRole('button', {
        name: 'module.operationsCourse.detail.creditUsage.details.openUsageDetails',
      }),
    );

    await waitFor(() => {
      expect(
        mockGetAdminOperationCourseCreditUsageDetails,
      ).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 10,
        user_bid: 'student-1',
        outline_item_bid: 'lesson-1',
        usage_scene: 'learning',
        mode: 'learn',
      });
    });

    const dialog = screen.getByRole('dialog');
    expect(
      within(dialog).getByText(
        'module.operationsCourse.detail.creditUsage.details.title',
      ),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        within(dialog).getByText('First generated output summary'),
      ).toBeInTheDocument();
    });
  });

  test('keeps zero values visible in listen usage details', async () => {
    mockGetAdminOperationCourseCreditUsages.mockResolvedValueOnce({
      view: 'grouped',
      items: [
        {
          group_key: 'student-1:lesson-1:learning:listen',
          usage_bid: 'usage-listen',
          progress_record_bid: 'progress-1',
          generated_block_bid: '',
          user_bid: 'student-1',
          mobile: '13900001234',
          email: '',
          nickname: 'Bob',
          chapter_outline_item_bid: 'chapter-1',
          chapter_title: 'Chapter 1',
          lesson_outline_item_bid: 'lesson-1',
          lesson_title: 'Lesson 1',
          usage_scene: 'learning',
          usage_mode: 'listen',
          provider: 'volcengine',
          model: 'cancan-2.0',
          usage_count: 1,
          model_variant_count: 1,
          consumed_credits: 2,
          created_at: '2026-04-08T12:30:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationCourseDetailPage />);

    await openCreditUsageTab();

    const usageRow = (await screen.findByText('Lesson 1')).closest('tr');
    expect(usageRow).not.toBeNull();
    fireEvent.click(
      within(usageRow as HTMLElement).getByRole('button', {
        name: 'module.operationsCourse.detail.creditUsage.details.openUsageDetails',
      }),
    );

    const dialog = await screen.findByRole('dialog');
    await waitFor(() => {
      expect(within(dialog).getAllByText('0').length).toBeGreaterThanOrEqual(2);
    });
  });

  test('formats course metrics and learning progress without grouping in Chinese locale', async () => {
    mockLanguage = 'zh-CN';
    mockGetAdminOperationCourseUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'student-1',
          mobile: '13900001234',
          email: '',
          nickname: 'Bob',
          user_role: 'student',
          learned_lesson_count: 1000,
          total_lesson_count: 2000,
          learning_status: 'learning',
          is_paid: true,
          total_paid_amount: '88',
          last_learning_at: '2026-04-08T11:30:00Z',
          joined_at: '2026-04-07T09:00:00Z',
          last_login_at: '2026-04-08T12:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    mockGetAdminOperationCourseDetail.mockResolvedValueOnce({
      basic_info: {
        shifu_bid: 'course-1',
        course_name: 'Course One',
        course_status: 'published',
        creator_user_bid: 'creator-1',
        creator_mobile: '13800001234',
        creator_email: '',
        creator_nickname: 'Alice',
        created_at: '2026-04-08T10:00:00Z',
        updated_at: '2026-04-08T11:00:00Z',
      },
      metrics: {
        visit_count_30d: 76384,
        learner_count: 12000,
        order_count: 4000,
        order_amount: '88',
        follow_up_count: 9000,
        rating_score: '4.2',
        credit_consumed_total: 11000,
        credit_usage_count: 8000,
        credit_user_count: 3000,
        completed_credit_user_count: 2000,
        completed_user_avg_credits: 5.5,
      },
      chapters: [],
    });

    render(<AdminOperationCourseDetailPage />);

    expect(await screen.findByText('12000')).toBeInTheDocument();
    expect(screen.getByText('11000')).toBeInTheDocument();
    expect(screen.queryByText('12,000')).not.toBeInTheDocument();

    await openUsersTab();
    expect(screen.getByText('1000 / 2000')).toBeInTheDocument();
    expect(screen.queryByText('1,000 / 2,000')).not.toBeInTheDocument();
  });

  test('navigates to follow-up page from the follow-up metric card', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.followUps.openMetric',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith(
      '/admin/operations/course-1/follow-ups',
    );
  });

  test('navigates to order management from the order count metric card', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.orders.openMetric',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith(
      '/admin/operations/orders?shifu_bid=course-1',
    );
  });

  test('navigates to ratings page from the rating metric card', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.ratings.openMetric',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith('/admin/operations/course-1/ratings');
  });

  test('renders static metric cards with non-interactive semantics', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');

    expect(
      screen.queryByText(
        'module.operationsCourse.detail.metricsLabels.visitCount30d',
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.followUps.openMetric',
      }),
    ).toBeInTheDocument();
  });

  test('opens chapter content dialog and requests chapter detail', async () => {
    const chapterDetailRequest = createDeferred<{
      outline_item_bid: string;
      title: string;
      content: string;
      llm_system_prompt: string;
      llm_system_prompt_source: 'chapter';
    }>();
    mockGetAdminOperationCourseChapterDetail.mockReturnValueOnce(
      chapterDetailRequest.promise,
    );

    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');

    const lessonRow = screen.getByText('Lesson 1').closest('tr');
    expect(lessonRow).not.toBeNull();

    fireEvent.click(
      within(lessonRow as HTMLElement).getByRole('button', {
        name: 'module.operationsCourse.detail.chaptersTable.detailAction',
      }),
    );

    expect(
      await screen.findByText(
        'module.operationsCourse.detail.contentDetailDialog.title',
      ),
    ).toBeInTheDocument();
    expect(mockGetAdminOperationCourseChapterDetail).toHaveBeenCalledWith({
      shifu_bid: 'course-1',
      outline_item_bid: 'lesson-1',
    });

    const initialCopyButton = screen.getByRole('button', {
      name: 'module.operationsCourse.detail.contentDetailDialog.copy',
    });
    expect(initialCopyButton).toBeDisabled();

    await act(async () => {
      chapterDetailRequest.resolve({
        outline_item_bid: 'lesson-1',
        title: 'Lesson 1',
        content: 'lesson content',
        llm_system_prompt: 'lesson system prompt',
        llm_system_prompt_source: 'chapter',
      });
      await chapterDetailRequest.promise;
    });

    await waitFor(() => {
      expect(screen.getByText('lesson content')).toBeInTheDocument();
      expect(screen.getByText('lesson system prompt')).toBeInTheDocument();
      expect(
        screen.getByRole('button', {
          name: 'module.operationsCourse.detail.contentDetailDialog.copy',
        }),
      ).not.toBeDisabled();
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.contentDetailDialog.copy',
      }),
    );

    await waitFor(() => {
      expect(mockCopyText).toHaveBeenCalledWith(
        [
          'module.operationsCourse.detail.contentDetailDialog.sections.content',
          'lesson content',
          '',
          'module.operationsCourse.detail.contentDetailDialog.sections.systemPrompt (module.operationsCourse.detail.contentDetailDialog.sources.chapter)',
          'lesson system prompt',
        ].join('\n'),
      );
      expect(mockToastShow).toHaveBeenCalledWith(
        'module.operationsCourse.detail.contentDetailDialog.copySuccess',
      );
    });
    expect(mockToastFail).not.toHaveBeenCalled();
  });

  test('redirects non-operators back to admin', async () => {
    mockUserState.userInfo = {
      is_operator: false,
    };

    render(<AdminOperationCourseDetailPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
  });

  test('surfaces unknown chapter type values instead of mislabeling them', async () => {
    mockGetAdminOperationCourseDetail.mockResolvedValue({
      basic_info: {
        shifu_bid: 'course-1',
        course_name: 'Course One',
        course_status: 'published',
        creator_user_bid: 'creator-1',
        creator_mobile: '13800001234',
        creator_email: '',
        creator_nickname: 'Alice',
        created_at: '2026-04-08T10:00:00Z',
        updated_at: '2026-04-08T11:00:00Z',
      },
      metrics: {
        visit_count_30d: 34,
        learner_count: 12,
        order_count: 4,
        order_amount: '88',
        follow_up_count: 9,
        rating_score: '4.2',
        credit_consumed_total: 120,
        credit_usage_count: 18,
        credit_user_count: 6,
        completed_credit_user_count: 3,
        completed_user_avg_credits: 20,
      },
      chapters: [
        {
          outline_item_bid: 'chapter-1',
          title: 'Chapter 1',
          parent_bid: '',
          position: '1',
          node_type: 'mystery',
          learning_permission: 'guest',
          is_visible: true,
          content_status: 'empty',
          follow_up_count: 3,
          rating_score: '',
          rating_count: 2,
          modifier_user_bid: 'creator-1',
          modifier_mobile: '13800001234',
          modifier_email: '',
          modifier_nickname: 'Alice',
          updated_at: '2026-04-08T11:00:00Z',
          children: [],
        },
      ],
    });

    render(<AdminOperationCourseDetailPage />);

    expect(
      await screen.findByText(
        'module.operationsCourse.statusLabels.unknown (mystery)',
      ),
    ).toBeInTheDocument();
  });

  test('searches course users with explicit search button', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');
    await openUsersTab();
    mockGetAdminOperationCourseUsers.mockClear();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.usersFilters.userKeywordPlaceholderPhone',
      ),
      {
        target: {
          value: 'student',
        },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCourseUsers).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        keyword: 'student',
        user_role: 'all',
        learning_status: 'all',
        payment_status: 'all',
      });
    });
  });

  test('loads course users only after users tab is activated', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');
    expect(mockGetAdminOperationCourseUsers).not.toHaveBeenCalled();

    await openUsersTab();

    await waitFor(() => {
      expect(mockGetAdminOperationCourseUsers).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        keyword: '',
        user_role: 'all',
        learning_status: 'all',
        payment_status: 'all',
      });
    });
  });

  test('shows empty account when current site mode field is missing', async () => {
    mockGetAdminOperationCourseUsers.mockResolvedValue({
      items: [
        {
          user_bid: 'guest-1',
          mobile: '',
          email: 'guest@example.com',
          nickname: '',
          user_role: 'student',
          learned_lesson_count: 0,
          total_lesson_count: 0,
          learning_status: 'not_started',
          is_paid: false,
          total_paid_amount: '0',
          last_learning_at: '',
          joined_at: '',
          last_login_at: '',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');
    await openUsersTab();
    await waitFor(() => {
      expect(screen.getAllByText('--').length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText('--').length).toBeGreaterThan(0);
    expect(screen.queryByText('guest@example.com')).not.toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.usersFilters.userKeywordPlaceholderPhone',
      ),
    ).toBeInTheDocument();
  });

  test('uses email placeholder in com site mode', async () => {
    mockEnvState.loginMethodsEnabled = ['email'];
    mockEnvState.defaultLoginMethod = 'email';

    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');
    await openUsersTab();
    expect(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.usersFilters.userKeywordPlaceholderEmail',
      ),
    ).toBeInTheDocument();
  });

  test('applies select filters immediately when user changes them', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');
    await openUsersTab();
    mockGetAdminOperationCourseUsers.mockClear();

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.operationsCourse.detail.userRole.operator',
      })[0],
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCourseUsers).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        keyword: '',
        user_role: 'operator',
        learning_status: 'all',
        payment_status: 'all',
      });
    });
  });

  test('does not apply draft keyword until search is submitted', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');
    await openUsersTab();
    mockGetAdminOperationCourseUsers.mockClear();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.usersFilters.userKeywordPlaceholderPhone',
      ),
      {
        target: {
          value: '15811237246',
        },
      },
    );

    fireEvent.click(
      screen.getAllByRole('button', {
        name: 'module.operationsCourse.detail.userRole.operator',
      })[0],
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCourseUsers).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        keyword: '',
        user_role: 'operator',
        learning_status: 'all',
        payment_status: 'all',
      });
    });
  });

  test('does not apply credit usage draft filters when scene changes', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');
    await openCreditUsageTab();
    mockGetAdminOperationCourseCreditUsages.mockClear();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.detail.creditUsage.filters.userKeywordPlaceholderPhone',
      ),
      {
        target: {
          value: 'draft keyword',
        },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.creditUsage.scenes.preview',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCourseCreditUsages).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        page: 1,
        page_size: 20,
        view: 'grouped',
        keyword: '',
        usage_scene: 'preview',
        mode: '',
        start_time: '',
        end_time: '',
      });
    });
  });

  test('requests the selected page when course user pagination changes', async () => {
    mockGetAdminOperationCourseUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'student-1',
          mobile: '13900001234',
          email: '',
          nickname: 'Bob',
          user_role: 'student',
          learned_lesson_count: 1,
          total_lesson_count: 3,
          learning_status: 'learning',
          is_paid: true,
          total_paid_amount: '88',
          last_learning_at: '2026-04-08T11:30:00Z',
          joined_at: '2026-04-07T09:00:00Z',
          last_login_at: '2026-04-08T12:00:00Z',
        },
      ],
      page: 1,
      page_count: 2,
      page_size: 20,
      total: 21,
    });
    mockGetAdminOperationCourseUsers.mockResolvedValueOnce({
      items: [],
      page: 2,
      page_count: 2,
      page_size: 20,
      total: 21,
    });

    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');
    await openUsersTab();

    fireEvent.click(
      await screen.findByRole('link', {
        name: '2',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCourseUsers).toHaveBeenLastCalledWith({
        shifu_bid: 'course-1',
        page: 2,
        page_size: 20,
        keyword: '',
        user_role: 'all',
        learning_status: 'all',
        payment_status: 'all',
      });
    });
  });
});

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import AdminOperationUserDetailPage from './page';

const mockPush = jest.fn();
const mockRefresh = jest.fn();
const mockScrollIntoView = jest.fn();
const mockBrowserTimeZone = jest.fn(() => 'UTC');
let currentUserBid = 'user-1';
const translationCache = new Map<string, { t: (key: string) => string }>();
const baseTranslation = (namespace?: string | string[]) => {
  const ns = Array.isArray(namespace) ? namespace[0] : namespace;
  const cacheKey = ns || 'translation';
  if (!translationCache.has(cacheKey)) {
    translationCache.set(cacheKey, {
      t: (key: string) => (ns && ns !== 'translation' ? `${ns}.${key}` : key),
    });
  }
  return translationCache.get(cacheKey)!;
};

const mockUserState: {
  isInitialized: boolean;
  isGuest: boolean;
  userInfo: { is_operator: boolean } | null;
} = {
  isInitialized: true,
  isGuest: false,
  userInfo: { is_operator: true },
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    refresh: mockRefresh,
  }),
  useParams: () => ({
    user_bid: currentUserBid,
  }),
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
    getAdminOperationUserDetail: jest.fn(),
    getAdminOperationUserCredits: jest.fn(),
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
      currencySymbol: string;
    }) => unknown,
  ) =>
    selector({
      loginMethodsEnabled: ['email'],
      defaultLoginMethod: 'email',
      currencySymbol: '¥',
    }),
}));

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => mockBrowserTimeZone(),
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => baseTranslation(namespace),
}));

jest.mock('@/components/ui/tooltip', () => ({
  __esModule: true,
  TooltipProvider: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  Tooltip: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage: string }) => (
    <div>{errorMessage}</div>
  ),
}));

jest.mock('@/components/ui/Tabs', () => {
  const ReactModule = jest.requireActual('react') as typeof React;
  const TabsContext = ReactModule.createContext<{
    value: string;
    onValueChange: (value: string) => void;
  }>({
    value: '',
    onValueChange: () => undefined,
  });

  return {
    __esModule: true,
    Tabs: ({
      value,
      onValueChange,
      children,
    }: React.PropsWithChildren<{
      value: string;
      onValueChange: (value: string) => void;
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
      const isActive = context.value === value;
      return (
        <button
          type='button'
          role='tab'
          data-state={isActive ? 'active' : 'inactive'}
          onClick={() => context.onValueChange(value)}
        >
          {children}
        </button>
      );
    },
    TabsContent: ({
      value,
      children,
    }: React.PropsWithChildren<{ value: string }>) => {
      const context = ReactModule.useContext(TabsContext);
      if (context.value !== value) {
        return null;
      }
      return <div>{children}</div>;
    },
  };
});

const mockGetAdminOperationUserDetail =
  api.getAdminOperationUserDetail as jest.Mock;
const mockGetAdminOperationUserCredits =
  api.getAdminOperationUserCredits as jest.Mock;

const detailResponse = {
  user_bid: 'user-1',
  mobile: '13812345678',
  email: 'user-1@example.com',
  nickname: 'Nick',
  user_status: 'paid',
  user_role: 'operator',
  user_roles: ['operator', 'creator', 'learner'],
  login_methods: ['phone', 'google'],
  registration_source: 'google',
  language: 'zh-CN',
  learning_courses: [
    {
      shifu_bid: 'course-1',
      course_name: 'Learned Course',
      course_status: 'published',
      completed_lesson_count: 1,
      total_lesson_count: 4,
    },
  ],
  created_courses: [
    {
      shifu_bid: 'course-2',
      course_name: 'Created Course',
      course_status: 'unpublished',
      completed_lesson_count: 0,
      total_lesson_count: 0,
    },
  ],
  total_paid_amount: '88.50',
  available_credits: '35.5',
  subscription_credits: '27.5',
  topup_credits: '8',
  credits_expire_at: '2026-05-01T00:00:00Z',
  has_active_subscription: true,
  last_login_at: '2026-04-15T09:00:00Z',
  last_learning_at: '2026-04-15T10:00:00Z',
  created_at: '2026-04-14T10:00:00Z',
  updated_at: '2026-04-14T11:00:00Z',
};

const creditsResponse = {
  summary: {
    available_credits: '35.5',
    subscription_credits: '27.5',
    topup_credits: '8',
    credits_expire_at: '2026-05-01T00:00:00Z',
    has_active_subscription: true,
  },
  items: [
    {
      ledger_bid: 'ledger-1',
      created_at: '2026-04-18T10:00:00Z',
      entry_type: 'grant',
      source_type: 'reward',
      display_entry_type: 'manual_grant',
      display_source_type: 'reward',
      amount: '5',
      balance_after: '35.5',
      expires_at: '',
      consumable_from: '2026-04-18T10:00:00Z',
      note: 'ops reward',
      note_code: '',
    },
  ],
  page: 1,
  page_count: 1,
  page_size: 10,
  total: 1,
};

describe('AdminOperationUserDetailPage', () => {
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: mockScrollIntoView,
    });
  });

  beforeEach(() => {
    currentUserBid = 'user-1';
    mockPush.mockReset();
    mockRefresh.mockReset();
    mockScrollIntoView.mockReset();
    mockBrowserTimeZone.mockReset();
    mockBrowserTimeZone.mockReturnValue('UTC');
    mockGetAdminOperationUserDetail.mockReset();
    mockGetAdminOperationUserCredits.mockReset();
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = { is_operator: true };
    window.history.pushState({}, '', '/admin/operations/users/user-1');
    mockGetAdminOperationUserDetail.mockResolvedValue(detailResponse);
    mockGetAdminOperationUserCredits.mockResolvedValue(creditsResponse);
  });

  test('loads and renders user detail with credits overview and ledger', async () => {
    render(<AdminOperationUserDetailPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUserDetail).toHaveBeenCalledWith({
        user_bid: 'user-1',
      });
      expect(mockGetAdminOperationUserCredits).toHaveBeenCalledWith({
        user_bid: 'user-1',
        page_index: 1,
        page_size: 10,
      });
    });

    expect(
      await screen.findByText('module.operationsUser.detail.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsUser.timezoneHint'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('Nick').length).toBeGreaterThan(0);
    expect(screen.getByText('user-1@example.com')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsUser.roleLabels.operator'),
    ).toBeInTheDocument();
    expect(screen.getByText('¥88.50')).toBeInTheDocument();
    expect(screen.getAllByText('35.5').length).toBeGreaterThan(0);
    expect(screen.getByText('27.5')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('2026-05-01 00:00:00')).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsUser.detail.creditLedgerTypeLabels.manual_grant',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsUser.detail.creditLedgerSourceLabels.reward',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('ops reward')).toBeInTheDocument();
    const pageContainer = screen.getByTestId(
      'admin-operation-user-detail-page',
    );
    expect(pageContainer).toHaveClass('h-full');
    expect(pageContainer).toHaveClass('overflow-hidden');
    expect(pageContainer).not.toHaveClass('overflow-auto');
    expect(
      screen.getByTestId('admin-operation-user-credit-ledger-scroll'),
    ).toHaveClass('overflow-auto');

    fireEvent.click(
      screen.getByRole('tab', {
        name: 'module.operationsUser.detail.tabs.learningCourses',
      }),
    );

    expect(
      await screen.findByRole('link', { name: 'Learned Course' }),
    ).toHaveAttribute('href', '/admin/operations/course-1');
    expect(screen.getByText('25% (1/4)')).toBeInTheDocument();
    expect(pageContainer).not.toHaveClass('overflow-auto');
  });

  test('renders detail timestamps in the viewer timezone when UTC crosses local day boundaries', async () => {
    mockBrowserTimeZone.mockReturnValue('America/Los_Angeles');
    mockGetAdminOperationUserDetail.mockResolvedValueOnce({
      ...detailResponse,
      last_login_at: '2026-04-15T01:30:00Z',
      last_learning_at: '2026-04-15T02:30:00Z',
      created_at: '2026-04-14T01:15:00Z',
      updated_at: '2026-04-14T03:45:00Z',
    });
    mockGetAdminOperationUserCredits.mockResolvedValueOnce({
      ...creditsResponse,
      summary: {
        ...creditsResponse.summary,
        credits_expire_at: '2026-05-01T01:00:00Z',
      },
      items: [
        {
          ...creditsResponse.items[0],
          created_at: '2026-04-18T01:00:00Z',
          expires_at: '2026-05-01T01:00:00Z',
        },
      ],
    });

    render(<AdminOperationUserDetailPage />);

    await screen.findByText('module.operationsUser.detail.title');

    expect(
      screen.getByText('module.operationsUser.timezoneHint'),
    ).toBeInTheDocument();
    expect(screen.getByText('2026-04-14 18:30:00')).toBeInTheDocument();
    expect(screen.getByText('2026-04-14 19:30:00')).toBeInTheDocument();
    expect(screen.getByText('2026-04-13 18:15:00')).toBeInTheDocument();
    expect(screen.getByText('2026-04-13 20:45:00')).toBeInTheDocument();
    expect(screen.getAllByText('2026-04-30 18:00:00').length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText('2026-04-17 18:00:00')).toBeInTheDocument();
  });

  test('keeps note column empty for system ledger rows without manual note', async () => {
    mockGetAdminOperationUserCredits.mockResolvedValueOnce({
      ...creditsResponse,
      items: [
        {
          ledger_bid: 'ledger-2',
          created_at: '2026-04-19T10:00:00Z',
          entry_type: 'grant',
          source_type: 'subscription',
          display_entry_type: 'subscription_grant',
          display_source_type: 'subscription',
          amount: '10',
          balance_after: '45.5',
          expires_at: '2026-05-01T00:00:00Z',
          consumable_from: '2026-04-19T10:00:00Z',
          note: '',
          note_code: 'subscription_purchase',
        },
      ],
    });

    render(<AdminOperationUserDetailPage />);

    expect(
      await screen.findByText(
        'module.operationsUser.detail.creditLedgerTypeLabels.subscription_grant',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsUser.detail.creditLedgerSourceLabels.subscription',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        'module.operationsUser.detail.creditLedgerNoteLabels.subscription_purchase',
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByText('--')).toBeInTheDocument();
  });

  test('back button returns to user list', async () => {
    render(<AdminOperationUserDetailPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUserDetail).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'module.operationsUser.detail.back' }),
    );

    expect(mockPush).toHaveBeenCalledWith('/admin/operations/users');
  });

  test('does not request detail or credits when the route param cannot be decoded', async () => {
    currentUserBid = '%';

    render(<AdminOperationUserDetailPage />);

    expect(
      await screen.findByText('server.common.paramsError'),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetAdminOperationUserDetail).not.toHaveBeenCalled();
      expect(mockGetAdminOperationUserCredits).not.toHaveBeenCalled();
    });
  });

  test('activates the credits tab when the hash is present', async () => {
    window.history.pushState({}, '', '/admin/operations/users/user-1#credits');

    render(<AdminOperationUserDetailPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUserDetail).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByRole('tab', {
        name: 'module.operationsUser.detail.tabs.credits',
      }),
    ).toHaveAttribute('data-state', 'active');
  });

  test('uses course status translations for unknown course states', async () => {
    mockGetAdminOperationUserDetail.mockResolvedValueOnce({
      ...detailResponse,
      created_courses: [
        {
          shifu_bid: 'course-unknown',
          course_name: 'Unknown State Course',
          course_status: '',
          completed_lesson_count: 0,
          total_lesson_count: 0,
        },
      ],
    });

    render(<AdminOperationUserDetailPage />);

    fireEvent.click(
      await screen.findByRole('tab', {
        name: 'module.operationsUser.detail.tabs.createdCourses',
      }),
    );

    expect(
      await screen.findByText('module.operationsCourse.statusLabels.unknown'),
    ).toBeInTheDocument();
  });

  test('uses default user name when nickname is empty', async () => {
    mockGetAdminOperationUserDetail.mockResolvedValueOnce({
      ...detailResponse,
      nickname: '',
      email: 'empty-nick@example.com',
      user_role: 'learner',
      user_roles: ['learner'],
      login_methods: ['email'],
      registration_source: 'email',
      learning_courses: [],
      created_courses: [],
      available_credits: '',
      subscription_credits: '',
      topup_credits: '',
      credits_expire_at: '',
      has_active_subscription: false,
    });
    mockGetAdminOperationUserCredits.mockResolvedValueOnce({
      summary: {
        available_credits: '',
        subscription_credits: '',
        topup_credits: '',
        credits_expire_at: '',
        has_active_subscription: false,
      },
      items: [],
      page: 1,
      page_count: 0,
      page_size: 10,
      total: 0,
    });

    render(<AdminOperationUserDetailPage />);

    expect(
      await screen.findAllByText('module.user.defaultUserName'),
    ).toHaveLength(1);
  });

  test('shows only the first ten courses until expanded', async () => {
    mockGetAdminOperationUserDetail.mockResolvedValueOnce({
      ...detailResponse,
      user_role: 'learner',
      user_roles: ['learner'],
      login_methods: ['email'],
      registration_source: 'email',
      learning_courses: Array.from({ length: 11 }, (_, index) => ({
        shifu_bid: `course-${index + 1}`,
        course_name: `Learning Course ${index + 1}`,
        course_status: 'published',
        completed_lesson_count: index,
        total_lesson_count: 12,
      })),
      created_courses: [],
    });

    render(<AdminOperationUserDetailPage />);

    fireEvent.click(
      await screen.findByRole('tab', {
        name: 'module.operationsUser.detail.tabs.learningCourses',
      }),
    );

    expect(
      await screen.findByRole('link', { name: 'Learning Course 10' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Learning Course 11' }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.expand module.operationsUser.detail.learningCourses',
      }),
    );

    expect(
      await screen.findByRole('link', { name: 'Learning Course 11' }),
    ).toBeInTheDocument();
  });
});

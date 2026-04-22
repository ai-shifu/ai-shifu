import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import AdminOperationUsersPage from './page';

const mockReplace = jest.fn();
const mockMutateBillingOverview = jest.fn();
const originalLocation = window.location;
const mockGrantDialogPrefix = 'grant-dialog-';
const mockGrantSuccessLabel = 'mock-grant-success';
const buildGrantDialogLabel = (userBid: string) =>
  `${mockGrantDialogPrefix}${userBid}`;
const translationCache = new Map<string, { t: (key: string) => string }>();
const baseTranslation = (namespace?: string | string[]) => {
  const ns = Array.isArray(namespace) ? namespace[0] : namespace;
  const cacheKey = ns || 'translation';
  if (!translationCache.has(cacheKey)) {
    translationCache.set(cacheKey, {
      t: (key: string) => {
        return ns && ns !== 'translation' ? `${ns}.${key}` : key;
      },
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
  userInfo: {
    is_operator: true,
  },
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
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
    getAdminOperationUsers: jest.fn(),
  },
}));

jest.mock('swr', () => ({
  __esModule: true,
  useSWRConfig: () => ({
    mutate: mockMutateBillingOverview,
  }),
}));

jest.mock('@/components/ui/DropdownMenu', () => ({
  __esModule: true,
  DropdownMenu: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => (
    <>{children}</>
  ),
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuItem: ({
    children,
    onClick,
  }: React.PropsWithChildren<{ onClick?: () => void }>) => (
    <button
      type='button'
      onClick={onClick}
    >
      {children}
    </button>
  ),
}));

jest.mock('./UserCreditGrantDialog', () => ({
  __esModule: true,
  default: ({
    open,
    user,
    onGranted,
  }: {
    open: boolean;
    user: { user_bid: string } | null;
    onGranted?: () => void;
  }) =>
    open ? (
      <div>
        <div>{buildGrantDialogLabel(user?.user_bid || '')}</div>
        <button
          type='button'
          onClick={onGranted}
        >
          {mockGrantSuccessLabel}
        </button>
      </div>
    ) : null,
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
  getBrowserTimeZone: () => 'UTC',
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => baseTranslation(namespace),
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

jest.mock('@/components/ui/Dialog', () => ({
  __esModule: true,
  Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
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

jest.mock('@/app/admin/components/AdminDateRangeFilter', () => ({
  __esModule: true,
  default: ({ placeholder }: { placeholder: string }) => (
    <div>{placeholder}</div>
  ),
}));

const mockGetAdminOperationUsers = api.getAdminOperationUsers as jest.Mock;

describe('AdminOperationUsersPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockMutateBillingOverview.mockReset();
    mockGetAdminOperationUsers.mockReset();
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = { is_operator: true };
    mockGetAdminOperationUsers.mockResolvedValue({
      items: [
        {
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
            {
              shifu_bid: 'course-3',
              course_name: 'Second Created Course',
              course_status: 'published',
              completed_lesson_count: 0,
              total_lesson_count: 0,
            },
          ],
          total_paid_amount: '88.50',
          available_credits: '35.5',
          subscription_credits: '27.5',
          topup_credits: '8',
          credits_expire_at: '2026-05-01T00:00:00Z',
          last_login_at: '2026-04-15T09:00:00Z',
          last_learning_at: '2026-04-15T10:00:00Z',
          created_at: '2026-04-14T10:00:00Z',
          updated_at: '2026-04-14T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        href: 'http://localhost/admin/operations/users',
        pathname: '/admin/operations/users',
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

  test('loads and renders operator users', async () => {
    render(<AdminOperationUsersPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 20,
        user_bid: '',
        identifier: '',
        nickname: '',
        user_status: '',
        user_role: '',
        start_time: '',
        end_time: '',
      });
    });

    expect(
      await screen.findByText('module.operationsUser.title'),
    ).toBeInTheDocument();
    expect(await screen.findByText('user-1')).toBeInTheDocument();
    expect(screen.getByText('user-1@example.com')).toBeInTheDocument();
    expect(screen.getByText('Nick')).toBeInTheDocument();
    expect(screen.getByText('¥88.50')).toBeInTheDocument();
    expect(screen.getByText('35.5')).toBeInTheDocument();
    expect(screen.getByText('2026-05-01 00:00:00')).toBeInTheDocument();
    expect(
      screen.getAllByText('module.operationsUser.statusLabels.paid').length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText('module.operationsUser.roleLabels.operator').length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(
        'module.operationsUser.loginMethodLabels.phone / module.operationsUser.loginMethodLabels.google',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsUser.registrationSourceLabels.google'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsUser.table.learningCourses (1)',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsUser.table.createdCourses (2)',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'user-1@example.com' }),
    ).toHaveAttribute('href', '/admin/operations/users/user-1');
    expect(screen.getByRole('link', { name: '35.5' })).toHaveAttribute(
      'href',
      '/admin/operations/users/user-1#credits',
    );
    expect(
      screen.getByRole('button', {
        name: 'module.operationsUser.actions.grantCredits',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsUser.actions.moreForUser',
      }),
    ).toBeInTheDocument();
  });

  test('opens the credit grant dialog from the action menu', async () => {
    render(<AdminOperationUsersPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.actions.grantCredits',
      }),
    );

    expect(await screen.findByText('grant-dialog-user-1')).toBeInTheDocument();
  });

  test('revalidates billing overview after credits are granted successfully', async () => {
    render(<AdminOperationUsersPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.actions.grantCredits',
      }),
    );

    fireEvent.click(
      await screen.findByRole('button', { name: mockGrantSuccessLabel }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenCalledTimes(2);
    });
    expect(mockMutateBillingOverview).toHaveBeenCalledTimes(1);
    expect(mockMutateBillingOverview).toHaveBeenCalledWith([
      'creator-billing-overview',
      'UTC',
    ]);
  });

  test('submits search filters', async () => {
    render(<AdminOperationUsersPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenCalledTimes(1);
    });

    const userIdInput = screen.getAllByRole('textbox')[0];
    fireEvent.change(userIdInput, { target: { value: 'user-22' } });
    fireEvent.click(screen.getByRole('button', { name: 'common.core.expand' }));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.roleLabels.creator',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'module.order.filters.search' }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenLastCalledWith({
        page_index: 1,
        page_size: 20,
        user_bid: 'user-22',
        identifier: '',
        nickname: '',
        user_status: '',
        user_role: 'creator',
        start_time: '',
        end_time: '',
      });
    });
  });

  test('redirects non-operators back to admin', async () => {
    mockUserState.userInfo = { is_operator: false };

    render(<AdminOperationUsersPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
    expect(mockGetAdminOperationUsers).not.toHaveBeenCalled();
  });

  test('opens course dialog from summary cells', async () => {
    render(<AdminOperationUsersPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.table.createdCourses (2)',
      }),
    );

    expect(
      screen.getByText(
        'module.operationsUser.courseSummary.dialog.createdTitle',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Created Course')).toBeInTheDocument();
    expect(screen.getByText('course-2')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.statusLabels.unpublished'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Created Course' }),
    ).toHaveAttribute('href', '/admin/operations/course-2');
  });

  test('links the user id cell when the primary contact is empty', async () => {
    mockGetAdminOperationUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'user-no-contact',
          mobile: '',
          email: '',
          nickname: 'No Contact',
          user_status: 'registered',
          user_role: 'regular',
          user_roles: ['regular'],
          login_methods: [],
          registration_source: 'unknown',
          language: 'en-US',
          learning_courses: [],
          created_courses: [],
          total_paid_amount: '0',
          available_credits: '',
          subscription_credits: '',
          topup_credits: '',
          credits_expire_at: '',
          last_login_at: '',
          last_learning_at: '',
          created_at: '2026-04-14T10:00:00Z',
          updated_at: '2026-04-14T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationUsersPage />);

    expect(
      await screen.findByRole('link', { name: 'user-no-contact' }),
    ).toHaveAttribute('href', '/admin/operations/users/user-no-contact');
  });

  test('uses course status translations for unknown course states in the dialog', async () => {
    mockGetAdminOperationUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'user-1',
          mobile: '',
          email: 'user-1@example.com',
          nickname: 'Nick',
          user_status: 'registered',
          user_role: 'creator',
          user_roles: ['creator'],
          login_methods: ['email'],
          registration_source: 'email',
          language: 'en-US',
          learning_courses: [],
          created_courses: [
            {
              shifu_bid: 'course-unknown',
              course_name: 'Unknown State Course',
              course_status: '',
              completed_lesson_count: 0,
              total_lesson_count: 0,
            },
          ],
          total_paid_amount: '0',
          available_credits: '0',
          subscription_credits: '0',
          topup_credits: '0',
          credits_expire_at: '',
          last_login_at: '',
          last_learning_at: '',
          created_at: '2026-04-14T10:00:00Z',
          updated_at: '2026-04-14T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationUsersPage />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'module.operationsUser.table.createdCourses (1)',
      }),
    );

    expect(
      screen.getByText('module.operationsCourse.statusLabels.unknown'),
    ).toBeInTheDocument();
  });

  test('shows localized unknown labels for unexpected login methods and course statuses', async () => {
    mockGetAdminOperationUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'user-unknown-values',
          mobile: '',
          email: 'user-unknown@example.com',
          nickname: 'Unknown Values',
          user_status: 'registered',
          user_role: 'creator',
          user_roles: ['creator'],
          login_methods: ['password'],
          registration_source: 'unknown',
          language: 'en-US',
          learning_courses: [],
          created_courses: [
            {
              shifu_bid: 'course-archived',
              course_name: 'Archived Course',
              course_status: 'archived',
              completed_lesson_count: 0,
              total_lesson_count: 0,
            },
          ],
          total_paid_amount: '0',
          available_credits: '0',
          subscription_credits: '0',
          topup_credits: '0',
          credits_expire_at: '',
          last_login_at: '',
          last_learning_at: '',
          created_at: '2026-04-14T10:00:00Z',
          updated_at: '2026-04-14T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationUsersPage />);

    expect(
      await screen.findByText(
        'module.operationsUser.loginMethodLabels.unknown',
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsUser.table.createdCourses (1)',
      }),
    );

    expect(
      screen.getByText(
        'module.operationsCourse.statusLabels.unknown (archived)',
      ),
    ).toBeInTheDocument();
  });

  test('uses default user name when nickname is empty', async () => {
    mockGetAdminOperationUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'user-2',
          mobile: '',
          email: 'empty-nick@example.com',
          nickname: '',
          user_status: 'registered',
          user_role: 'learner',
          user_roles: ['learner'],
          login_methods: ['email'],
          registration_source: 'email',
          language: 'en-US',
          learning_courses: [],
          created_courses: [],
          total_paid_amount: '0',
          available_credits: '',
          subscription_credits: '',
          topup_credits: '',
          credits_expire_at: '',
          last_login_at: '',
          last_learning_at: '',
          created_at: '2026-04-14T10:00:00Z',
          updated_at: '2026-04-14T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationUsersPage />);

    expect(
      await screen.findByText('module.user.defaultUserName'),
    ).toBeInTheDocument();
  });

  test('shows long-term credit label when active credits do not expire', async () => {
    mockGetAdminOperationUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'user-long-term-credits',
          mobile: '',
          email: 'long-term@example.com',
          nickname: 'Long Term',
          user_status: 'paid',
          user_role: 'creator',
          user_roles: ['creator'],
          login_methods: ['email'],
          registration_source: 'email',
          language: 'en-US',
          learning_courses: [],
          created_courses: [],
          total_paid_amount: '0',
          available_credits: '12',
          subscription_credits: '12',
          topup_credits: '0',
          credits_expire_at: '',
          last_login_at: '',
          last_learning_at: '',
          created_at: '2026-04-14T10:00:00Z',
          updated_at: '2026-04-14T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    render(<AdminOperationUsersPage />);

    expect(
      await screen.findByText('module.operationsUser.credits.longTerm'),
    ).toBeInTheDocument();
  });

  test('requests the selected page when the user list pagination changes', async () => {
    mockGetAdminOperationUsers.mockResolvedValueOnce({
      items: [
        {
          user_bid: 'user-1',
          mobile: '13812345678',
          email: 'user-1@example.com',
          nickname: 'Nick',
          user_status: 'paid',
          user_role: 'operator',
          user_roles: ['operator'],
          login_methods: ['phone'],
          registration_source: 'google',
          language: 'zh-CN',
          learning_courses: [],
          created_courses: [],
          total_paid_amount: '88.50',
          available_credits: '55',
          subscription_credits: '40',
          topup_credits: '15',
          credits_expire_at: '',
          last_login_at: '2026-04-15T09:00:00Z',
          last_learning_at: '2026-04-15T10:00:00Z',
          created_at: '2026-04-14T10:00:00Z',
          updated_at: '2026-04-14T11:00:00Z',
        },
      ],
      page: 1,
      page_count: 2,
      page_size: 20,
      total: 21,
    });
    mockGetAdminOperationUsers.mockResolvedValueOnce({
      items: [],
      page: 2,
      page_count: 2,
      page_size: 20,
      total: 21,
    });

    render(<AdminOperationUsersPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenCalledWith(
        expect.objectContaining({
          page_index: 1,
          page_size: 20,
        }),
      );
    });

    fireEvent.click(
      await screen.findByRole('link', {
        name: '2',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page_index: 2,
          page_size: 20,
        }),
      );
    });
  });
});

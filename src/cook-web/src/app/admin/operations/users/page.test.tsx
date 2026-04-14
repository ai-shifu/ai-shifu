import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import AdminOperationUsersPage from './page';

const mockReplace = jest.fn();
const originalLocation = window.location;
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
    <a href={href} {...props}>
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
  Dialog: ({
    open,
    children,
  }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
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
          last_login_at: '2026-04-15 09:00:00',
          last_learning_at: '2026-04-15 10:00:00',
          created_at: '2026-04-14 10:00:00',
          updated_at: '2026-04-14 11:00:00',
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
      screen.getByRole('button', { name: '1' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '2' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'user-1@example.com' })).toHaveAttribute(
      'href',
      '/admin/operations/users/user-1',
    );
  });

  test('submits search filters', async () => {
    render(<AdminOperationUsersPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUsers).toHaveBeenCalledTimes(1);
    });

    const userIdInput = screen.getAllByRole('textbox')[0];
    fireEvent.change(userIdInput, { target: { value: 'user-22' } });
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.expand' }),
    );

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
      screen.getByRole('button', { name: '2' }),
    );

    expect(
      screen.getByText('module.operationsUser.courseSummary.dialog.createdTitle'),
    ).toBeInTheDocument();
    expect(screen.getByText('Created Course')).toBeInTheDocument();
    expect(screen.getByText('course-2')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.statusLabels.unpublished'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Created Course' })).toHaveAttribute(
      'href',
      '/admin/operations/course-2',
    );
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
          last_login_at: '',
          last_learning_at: '',
          created_at: '2026-04-14 10:00:00',
          updated_at: '2026-04-14 11:00:00',
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
});

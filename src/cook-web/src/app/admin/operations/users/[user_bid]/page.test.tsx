import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import AdminOperationUserDetailPage from './page';

const mockPush = jest.fn();
const mockRefresh = jest.fn();
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

const mockGetAdminOperationUserDetail =
  api.getAdminOperationUserDetail as jest.Mock;

describe('AdminOperationUserDetailPage', () => {
  beforeEach(() => {
    currentUserBid = 'user-1';
    mockPush.mockReset();
    mockRefresh.mockReset();
    mockGetAdminOperationUserDetail.mockReset();
    mockGetAdminOperationUserDetail.mockResolvedValue({
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
      last_login_at: '2026-04-15 09:00:00',
      last_learning_at: '2026-04-15 10:00:00',
      created_at: '2026-04-14 10:00:00',
      updated_at: '2026-04-14 11:00:00',
    });
  });

  test('loads and renders user detail', async () => {
    render(<AdminOperationUserDetailPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationUserDetail).toHaveBeenCalledWith({
        user_bid: 'user-1',
      });
    });

    expect(
      await screen.findByText('module.operationsUser.detail.title'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('Nick').length).toBeGreaterThan(0);
    expect(screen.getByText('user-1@example.com')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsUser.roleLabels.operator'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Learned Course' }),
    ).toHaveAttribute('href', '/admin/operations/course-1');
    expect(screen.getByText('25% (1/4)')).toBeInTheDocument();
    expect(screen.getByText('¥88.50')).toBeInTheDocument();
    expect(
      screen.getAllByText(
        'module.operationsUser.registrationSourceLabels.google',
      ).length,
    ).toBeGreaterThan(0);
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

  test('uses course status translations for unknown course states', async () => {
    mockGetAdminOperationUserDetail.mockResolvedValueOnce({
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
      last_login_at: '',
      last_learning_at: '',
      created_at: '2026-04-14 10:00:00',
      updated_at: '2026-04-14 11:00:00',
    });

    render(<AdminOperationUserDetailPage />);

    expect(
      await screen.findByText('module.operationsCourse.statusLabels.unknown'),
    ).toBeInTheDocument();
  });

  test('shows localized unknown labels for unexpected login methods and course statuses', async () => {
    mockGetAdminOperationUserDetail.mockResolvedValueOnce({
      user_bid: 'user-1',
      mobile: '',
      email: 'user-1@example.com',
      nickname: 'Nick',
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
      last_login_at: '',
      last_learning_at: '',
      created_at: '2026-04-14 10:00:00',
      updated_at: '2026-04-14 11:00:00',
    });

    render(<AdminOperationUserDetailPage />);

    expect(
      await screen.findByText('module.operationsUser.loginMethodLabels.unknown'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.statusLabels.unknown (archived)'),
    ).toBeInTheDocument();
  });

  test('uses default user name when nickname is empty', async () => {
    mockGetAdminOperationUserDetail.mockResolvedValueOnce({
      user_bid: 'user-1',
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
    });

    render(<AdminOperationUserDetailPage />);

    expect(
      await screen.findAllByText('module.user.defaultUserName'),
    ).toHaveLength(1);
  });

  test('shows only the first ten courses until expanded', async () => {
    mockGetAdminOperationUserDetail.mockResolvedValueOnce({
      user_bid: 'user-1',
      mobile: '13812345678',
      email: 'user-1@example.com',
      nickname: 'Nick',
      user_status: 'paid',
      user_role: 'learner',
      user_roles: ['learner'],
      login_methods: ['email'],
      registration_source: 'email',
      language: 'zh-CN',
      learning_courses: Array.from({ length: 11 }, (_, index) => ({
        shifu_bid: `course-${index + 1}`,
        course_name: `Learning Course ${index + 1}`,
        course_status: 'published',
        completed_lesson_count: index,
        total_lesson_count: 12,
      })),
      created_courses: [],
      total_paid_amount: '0',
      last_login_at: '',
      last_learning_at: '',
      created_at: '2026-04-14 10:00:00',
      updated_at: '2026-04-14 11:00:00',
    });

    render(<AdminOperationUserDetailPage />);

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

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.collapse module.operationsUser.detail.learningCourses',
      }),
    );

    await waitFor(() => {
      expect(
        screen.queryByRole('link', { name: 'Learning Course 11' }),
      ).not.toBeInTheDocument();
    });
  });

  test('collapses expanded course tables after switching to another user', async () => {
    mockGetAdminOperationUserDetail.mockImplementation(
      ({ user_bid }: { user_bid: string }) => ({
        user_bid,
        mobile: '',
        email: `${user_bid}@example.com`,
        nickname: user_bid,
        user_status: 'registered',
        user_role: 'learner',
        user_roles: ['learner'],
        login_methods: ['email'],
        registration_source: 'email',
        language: 'en-US',
        learning_courses: Array.from({ length: 11 }, (_, index) => ({
          shifu_bid: `${user_bid}-course-${index + 1}`,
          course_name: `${user_bid} course ${index + 1}`,
          course_status: 'published',
          completed_lesson_count: index,
          total_lesson_count: 12,
        })),
        created_courses: [],
        total_paid_amount: '0',
        last_login_at: '',
        last_learning_at: '',
        created_at: '2026-04-14 10:00:00',
        updated_at: '2026-04-14 11:00:00',
      }),
    );

    const { rerender } = render(<AdminOperationUserDetailPage />);

    expect(
      await screen.findByRole('link', { name: 'user-1 course 10' }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.expand module.operationsUser.detail.learningCourses',
      }),
    );

    expect(
      await screen.findByRole('link', { name: 'user-1 course 11' }),
    ).toBeInTheDocument();

    currentUserBid = 'user-2';
    rerender(<AdminOperationUserDetailPage />);

    expect(
      await screen.findByRole('link', { name: 'user-2 course 10' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.queryByRole('link', { name: 'user-2 course 11' }),
      ).not.toBeInTheDocument();
    });
  });

  test('shows an error when the route param cannot be decoded', async () => {
    currentUserBid = '%E0%A4%A';

    render(<AdminOperationUserDetailPage />);

    expect(
      await screen.findByText('server.common.paramsError'),
    ).toBeInTheDocument();
    expect(mockGetAdminOperationUserDetail).not.toHaveBeenCalled();
  });
});

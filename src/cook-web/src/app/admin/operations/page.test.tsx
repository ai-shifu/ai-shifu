import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import api from '@/api';
import OperationsPage from './page';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockToast = jest.fn();
const originalLocation = window.location;

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
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCourses: jest.fn(),
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
  useTranslation: (namespace?: string | string[]) => {
    const ns = Array.isArray(namespace) ? namespace[0] : namespace;
    return {
      t: (key: string, params?: { count?: number }) => {
        const resolvedKey = ns && ns !== 'translation' ? `${ns}.${key}` : key;
        return params?.count !== undefined
          ? `${resolvedKey}:${params.count}`
          : resolvedKey;
      },
    };
  },
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: mockToast,
  }),
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage: string }) => (
    <div>{errorMessage}</div>
  ),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ui/DropdownMenu', () => {
  const React = jest.requireActual<typeof import('react')>('react');

  type DropdownContextValue = {
    open: boolean;
    setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  };

  const DropdownContext = React.createContext<DropdownContextValue | null>(
    null,
  );

  const useDropdownContext = () => {
    const context = React.useContext(DropdownContext);
    if (!context) {
      throw new Error('DropdownMenu mock must be used within DropdownMenu');
    }
    return context;
  };

  const composeHandlers =
    <Event,>(...handlers: Array<((event: Event) => void) | undefined>) =>
    (event: Event) => {
      handlers.forEach(handler => handler?.(event));
    };

  return {
    __esModule: true,
    DropdownMenu: ({ children }: { children: React.ReactNode }) => {
      const [open, setOpen] = React.useState(false);
      return (
        <DropdownContext.Provider value={{ open, setOpen }}>
          {children}
        </DropdownContext.Provider>
      );
    },
    DropdownMenuTrigger: ({
      children,
      asChild,
    }: {
      children: React.ReactNode;
      asChild?: boolean;
    }) => {
      const { open, setOpen } = useDropdownContext();

      if (asChild && React.isValidElement(children)) {
        const child = children as React.ReactElement<{
          onClick?: (event: React.MouseEvent) => void;
          'aria-expanded'?: boolean;
        }>;
        return React.cloneElement(child, {
          onClick: composeHandlers(child.props.onClick, () =>
            setOpen(previous => !previous),
          ),
          'aria-expanded': open,
        });
      }

      return (
        <button
          type='button'
          onClick={() => setOpen(previous => !previous)}
        >
          {children}
        </button>
      );
    },
    DropdownMenuContent: ({ children }: { children: React.ReactNode }) => {
      const { open } = useDropdownContext();
      if (!open) {
        return null;
      }
      return <div role='menu'>{children}</div>;
    },
    DropdownMenuItem: ({
      children,
      onClick,
    }: {
      children: React.ReactNode;
      onClick?: () => void;
    }) => {
      const { setOpen } = useDropdownContext();
      return (
        <button
          type='button'
          role='menuitem'
          onClick={() => {
            onClick?.();
            setOpen(false);
          }}
        >
          {children}
        </button>
      );
    },
  };
});

const mockGetAdminOperationCourses = api.getAdminOperationCourses as jest.Mock;

describe('OperationsPage', () => {
  const renderAndWaitForLoadedPage = async () => {
    render(<OperationsPage />);

    await waitFor(() => {
      expect(mockGetAdminOperationCourses).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.queryByTestId('loading-indicator')).not.toBeInTheDocument();
    });
  };

  beforeAll(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        href: '',
        pathname: '/admin/operations',
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

  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    mockToast.mockReset();
    mockGetAdminOperationCourses.mockReset();
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = {
      is_operator: true,
    };
    Object.assign(window.location, {
      href: '',
      pathname: '/admin/operations',
      search: '',
    });

    mockGetAdminOperationCourses.mockResolvedValue({
      items: [
        {
          shifu_bid: 'course-1',
          course_name: 'Course 1',
          price: '99',
          creator_user_bid: 'creator-1',
          creator_mobile: '15811112222',
          creator_email: 'creator@example.com',
          creator_nickname: 'Creator Mars',
          updater_user_bid: 'editor-1',
          updater_mobile: '15833334444',
          updater_email: 'editor@example.com',
          updater_nickname: '',
          created_at: '2025-04-01 10:00:00',
          updated_at: '2025-04-02 10:00:00',
        },
        {
          shifu_bid: 'course-system-custom',
          course_name: 'Custom System Course',
          price: '0',
          creator_user_bid: 'system',
          creator_mobile: '',
          creator_email: '',
          creator_nickname: '',
          updater_user_bid: 'system',
          updater_mobile: '',
          updater_email: '',
          updater_nickname: '',
          created_at: '2025-04-03 10:00:00',
          updated_at: '2025-04-03 10:00:00',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 2,
    });
  });

  test('loads and renders operator course list in email mode', async () => {
    await renderAndWaitForLoadedPage();

    expect(mockGetAdminOperationCourses).toHaveBeenCalledWith(
      expect.objectContaining({
        page_index: 1,
        page_size: 20,
        shifu_bid: '',
        course_name: '',
        creator_keyword: '',
        start_time: '',
        end_time: '',
        updated_start_time: '',
        updated_end_time: '',
      }),
    );

    expect(screen.getByText('Course 1')).toBeInTheDocument();
    expect(screen.getByText('creator@example.com')).toBeInTheDocument();
    expect(screen.getByText('Creator Mars')).toBeInTheDocument();
    expect(screen.getByText('editor@example.com')).toBeInTheDocument();
    expect(screen.getByText('module.user.defaultUserName')).toBeInTheDocument();

    const systemRow = screen.getByText('Custom System Course').closest('tr');
    expect(systemRow).not.toBeNull();
    const scopedRow = within(systemRow as HTMLElement);
    expect(scopedRow.getAllByText('system')).toHaveLength(2);
    expect(
      scopedRow.queryByText('module.user.defaultUserName'),
    ).not.toBeInTheDocument();
  });

  test('navigates from course name and fires placeholder action toast', async () => {
    await renderAndWaitForLoadedPage();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Course 1',
      }),
    );
    expect(mockPush).toHaveBeenCalledWith('/admin/operations/course-1');

    const firstRow = screen.getByText('Course 1').closest('tr');
    expect(firstRow).not.toBeNull();
    const moreButton = within(firstRow as HTMLElement).getByRole('button', {
      name: 'common.core.more',
    });
    expect(
      screen.queryByRole('menuitem', {
        name: 'module.operationsCourse.actions.transferCreator',
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(moreButton);

    const transferCreatorMenuItem = await screen.findByRole('menuitem', {
      name: 'module.operationsCourse.actions.transferCreator',
    });

    fireEvent.click(transferCreatorMenuItem);

    expect(mockToast).toHaveBeenCalledWith({
      title: 'common.core.waitingForCompletion',
    });
  });

  test('clears search input with the right-side clear action', async () => {
    await renderAndWaitForLoadedPage();
    const courseIdInput = screen.getByPlaceholderText(
      'module.operationsCourse.filters.courseId',
    ) as HTMLInputElement;

    fireEvent.change(courseIdInput, {
      target: { value: 'course-1' },
    });
    expect(courseIdInput.value).toBe('course-1');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.chat.lessonFeedbackClearInput',
      }),
    );

    expect(courseIdInput.value).toBe('');
  });

  test('redirects non-operators back to admin', async () => {
    mockUserState.userInfo = {
      is_operator: false,
    };

    render(<OperationsPage />);

    expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
  });

  test('redirects guests to login with encoded current path', async () => {
    mockUserState.isGuest = true;
    Object.assign(window.location, {
      href: '',
      pathname: '/admin/operations',
      search: '?tab=list',
    });

    render(<OperationsPage />);

    await waitFor(() => {
      expect(window.location.href).toContain(
        '/login?redirect=%2Fadmin%2Foperations%3Ftab%3Dlist',
      );
    });
  });
});

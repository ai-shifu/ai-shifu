import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import api from '@/api';
import { ErrorWithCode } from '@/lib/request';
import OperationsPage from './page';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockToast = jest.fn();
const mockErrorDisplay = jest.fn();
const mockCopyText = jest.fn();
const originalLocation = window.location;
const originalFetch = global.fetch;
const originalWindow = global.window;
const RETRY_LABEL = 'retry';
const LONG_COURSE_PROMPT =
  'You are a patient course assistant. Help learners build understanding step by step, summarize key ideas clearly, and always connect each answer back to the course context.';
const DEFAULT_OVERVIEW = {
  total_course_count: 24,
  draft_course_count: 8,
  published_course_count: 16,
  created_last_7d_course_count: 5,
  learning_active_30d_course_count: 11,
  paid_order_30d_course_count: 7,
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
    push: mockPush,
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCourses: jest.fn(),
    getAdminOperationCoursePrompt: jest.fn(),
    transferAdminOperationCourseCreator: jest.fn(),
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

jest.mock('@/c-utils/textutils', () => ({
  copyText: (...args: unknown[]) => mockCopyText(...args),
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: (props: {
    errorMessage: string;
    errorCode?: number;
    onRetry?: () => void;
  }) => {
    mockErrorDisplay(props);
    return (
      <div>
        <div>{props.errorMessage}</div>
        <div>{props.errorCode ?? 'no-code'}</div>
        {props.onRetry ? (
          <button
            type='button'
            onClick={props.onRetry}
          >
            {RETRY_LABEL}
          </button>
        ) : null}
      </div>
    );
  },
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
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
  DialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
}));

jest.mock('@/components/ui/AlertDialog', () => ({
  __esModule: true,
  AlertDialog: ({
    open,
    children,
  }: React.PropsWithChildren<{ open?: boolean }>) =>
    open ? <div>{children}</div> : null,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => (
    <div role='alertdialog'>{children}</div>
  ),
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogCancel: ({
    children,
    onClick,
    disabled,
  }: React.PropsWithChildren<{ onClick?: () => void; disabled?: boolean }>) => (
    <button
      type='button'
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  ),
  AlertDialogAction: ({
    children,
    onClick,
    disabled,
  }: React.PropsWithChildren<{ onClick?: () => void; disabled?: boolean }>) => (
    <button
      type='button'
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  ),
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
const mockGetAdminOperationCoursePrompt =
  api.getAdminOperationCoursePrompt as jest.Mock;
const mockTransferAdminOperationCourseCreator =
  api.transferAdminOperationCourseCreator as jest.Mock;

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

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
    mockErrorDisplay.mockReset();
    mockCopyText.mockReset();
    mockGetAdminOperationCourses.mockReset();
    mockGetAdminOperationCoursePrompt.mockReset();
    mockTransferAdminOperationCourseCreator.mockReset();
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
      summary: DEFAULT_OVERVIEW,
      items: [
        {
          shifu_bid: 'course-1',
          course_name: 'Course 1',
          course_status: 'published',
          price: '99',
          course_model: 'gpt-4.1-mini',
          has_course_prompt: true,
          creator_user_bid: 'creator-1',
          creator_mobile: '15811112222',
          creator_email: 'creator@example.com',
          creator_nickname: 'Creator Mars',
          updater_user_bid: 'editor-1',
          updater_mobile: '15833334444',
          updater_email: 'editor@example.com',
          updater_nickname: '',
          created_at: '2025-04-01T10:00:00Z',
          updated_at: '2025-04-02T10:00:00Z',
        },
        {
          shifu_bid: 'course-system-custom',
          course_name: 'Custom System Course',
          course_status: 'unpublished',
          price: '0',
          course_model: '',
          has_course_prompt: false,
          creator_user_bid: 'system',
          creator_mobile: '',
          creator_email: '',
          creator_nickname: '',
          updater_user_bid: 'system',
          updater_mobile: '',
          updater_email: '',
          updater_nickname: '',
          created_at: '2025-04-03T10:00:00Z',
          updated_at: '2025-04-03T10:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 2,
    });
    mockGetAdminOperationCoursePrompt.mockResolvedValue({
      course_prompt: LONG_COURSE_PROMPT,
    });
    mockTransferAdminOperationCourseCreator.mockResolvedValue({});
  });

  afterEach(() => {
    global.fetch = originalFetch;
    Object.defineProperty(global, 'window', {
      configurable: true,
      value: originalWindow,
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
        course_status: '',
        start_time: '',
        end_time: '',
        updated_start_time: '',
        updated_end_time: '',
      }),
    );

    expect(screen.getByText('Course 1')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.overview.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('24')).toBeInTheDocument();
    expect(screen.getByText('11')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsCourse.overview.tooltips.totalCourses',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('gpt-4.1-mini')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'module.operationsCourse.table.detailAction',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('creator@example.com')).toBeInTheDocument();
    expect(screen.getByText('Creator Mars')).toBeInTheDocument();
    expect(screen.getByText('editor@example.com')).toBeInTheDocument();
    expect(screen.getByText('module.user.defaultUserName')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.statusLabels.published'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.statusLabels.unpublished'),
    ).toBeInTheDocument();

    const systemRow = screen.getByText('Custom System Course').closest('tr');
    expect(systemRow).not.toBeNull();
    const scopedRow = within(systemRow as HTMLElement);
    expect(scopedRow.getAllByText('system')).toHaveLength(2);
    expect(
      scopedRow.queryByText('module.user.defaultUserName'),
    ).not.toBeInTheDocument();
  });

  test('navigates from course name and transfers creator from the action menu', async () => {
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

    expect(
      screen.getByText('module.operationsCourse.transferCreatorDialog.title'),
    ).toBeInTheDocument();
    const transferDialog = screen.getByRole('dialog');
    expect(
      within(transferDialog).getByText(
        'module.operationsCourse.table.courseName',
      ),
    ).toBeInTheDocument();
    expect(
      within(transferDialog).getByText('creator@example.com'),
    ).toBeInTheDocument();
    expect(within(transferDialog).getByText('Course 1')).toBeInTheDocument();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.transferCreatorDialog.contactPlaceholderEmail',
      ),
      {
        target: { value: 'next-creator@example.com' },
      },
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.transferCreatorDialog.confirm',
      }),
    );

    const confirmDialog = screen.getByRole('alertdialog');
    expect(
      within(confirmDialog).getByText(
        'module.operationsCourse.transferCreatorDialog.confirmTitle',
      ),
    ).toBeInTheDocument();
    expect(within(confirmDialog).getByText('Course 1')).toBeInTheDocument();
    expect(
      within(confirmDialog).getByText('creator@example.com'),
    ).toBeInTheDocument();
    expect(
      within(confirmDialog).getByText('next-creator@example.com'),
    ).toBeInTheDocument();

    fireEvent.click(
      within(confirmDialog).getByRole('button', {
        name: 'module.operationsCourse.transferCreatorDialog.confirm',
      }),
    );

    await waitFor(() => {
      expect(mockTransferAdminOperationCourseCreator).toHaveBeenCalledWith({
        shifu_bid: 'course-1',
        contact_type: 'email',
        identifier: 'next-creator@example.com',
      });
    });

    await waitFor(() => {
      expect(mockGetAdminOperationCourses).toHaveBeenCalledTimes(2);
    });

    expect(mockToast).toHaveBeenCalledWith({
      title: 'module.operationsCourse.transferCreatorDialog.submitSuccess',
    });
    expect(
      screen.queryByText('module.operationsCourse.transferCreatorDialog.title'),
    ).not.toBeInTheDocument();
  });

  test('opens course prompt detail dialog and toggles expand state', async () => {
    const scrollHeightSpy = jest
      .spyOn(HTMLElement.prototype, 'scrollHeight', 'get')
      .mockReturnValue(160);
    const clientHeightSpy = jest
      .spyOn(HTMLElement.prototype, 'clientHeight', 'get')
      .mockReturnValue(72);
    const scrollWidthSpy = jest
      .spyOn(HTMLElement.prototype, 'scrollWidth', 'get')
      .mockReturnValue(0);
    const clientWidthSpy = jest
      .spyOn(HTMLElement.prototype, 'clientWidth', 'get')
      .mockReturnValue(0);

    try {
      await renderAndWaitForLoadedPage();

      const firstRow = screen.getByText('Course 1').closest('tr');
      expect(firstRow).not.toBeNull();

      fireEvent.click(
        within(firstRow as HTMLElement).getByRole('button', {
          name: 'module.operationsCourse.table.detailAction',
        }),
      );

      await waitFor(() => {
        expect(mockGetAdminOperationCoursePrompt).toHaveBeenCalledWith({
          shifu_bid: 'course-1',
        });
      });

      expect(
        screen.getByText('module.operationsCourse.coursePromptDialog.title'),
      ).toBeInTheDocument();
      expect(await screen.findByText(LONG_COURSE_PROMPT)).toBeInTheDocument();
      const promptDialog = screen.getByRole('dialog');

      fireEvent.click(
        within(promptDialog).getByRole('button', {
          name: 'module.operationsCourse.coursePromptDialog.copy',
        }),
      );

      await waitFor(() => {
        expect(mockCopyText).toHaveBeenCalledWith(LONG_COURSE_PROMPT);
      });

      fireEvent.click(
        await within(promptDialog).findByRole('button', {
          name: 'common.core.expand',
        }),
      );

      expect(
        within(promptDialog).getByRole('button', {
          name: 'common.core.collapse',
        }),
      ).toBeInTheDocument();
    } finally {
      scrollHeightSpy.mockRestore();
      clientHeightSpy.mockRestore();
      scrollWidthSpy.mockRestore();
      clientWidthSpy.mockRestore();
    }
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

  test('searches by course status', async () => {
    await renderAndWaitForLoadedPage();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.expand',
      }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.statusLabels.published',
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    await waitFor(() => {
      expect(mockGetAdminOperationCourses).toHaveBeenLastCalledWith(
        expect.objectContaining({
          course_status: 'published',
        }),
      );
    });
  });

  test('shows inline validation and request errors for transfer creator', async () => {
    mockTransferAdminOperationCourseCreator.mockRejectedValueOnce(
      new Error('transfer failed'),
    );

    await renderAndWaitForLoadedPage();

    const firstRow = screen.getByText('Course 1').closest('tr');
    expect(firstRow).not.toBeNull();

    fireEvent.click(
      within(firstRow as HTMLElement).getByRole('button', {
        name: 'common.core.more',
      }),
    );
    fireEvent.click(
      await screen.findByRole('menuitem', {
        name: 'module.operationsCourse.actions.transferCreator',
      }),
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.transferCreatorDialog.contactPlaceholderEmail',
      ),
      {
        target: { value: 'creator@example.com' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.transferCreatorDialog.confirm',
      }),
    );

    expect(
      await screen.findByText(
        'module.operationsCourse.transferCreatorDialog.sameCreator',
      ),
    ).toBeInTheDocument();
    expect(mockTransferAdminOperationCourseCreator).not.toHaveBeenCalled();

    fireEvent.change(
      screen.getByPlaceholderText(
        'module.operationsCourse.transferCreatorDialog.contactPlaceholderEmail',
      ),
      {
        target: { value: 'valid@example.com' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.transferCreatorDialog.confirm',
      }),
    );

    const confirmDialog = screen.getByRole('alertdialog');
    fireEvent.click(
      within(confirmDialog).getByRole('button', {
        name: 'module.operationsCourse.transferCreatorDialog.confirm',
      }),
    );

    expect(await screen.findByText('transfer failed')).toBeInTheDocument();
    expect(mockTransferAdminOperationCourseCreator).toHaveBeenCalledWith({
      shifu_bid: 'course-1',
      contact_type: 'email',
      identifier: 'valid@example.com',
    });
  });

  test('retries the last requested page after a page change fails', async () => {
    mockGetAdminOperationCourses.mockResolvedValueOnce({
      summary: DEFAULT_OVERVIEW,
      items: [
        {
          shifu_bid: 'course-1',
          course_name: 'Course 1',
          course_status: 'published',
          price: '99',
          course_model: 'gpt-4.1-mini',
          has_course_prompt: true,
          creator_user_bid: 'creator-1',
          creator_mobile: '15811112222',
          creator_email: 'creator@example.com',
          creator_nickname: 'Creator Mars',
          updater_user_bid: 'editor-1',
          updater_mobile: '15833334444',
          updater_email: 'editor@example.com',
          updater_nickname: '',
          created_at: '2025-04-01T10:00:00Z',
          updated_at: '2025-04-02T10:00:00Z',
        },
      ],
      page: 1,
      page_count: 2,
      page_size: 20,
      total: 2,
    });
    mockGetAdminOperationCourses.mockRejectedValueOnce(
      new ErrorWithCode('load failed', 418),
    );
    mockGetAdminOperationCourses.mockResolvedValueOnce({
      summary: DEFAULT_OVERVIEW,
      items: [],
      page: 2,
      page_count: 2,
      page_size: 20,
      total: 2,
    });

    await renderAndWaitForLoadedPage();

    fireEvent.click(
      screen.getByRole('link', {
        name: '2',
      }),
    );

    expect(await screen.findByText('load failed')).toBeInTheDocument();
    expect(screen.getByText('418')).toBeInTheDocument();
    expect(mockErrorDisplay).toHaveBeenLastCalledWith(
      expect.objectContaining({
        errorCode: 418,
        errorMessage: 'load failed',
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'retry' }));

    await waitFor(() => {
      expect(mockGetAdminOperationCourses).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page_index: 2,
        }),
      );
    });
  });

  test('ignores stale responses when a newer search finishes later', async () => {
    const firstSearch = createDeferred<{
      summary: typeof DEFAULT_OVERVIEW;
      items: Array<Record<string, string | boolean>>;
      page: number;
      page_count: number;
      page_size: number;
      total: number;
    }>();
    const secondSearch = createDeferred<{
      summary: typeof DEFAULT_OVERVIEW;
      items: Array<Record<string, string | boolean>>;
      page: number;
      page_count: number;
      page_size: number;
      total: number;
    }>();

    await renderAndWaitForLoadedPage();

    const courseIdInput = screen.getByPlaceholderText(
      'module.operationsCourse.filters.courseId',
    ) as HTMLInputElement;

    mockGetAdminOperationCourses.mockImplementationOnce(
      () => firstSearch.promise,
    );
    fireEvent.change(courseIdInput, {
      target: { value: 'course-first' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    mockGetAdminOperationCourses.mockImplementationOnce(
      () => secondSearch.promise,
    );
    fireEvent.change(courseIdInput, {
      target: { value: 'course-second' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.filters.search',
      }),
    );

    secondSearch.resolve({
      summary: DEFAULT_OVERVIEW,
      items: [
        {
          shifu_bid: 'course-second',
          course_name: 'Course Second',
          course_status: 'published',
          price: '29',
          course_model: 'gpt-4.1',
          has_course_prompt: true,
          creator_user_bid: 'creator-2',
          creator_mobile: '15899990000',
          creator_email: 'second@example.com',
          creator_nickname: 'Second Creator',
          updater_user_bid: 'editor-2',
          updater_mobile: '15899991111',
          updater_email: 'editor-second@example.com',
          updater_nickname: '',
          created_at: '2025-04-05T10:00:00Z',
          updated_at: '2025-04-06T10:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    expect(await screen.findByText('Course Second')).toBeInTheDocument();

    firstSearch.resolve({
      summary: DEFAULT_OVERVIEW,
      items: [
        {
          shifu_bid: 'course-first',
          course_name: 'Course First',
          course_status: 'published',
          price: '19',
          course_model: 'gpt-4.1',
          has_course_prompt: true,
          creator_user_bid: 'creator-1',
          creator_mobile: '15888880000',
          creator_email: 'first@example.com',
          creator_nickname: 'First Creator',
          updater_user_bid: 'editor-1',
          updater_mobile: '15888881111',
          updater_email: 'editor-first@example.com',
          updater_nickname: '',
          created_at: '2025-04-03T10:00:00Z',
          updated_at: '2025-04-04T10:00:00Z',
        },
      ],
      page: 1,
      page_count: 1,
      page_size: 20,
      total: 1,
    });

    await waitFor(() => {
      expect(screen.getByText('Course Second')).toBeInTheDocument();
      expect(screen.queryByText('Course First')).not.toBeInTheDocument();
    });
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

  test('keeps waiting when logged-in user info is temporarily unavailable', async () => {
    mockUserState.userInfo = null;

    render(<OperationsPage />);

    expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetAdminOperationCourses).not.toHaveBeenCalled();
      expect(mockReplace).not.toHaveBeenCalled();
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

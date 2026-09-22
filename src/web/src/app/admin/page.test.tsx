import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { copyText } from '@/lib/textutils';

import AdminPage from './page';

const mockPush = jest.fn();
const mockTrackEvent = jest.fn();
const mockToast = jest.fn();
let mockCourseCreatorUrl: string | null = null;
const mockT = (key: string) => key;
const mockI18n = {
  language: 'en-US',
};
const CLOSE_IMPORT_LABEL = 'close-import';
const CLOSE_REDEMPTION_LABEL = 'close-redemption';
const SUBMIT_COURSE_LABEL = 'component.courseCreationChoiceDialog.manualAction';
const CANCEL_COURSE_LABEL = 'component.header.close';
const CHOOSE_AI_COURSE_LABEL =
  'component.courseCreationChoiceDialog.guideAction';
const COPY_AI_COURSE_PROMPT_LABEL =
  'component.courseCreationChoiceDialog.copyAction';

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

jest.mock('next/link', () => {
  function MockLink({
    children,
    href,
  }: React.PropsWithChildren<{ href: string }>) {
    return <a href={href}>{children}</a>;
  }

  MockLink.displayName = 'MockLink';

  return MockLink;
});

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    ensureAdminCreator: jest.fn(),
    getShifuList: jest.fn(),
    createShifu: jest.fn(),
    archiveShifu: jest.fn(),
    unarchiveShifu: jest.fn(),
  },
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (
    selector: (state: {
      isInitialized: boolean;
      isGuest: boolean;
      isLoggedIn: boolean;
      userInfo: { user_id: string };
    }) => unknown,
  ) =>
    selector({
      isInitialized: true,
      isGuest: false,
      isLoggedIn: true,
      userInfo: { user_id: 'user-1' },
    }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: mockToast,
  }),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
}));

jest.mock('@/hooks/useOnboarding', () => ({
  useCreatorOnboardingStatus: () => ({
    data: null,
  }),
}));

jest.mock('@/lib/urlUtils', () => ({
  getCourseCreatorUrl: () => mockCourseCreatorUrl,
}));

jest.mock('@/lib/textutils', () => ({
  copyText: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('@/lib/onboardingTargets', () => ({
  ...jest.requireActual('@/lib/onboardingTargets'),
  buildGuideCourseTargetId: () => undefined,
}));

jest.mock('@/lib/shifu-permissions', () => ({
  canManageArchive: () => true,
  canManageOwnerCourseAction: (
    shifu: { created_user_bid?: string } | null | undefined,
    currentUserId: string,
  ) => shifu?.created_user_bid === currentUserId,
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockT,
    i18n: mockI18n,
  }),
}));

jest.mock('@/components/ui/Tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({
    children,
    value,
  }: React.PropsWithChildren<{ value: string }>) => (
    <button type='button'>{children || value}</button>
  ),
}));

jest.mock('@/components/ui/Button', () => ({
  Button: ({
    children,
    onClick,
    ...props
  }: React.PropsWithChildren<{
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
  }>) => (
    <button
      type='button'
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/Card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/components/ui/Badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}));

jest.mock('@/components/ui/DropdownMenu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DropdownMenuItem: ({
    children,
    onSelect,
  }: React.PropsWithChildren<{
    onSelect?: (event: { stopPropagation: () => void }) => void;
  }>) => (
    <button
      type='button'
      onClick={() => onSelect?.({ stopPropagation: () => undefined })}
    >
      {children}
    </button>
  ),
}));

jest.mock('@/components/ui/AlertDialog', () => ({
  AlertDialog: ({
    open,
    children,
  }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  AlertDialogAction: ({
    children,
    onClick,
  }: React.PropsWithChildren<{
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
  }>) => (
    <button
      type='button'
      onClick={onClick}
    >
      {children}
    </button>
  ),
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => (
    <button type='button'>{children}</button>
  ),
  AlertDialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => (
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

jest.mock('@/components/MobileUnsupportedDialog', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/components/shifu-setting/ShifuPermissionDialog', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('./components/AdminTitle', () => ({
  __esModule: true,
  default: ({ title }: { title: string }) => <div>{title}</div>,
}));

jest.mock('@/components/order/ImportActivationDialog', () => ({
  __esModule: true,
  default: ({
    open,
    initialCourseId,
    initialCourseName,
    onOpenChange,
  }: {
    open: boolean;
    initialCourseId?: string;
    initialCourseName?: string;
    onOpenChange: (open: boolean) => void;
  }) => (
    <div
      data-testid='import-activation-dialog'
      data-open={String(open)}
    >
      <div data-testid='import-course-id'>{initialCourseId || 'none'}</div>
      <div data-testid='import-course-name'>{initialCourseName || 'none'}</div>
      <button
        type='button'
        onClick={() => onOpenChange(false)}
      >
        {CLOSE_IMPORT_LABEL}
      </button>
    </div>
  ),
}));

jest.mock('./orders/CreatorRedemptionCodeDialog', () => ({
  __esModule: true,
  default: ({
    open,
    initialShifuBid,
    initialShifuName,
    onOpenChange,
  }: {
    open: boolean;
    initialShifuBid?: string;
    initialShifuName?: string;
    onOpenChange: (open: boolean) => void;
  }) => (
    <div
      data-testid='creator-redemption-dialog'
      data-open={String(open)}
    >
      <div data-testid='redemption-shifu-id'>{initialShifuBid || 'none'}</div>
      <div data-testid='redemption-shifu-name'>
        {initialShifuName || 'none'}
      </div>
      <button
        type='button'
        onClick={() => onOpenChange(false)}
      >
        {CLOSE_REDEMPTION_LABEL}
      </button>
    </div>
  ),
}));

const fillManualCourseForm = () => {
  fireEvent.change(
    screen.getByLabelText('component.createShifuDialog.nameLabel'),
    { target: { value: 'Sensitive course name' } },
  );
  fireEvent.change(
    screen.getByLabelText('component.createShifuDialog.descriptionLabel'),
    { target: { value: 'Sensitive course description' } },
  );
};

const mockEnsureAdminCreator = api.ensureAdminCreator as jest.Mock;
const mockGetShifuList = api.getShifuList as jest.Mock;
const mockCreateShifu = api.createShifu as jest.Mock;

describe('AdminPage', () => {
  let consoleInfoSpy: jest.SpyInstance;

  beforeEach(() => {
    mockPush.mockReset();
    mockTrackEvent.mockReset();
    mockToast.mockReset();
    (copyText as jest.Mock).mockReset().mockResolvedValue(undefined);
    mockCourseCreatorUrl = null;
    mockEnsureAdminCreator.mockReset();
    mockGetShifuList.mockReset();
    mockCreateShifu.mockReset();
    consoleInfoSpy = jest
      .spyOn(console, 'info')
      .mockImplementation(() => undefined);
    mockEnsureAdminCreator.mockResolvedValue({});
    mockCreateShifu.mockResolvedValue({
      bid: 'course-created-1',
      name: 'Sensitive response name',
    });
    mockGetShifuList.mockResolvedValue({
      items: [
        {
          bid: 'course-1',
          name: 'Course 1',
          description: 'Course description',
          state: 1,
          archived: false,
          avatar: '',
          is_favorite: false,
          created_user_bid: 'user-1',
          can_manage_permissions: true,
        },
      ],
    });

    class MockIntersectionObserver {
      observe() {}
      disconnect() {}
      unobserve() {}
    }

    global.IntersectionObserver =
      MockIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  afterEach(() => {
    consoleInfoSpy.mockRestore();
  });

  test('tracks manual course creation attempts and results without free-form course fields', async () => {
    render(<AdminPage />);
    await screen.findByText('Course 1');

    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    fillManualCourseForm();

    fireEvent.click(screen.getByRole('button', { name: SUBMIT_COURSE_LABEL }));
    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_course_create_attempt',
        { creation_path: 'manual' },
      ),
    );
    expect(mockCreateShifu).toHaveBeenCalledWith({
      name: 'Sensitive course name',
      description: 'Sensitive course description',
      avatar: '',
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'creator_course_create_cancel',
      expect.anything(),
    );
    await waitFor(() =>
      expect(mockPush).toHaveBeenCalledWith(
        '/shifu/course-created-1?onboarding_source=manual_create',
      ),
    );

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_course_create_result',
        {
          creation_path: 'manual',
          outcome: 'success',
          shifu_bid: 'course-created-1',
        },
      ),
    );
    const serializedCalls = JSON.stringify(mockTrackEvent.mock.calls);
    expect(serializedCalls).not.toContain('Sensitive course name');
    expect(serializedCalls).not.toContain('Sensitive response name');
    expect(serializedCalls).not.toContain('Sensitive course description');
    expect(serializedCalls).not.toContain('shifu_name');
    expect(serializedCalls).not.toContain('creator_shifu_create_click');
    expect(serializedCalls).not.toContain('creator_shifu_create_success');
  });

  test('tracks bounded manual failure and explicit cancellation outcomes', async () => {
    mockCreateShifu.mockRejectedValueOnce(
      new Error('raw provider failure must stay out of analytics'),
    );
    render(<AdminPage />);
    await screen.findByText('Course 1');

    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    fillManualCourseForm();
    fireEvent.click(screen.getByRole('button', { name: SUBMIT_COURSE_LABEL }));

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_course_create_result',
        {
          creation_path: 'manual',
          outcome: 'failed',
          failure_category: 'request_failed',
        },
      ),
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'raw provider failure',
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(
      screen.getByLabelText('component.createShifuDialog.nameLabel'),
    ).toHaveValue('Sensitive course name');
    expect(
      screen.getByLabelText('component.createShifuDialog.descriptionLabel'),
    ).toHaveValue('Sensitive course description');

    fireEvent.click(screen.getByRole('button', { name: CANCEL_COURSE_LABEL }));
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_course_create_cancel',
      { creation_path: 'manual' },
    );
  });

  test('counts only engaged manual dismissals and resets engagement when reopened', async () => {
    render(<AdminPage />);
    await screen.findByText('Course 1');
    const openCreation = () =>
      fireEvent.click(
        screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
      );
    const closeCreation = () =>
      fireEvent.click(
        screen.getByRole('button', { name: CANCEL_COURSE_LABEL }),
      );
    const cancellations = () =>
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'creator_course_create_cancel',
      );

    openCreation();
    closeCreation();
    expect(cancellations()).toHaveLength(0);

    openCreation();
    fireEvent.click(
      screen.getByRole('button', { name: COPY_AI_COURSE_PROMPT_LABEL }),
    );
    await screen.findByRole('button', {
      name: 'component.courseCreationChoiceDialog.copiedAction',
    });
    closeCreation();
    expect(cancellations()).toHaveLength(0);

    openCreation();
    fillManualCourseForm();
    closeCreation();
    expect(cancellations()).toEqual([
      ['creator_course_create_cancel', { creation_path: 'manual' }],
    ]);

    openCreation();
    expect(
      screen.getByLabelText('component.createShifuDialog.nameLabel'),
    ).toHaveValue('');
    closeCreation();
    expect(cancellations()).toHaveLength(1);

    openCreation();
    fireEvent.click(screen.getByRole('button', { name: SUBMIT_COURSE_LABEL }));
    await screen.findByText('component.createShifuDialog.nameRequired');
    expect(mockCreateShifu).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'creator_course_create_attempt',
      expect.anything(),
    );
    closeCreation();
    expect(cancellations()).toHaveLength(2);
  });

  test('blocks pending manual dismissal and allows retry after a failed creation', async () => {
    let rejectCreation!: (error: Error) => void;
    mockCreateShifu.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectCreation = reject;
        }),
    );
    render(<AdminPage />);
    await screen.findByText('Course 1');
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    fillManualCourseForm();
    fireEvent.click(screen.getByRole('button', { name: SUBMIT_COURSE_LABEL }));
    await waitFor(() => expect(mockCreateShifu).toHaveBeenCalledTimes(1));
    expect(
      screen.getByRole('button', {
        name: 'component.createShifuDialog.creating',
      }),
    ).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'creator_course_create_cancel',
      expect.anything(),
    );

    rejectCreation(new Error('request failed'));
    const retry = await screen.findByRole('button', {
      name: SUBMIT_COURSE_LABEL,
    });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    await waitFor(() => expect(mockCreateShifu).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'creator_course_create_attempt',
      ),
    ).toHaveLength(2);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'creator_course_create_result',
      ),
    ).toEqual([
      [
        'creator_course_create_result',
        {
          creation_path: 'manual',
          outcome: 'failed',
          failure_category: 'request_failed',
        },
      ],
      [
        'creator_course_create_result',
        {
          creation_path: 'manual',
          outcome: 'success',
          shifu_bid: 'course-created-1',
        },
      ],
    ]);
  });

  test('tracks the AI course-creation handoff as its own path', async () => {
    mockCourseCreatorUrl = 'https://creator.example.test/new';
    render(<AdminPage />);

    await screen.findByText('Course 1');
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'creator_ai_course_entry_impression',
      expect.anything(),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    const link = screen.getByRole('link', { name: CHOOSE_AI_COURSE_LABEL });
    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_ai_course_entry_impression',
        {
          surface: 'admin_course_list',
          presentation: 'creation_choice_modal',
        },
      ),
    );
    fireEvent.click(link);

    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_ai_course_entry_click',
      {
        surface: 'admin_course_list',
        presentation: 'creation_choice_modal',
      },
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'creator_course_create_attempt',
      { creation_path: 'ai_assistant' },
    );
    const serializedCalls = JSON.stringify(mockTrackEvent.mock.calls);
    expect(serializedCalls).not.toContain('creator.example.test');
  });

  test('tracks one AI entry impression per mounted visit across rerenders', async () => {
    mockCourseCreatorUrl = 'https://creator.example.test/new';
    const { rerender } = render(<AdminPage />);
    await screen.findByText('Course 1');
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    await screen.findByRole('link', { name: CHOOSE_AI_COURSE_LABEL });
    await waitFor(() =>
      expect(
        mockTrackEvent.mock.calls.filter(
          ([eventName]) => eventName === 'creator_ai_course_entry_impression',
        ),
      ).toHaveLength(1),
    );

    rerender(<AdminPage />);

    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'creator_ai_course_entry_impression',
      ),
    ).toHaveLength(1);
  });

  test('tracks prompt copy attempt and terminal success without exposing prompt text', async () => {
    render(<AdminPage />);
    await screen.findByText('Course 1');
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: COPY_AI_COURSE_PROMPT_LABEL }),
    );

    await waitFor(() => expect(copyText).toHaveBeenCalledTimes(1));
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_ai_skill_install_copy_attempt',
      {
        surface: 'admin_course_list',
        presentation: 'creation_choice_modal',
      },
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_ai_skill_install_copy_result',
      {
        surface: 'admin_course_list',
        presentation: 'creation_choice_modal',
        outcome: 'success',
      },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'component.courseCreationChoiceDialog.aiPrompt',
    );
  });

  test('waits for clipboard settlement and never treats installation copy as course creation', async () => {
    let finish!: () => void;
    (copyText as jest.Mock).mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          finish = resolve;
        }),
    );
    render(<AdminPage />);
    await screen.findByText('Course 1');
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: COPY_AI_COURSE_PROMPT_LABEL }),
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'creator_ai_skill_install_copy_attempt',
      ),
    ).toHaveLength(1);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'creator_ai_skill_install_copy_result',
      ),
    ).toHaveLength(0);
    finish();
    await waitFor(() =>
      expect(
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === 'creator_ai_skill_install_copy_result',
        ),
      ).toHaveLength(1),
    );
    for (const retired of [
      'creator_ai_course_prompt_copy_attempt',
      'creator_ai_course_prompt_copy_result',
      'creator_course_create_attempt',
      'creator_course_create_result',
    ]) {
      expect(mockTrackEvent.mock.calls.some(([name]) => name === retired)).toBe(
        false,
      );
    }
    for (const [, payload] of mockTrackEvent.mock.calls) {
      for (const field of [
        'prompt',
        'text',
        'aiExamples',
        'tools',
        'url',
        'error',
      ])
        expect(payload).not.toHaveProperty(field);
    }
  });

  test('tracking failures do not prevent installation instruction copying', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('tracking unavailable');
    });
    render(<AdminPage />);
    await screen.findByText('Course 1');
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: COPY_AI_COURSE_PROMPT_LABEL }),
    );
    await waitFor(() => expect(copyText).toHaveBeenCalled());
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  test('reports a bounded prompt copy failure and keeps the choice dialog open', async () => {
    (copyText as jest.Mock).mockRejectedValueOnce(
      new Error('sensitive clipboard failure'),
    );
    render(<AdminPage />);
    await screen.findByText('Course 1');
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: COPY_AI_COURSE_PROMPT_LABEL }),
    );

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_ai_skill_install_copy_result',
        {
          surface: 'admin_course_list',
          presentation: 'creation_choice_modal',
          outcome: 'failed',
        },
      ),
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'sensitive clipboard failure',
    );
  });

  test('tracks the in-product AI option even when the optional guide is unavailable', async () => {
    render(<AdminPage />);
    await screen.findByText('Course 1');
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );

    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_ai_course_entry_impression',
      {
        surface: 'admin_course_list',
        presentation: 'creation_choice_modal',
      },
    );
  });

  test('does not expose or track the AI entry before admin access resolves', async () => {
    mockCourseCreatorUrl = 'https://creator.example.test/new';
    mockEnsureAdminCreator.mockReturnValue(new Promise(() => {}));
    render(<AdminPage />);

    await waitFor(() => expect(mockEnsureAdminCreator).toHaveBeenCalled());
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    expect(
      screen.queryByRole('link', { name: CHOOSE_AI_COURSE_LABEL }),
    ).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'creator_ai_course_entry_impression',
      expect.anything(),
    );
  });

  test('does not expose or track the AI entry when admin access fails', async () => {
    const consoleErrorSpy = jest
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);
    mockCourseCreatorUrl = 'https://creator.example.test/new';
    mockEnsureAdminCreator.mockRejectedValue(new Error('permission denied'));
    render(<AdminPage />);

    await screen.findByText('permission denied');
    expect(
      screen.queryByRole('link', { name: CHOOSE_AI_COURSE_LABEL }),
    ).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'creator_ai_course_entry_impression',
      expect.anything(),
    );
    consoleErrorSpy.mockRestore();
  });

  test('keeps the AI entry usable when tracking is unavailable', async () => {
    mockCourseCreatorUrl = 'https://creator.example.test/new';
    mockTrackEvent.mockImplementation(() => {
      throw new Error('tracking unavailable');
    });
    render(<AdminPage />);

    await screen.findByText('Course 1');
    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    const link = screen.getByRole('link', { name: CHOOSE_AI_COURSE_LABEL });
    expect(link).toHaveAttribute('href', 'https://creator.example.test/new');
    expect(() => fireEvent.click(link)).not.toThrow();
  });

  test('keeps the manual create workflow usable when tracking throws', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('tracking unavailable');
    });
    render(<AdminPage />);
    await screen.findByText('Course 1');

    fireEvent.click(
      screen.getByRole('button', { name: 'common.core.createBlankShifu' }),
    );
    fillManualCourseForm();
    fireEvent.click(screen.getByRole('button', { name: SUBMIT_COURSE_LABEL }));

    await waitFor(() => expect(mockCreateShifu).toHaveBeenCalledTimes(1));
  });

  test('opens redemption dialog from the course card menu and keeps the course locked until close animation finishes', async () => {
    render(<AdminPage />);

    await waitFor(() => {
      expect(mockEnsureAdminCreator).toHaveBeenCalledWith({});
      expect(mockGetShifuList).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 30,
        archived: false,
      });
      expect(screen.getByText('Course 1')).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.more',
      }),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.redemptionCodes.action',
      }),
    );

    expect(screen.getByTestId('creator-redemption-dialog')).toHaveAttribute(
      'data-open',
      'true',
    );
    expect(screen.getByTestId('redemption-shifu-id')).toHaveTextContent(
      'course-1',
    );
    expect(screen.getByTestId('redemption-shifu-name')).toHaveTextContent(
      'Course 1',
    );

    fireEvent.click(
      screen.getByRole('button', { name: CLOSE_REDEMPTION_LABEL }),
    );

    expect(screen.getByTestId('creator-redemption-dialog')).toHaveAttribute(
      'data-open',
      'false',
    );
    expect(screen.getByTestId('redemption-shifu-id')).toHaveTextContent(
      'course-1',
    );

    await waitFor(
      () => {
        expect(screen.getByTestId('redemption-shifu-id')).toHaveTextContent(
          'none',
        );
      },
      { timeout: 500 },
    );
  });

  test('does not show owner-only course actions for shared-permission courses', async () => {
    mockGetShifuList.mockResolvedValue({
      items: [
        {
          bid: 'course-shared-1',
          name: 'Shared Course',
          description: 'Shared course description',
          state: 1,
          archived: false,
          avatar: '',
          is_favorite: false,
          created_user_bid: 'owner-1',
          can_manage_permissions: false,
        },
      ],
    });

    render(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByText('Shared Course')).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.more',
      }),
    );

    expect(
      screen.queryByRole('button', {
        name: 'module.order.importActivation.action',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.order.redemptionCodes.action',
      }),
    ).not.toBeInTheDocument();
  });

  test('does not show import activation or redemption code actions for unpublished owner courses', async () => {
    mockGetShifuList.mockResolvedValue({
      items: [
        {
          bid: 'course-draft-1',
          name: 'Draft Course',
          description: 'Draft course description',
          state: 0,
          archived: false,
          avatar: '',
          is_favorite: false,
          created_user_bid: 'user-1',
          can_manage_permissions: true,
        },
      ],
    });

    render(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByText('Draft Course')).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'common.core.more',
      }),
    );

    expect(
      screen.queryByRole('button', {
        name: 'module.order.importActivation.action',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.order.redemptionCodes.action',
      }),
    ).not.toBeInTheDocument();
  });
});

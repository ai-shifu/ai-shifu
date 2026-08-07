import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import ChatPage from './page';

const mockGetProfileOnboarding = jest.fn();
const mockCompleteProfileOnboarding = jest.fn();
const mockSkipProfileOnboarding = jest.fn();
const mockUpdateWxcode = jest.fn();
const mockRefreshUserInfo = jest.fn();
const mockUpdateCourseId = jest.fn();
const mockLoadTree = jest.fn();
const mockReloadTree = jest.fn();
const mockUpdateLesson = jest.fn();
const mockUpdateSelectedLesson = jest.fn();
const mockUpdateLessonId = jest.fn();
const mockUpdateChapterId = jest.fn();
const mockTrackEvent = jest.fn();
const mockToast = jest.fn();

interface MockChatMobileHeaderProps {
  lessonId?: string;
  lessonTitle?: string;
}

interface MockChatUiProps {
  lessonId?: string;
  lessonUpdate?: (value: {
    id: string;
    status: string;
    status_value: string;
  }) => void;
}

type ResetChapterEventHandler = (
  event: CustomEvent<{
    chapter_id: string;
    lesson_id: string;
  }>,
) => Promise<void>;

const getResetChapterEventHandler = () => {
  const { shifu: mockedShifu } = jest.requireMock('@/c-service/Shifu') as {
    shifu: {
      events: {
        addEventListener: jest.Mock;
      };
    };
  };
  return mockedShifu.events.addEventListener.mock.calls.find(
    ([eventType]) => eventType === 'RESET_CHAPTER',
  )?.[1] as ResetChapterEventHandler | undefined;
};

const mockChatMobileHeader = jest.fn(
  ({ lessonId, lessonTitle }: MockChatMobileHeaderProps) => (
    <div
      data-testid='mobile-header'
      data-lesson-id={lessonId}
      data-lesson-title={lessonTitle}
    />
  ),
);
const mockChatUi = jest.fn(({ lessonId }: MockChatUiProps) => (
  <div
    data-testid='chat-ui'
    data-lesson-id={lessonId}
  />
));
const completeOnboardingLabel = 'complete onboarding';
const skipOnboardingLabel = 'skip onboarding';
const profileV2Status = (overrides: Record<string, unknown> = {}) => ({
  contract_version: 'profile-v2',
  enabled: true,
  should_show: false,
  presentation: 'hidden',
  legacy_handled: false,
  has_learner_profile: false,
  learner_profile_updated_at: null,
  max_length: 1000,
  config_revision: 1,
  guided_available: true,
  ...overrides,
});
let mockSelectedLessonId = 'lesson-1';
let mockLessonTreeLessons = [
  {
    id: 'lesson-1',
    name: 'Lesson title',
    status: 'not_started',
  },
];

type MockUserInfo = {
  user_id: string;
  name: string;
  email: string;
  language: string;
};

type MockUserStoreState = {
  userInfo: MockUserInfo | null;
  isLoggedIn: boolean;
  isInitialized: boolean;
  refreshUserInfo: typeof mockRefreshUserInfo;
  getToken: () => string;
};

const defaultMockUserInfo: MockUserInfo = {
  user_id: 'user-1',
  name: 'Old name',
  email: 'user@example.com',
  language: 'zh-CN',
};

const mockUserStoreState: MockUserStoreState = {
  userInfo: {
    ...defaultMockUserInfo,
  },
  isLoggedIn: true,
  isInitialized: true,
  refreshUserInfo: mockRefreshUserInfo,
  getToken: () => 'token-1',
};

const mockCourseStoreState = {
  courseName: 'Course name',
  courseAvatar: '',
  lessonId: 'lesson-1',
  chapterId: 'chapter-1',
  payModalOpen: false,
  payModalState: {},
  openPayModal: jest.fn(),
  closePayModal: jest.fn(),
  setPayModalResult: jest.fn(),
  updateLessonId: mockUpdateLessonId,
  updateChapterId: mockUpdateChapterId,
};

const mockSystemStoreState = {
  wechatCode: '',
  previewMode: false,
  learningMode: 'read',
  showLearningModeToggle: false,
};

const mockUiLayoutStoreState = {
  frameLayout: 'desktop',
  updateFrameLayout: jest.fn(),
};

jest.mock('next/dynamic', () => ({
  __esModule: true,
  default: () =>
    function MockDynamicComponent() {
      return null;
    },
}));

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: ['course-1'] }),
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'zh-CN',
    },
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}));

jest.mock('zustand/react/shallow', () => ({
  useShallow: (selector: unknown) => selector,
}));

jest.mock('@/c-constants/uiConstants', () => ({
  FRAME_LAYOUT_MOBILE: 'mobile',
  LISTEN_MODE_VH_FALLBACK_CLASSNAME: 'listen-mode-vh-fallback',
  calcFrameLayout: () => 'desktop',
  inWechat: () => false,
  inMiniProgram: () => false,
}));

jest.mock('@/c-store', () => ({
  useEnvStore: Object.assign(
    (
      selector?: (state: {
        updateCourseId: typeof mockUpdateCourseId;
      }) => unknown,
    ) =>
      selector ? selector({ updateCourseId: mockUpdateCourseId }) : undefined,
    {
      getState: () => ({
        updateCourseId: mockUpdateCourseId,
      }),
    },
  ),
  useCourseStore: Object.assign(
    (selector: (state: typeof mockCourseStoreState) => unknown) =>
      selector(mockCourseStoreState),
    {
      getState: () => mockCourseStoreState,
    },
  ),
  useUiLayoutStore: Object.assign(
    (selector: (state: typeof mockUiLayoutStoreState) => unknown) =>
      selector(mockUiLayoutStoreState),
    {
      getState: () => mockUiLayoutStoreState,
    },
  ),
  useSystemStore: (selector: (state: typeof mockSystemStoreState) => unknown) =>
    selector(mockSystemStoreState),
}));

jest.mock('@/store', () => ({
  useUserStore: Object.assign(
    (selector: (state: typeof mockUserStoreState) => unknown) =>
      selector(mockUserStoreState),
    {
      getState: () => mockUserStoreState,
    },
  ),
}));

jest.mock('@/c-common/hooks/useDisclosure', () => ({
  useDisclosure: () => ({
    open: false,
    onClose: jest.fn(),
    onToggle: jest.fn(),
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
}));

jest.mock('@/c-api/user', () => ({
  completeProfileOnboarding: (...args: unknown[]) =>
    mockCompleteProfileOnboarding(...args),
  getProfileOnboarding: (...args: unknown[]) =>
    mockGetProfileOnboarding(...args),
  isProfileOnboardingV2Status: (value: unknown) =>
    typeof value === 'object' &&
    value !== null &&
    'contract_version' in value &&
    value.contract_version === 'profile-v2',
  skipProfileOnboarding: (...args: unknown[]) =>
    mockSkipProfileOnboarding(...args),
  updateWxcode: (...args: unknown[]) => mockUpdateWxcode(...args),
}));

jest.mock('@/c-service/Shifu', () => ({
  shifu: {
    EventTypes: {
      OPEN_LOGIN_MODAL: 'OPEN_LOGIN_MODAL',
      RESET_CHAPTER: 'RESET_CHAPTER',
    },
    events: {
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    },
  },
}));

jest.mock('./hooks/useLessonTree', () => ({
  useLessonTree: () => ({
    tree: {
      bannerInfo: null,
      catalogs: [
        {
          id: 'chapter-1',
          lessons: mockLessonTreeLessons,
        },
      ],
    },
    selectedLessonId: mockSelectedLessonId,
    loadTree: mockLoadTree,
    reloadTree: mockReloadTree,
    updateSelectedLesson: mockUpdateSelectedLesson,
    toggleCollapse: jest.fn(),
    getCurrElement: jest.fn().mockResolvedValue(null),
    updateLesson: mockUpdateLesson,
    updateChapterStatus: jest.fn(),
    getChapterByLesson: jest.fn(() => ({
      id: 'chapter-1',
    })),
    onTryLessonSelect: jest.fn(),
    getNextLessonId: jest.fn(),
  }),
}));

jest.mock('./courseVisitTracking', () => ({
  trackCourseVisitIfNeeded: jest.fn().mockResolvedValue(false),
}));

jest.mock('./Components/NavDrawer/NavDrawer', () => ({
  __esModule: true,
  default: () => <div data-testid='nav-drawer' />,
}));

jest.mock('./Components/ChatMobileHeader', () => ({
  __esModule: true,
  default: (props: MockChatMobileHeaderProps) => mockChatMobileHeader(props),
}));

jest.mock('./Components/ChatUi/ChatUi', () => ({
  __esModule: true,
  default: (props: MockChatUiProps) => mockChatUi(props),
}));

jest.mock('@/c-components/TrackingVisit', () => ({
  __esModule: true,
  default: () => <div data-testid='tracking-visit' />,
}));

jest.mock('./Components/FeedbackModal/FeedbackModal', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/components/debug/DebugConsoleOverlay', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/components/profile-onboarding/ProfileOnboardingModal', () => ({
  __esModule: true,
  default: ({
    open,
    onComplete,
    onSkip,
    errorMessage,
  }: {
    open: boolean;
    onComplete: (
      learnerProfile: string,
      source: 'guided' | 'pasted',
      sessionId?: string,
    ) => void;
    onSkip: (sessionId?: string) => void;
    errorMessage?: string;
  }) =>
    open ? (
      <div data-testid='profile-onboarding-modal'>
        <button
          type='button'
          onClick={() => onComplete('我是产品经理，喜欢简洁表达。', 'pasted')}
        >
          {completeOnboardingLabel}
        </button>
        <button
          type='button'
          onClick={() => onSkip()}
        >
          {skipOnboardingLabel}
        </button>
        {errorMessage ? <div role='alert'>{errorMessage}</div> : null}
      </div>
    ) : null,
}));

describe('ChatPage profile onboarding gate', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUserStoreState.userInfo = { ...defaultMockUserInfo };
    mockUserStoreState.isLoggedIn = true;
    mockUserStoreState.isInitialized = true;
    mockUserStoreState.getToken = () => 'token-1';
    mockCourseStoreState.lessonId = 'lesson-1';
    mockCourseStoreState.chapterId = 'chapter-1';
    mockSystemStoreState.previewMode = false;
    mockSystemStoreState.learningMode = 'read';
    mockUiLayoutStoreState.frameLayout = 'desktop';
    mockSelectedLessonId = 'lesson-1';
    mockToast.mockReset();
    mockLessonTreeLessons = [
      {
        id: 'lesson-1',
        name: 'Lesson title',
        status: 'not_started',
      },
    ];
    window.matchMedia = jest.fn().mockReturnValue({
      matches: false,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      addListener: jest.fn(),
      removeListener: jest.fn(),
    });
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: false,
        presentation: 'hidden',
      }),
    );
    mockCompleteProfileOnboarding.mockResolvedValue({
      completed: true,
    });
    mockSkipProfileOnboarding.mockResolvedValue({ skipped: true });
    mockReloadTree.mockResolvedValue(null);
    mockRefreshUserInfo.mockResolvedValue(undefined);
  });

  test('does not mount the chat runtime before onboarding status is resolved', async () => {
    let resolveStatus: (value: unknown) => void = () => {};
    mockGetProfileOnboarding.mockReturnValue(
      new Promise(resolve => {
        resolveStatus = resolve;
      }),
    );

    render(<ChatPage />);

    await waitFor(() => expect(mockGetProfileOnboarding).toHaveBeenCalled());
    expect(screen.queryByTestId('chat-ui')).not.toBeInTheDocument();

    resolveStatus(
      profileV2Status({
        should_show: false,
        presentation: 'hidden',
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
    });
  });

  test('resets onboarding and ignores stale status when the auth scope changes', async () => {
    let resolveFirstStatus: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding
      .mockImplementationOnce(
        () =>
          new Promise(resolve => {
            resolveFirstStatus = resolve;
          }),
      )
      .mockResolvedValueOnce(
        profileV2Status({
          should_show: false,
          presentation: 'hidden',
        }),
      );

    const { rerender } = render(<ChatPage />);
    await waitFor(() =>
      expect(mockGetProfileOnboarding).toHaveBeenCalledTimes(1),
    );

    mockUserStoreState.userInfo = null;
    mockUserStoreState.isLoggedIn = false;
    mockUserStoreState.getToken = () => 'guest-token';
    rerender(<ChatPage />);

    expect(await screen.findByTestId('chat-ui')).toBeInTheDocument();
    await act(async () => {
      resolveFirstStatus(
        profileV2Status({
          should_show: true,
          presentation: 'blocking',
        }),
      );
    });
    expect(
      screen.queryByTestId('profile-onboarding-modal'),
    ).not.toBeInTheDocument();

    mockUserStoreState.userInfo = {
      ...defaultMockUserInfo,
      user_id: 'user-2',
      email: 'second@example.com',
    };
    mockUserStoreState.isLoggedIn = true;
    mockUserStoreState.getToken = () => 'token-2';
    rerender(<ChatPage />);

    await waitFor(() =>
      expect(mockGetProfileOnboarding).toHaveBeenCalledTimes(2),
    );
    expect(await screen.findByTestId('chat-ui')).toBeInTheDocument();
    expect(
      screen.queryByTestId('profile-onboarding-modal'),
    ).not.toBeInTheDocument();
  });

  test('fails open without showing v2 onboarding when an old backend omits the contract version', async () => {
    mockGetProfileOnboarding.mockResolvedValue({
      enabled: true,
      should_show: true,
      markdownflow: '?[怎么称呼你？]',
    });

    render(<ChatPage />);

    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId('profile-onboarding-modal'),
    ).not.toBeInTheDocument();
    expect(mockCompleteProfileOnboarding).not.toHaveBeenCalled();
    expect(mockSkipProfileOnboarding).not.toHaveBeenCalled();
  });

  test('does not open onboarding when the server presentation is hidden', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'hidden',
      }),
    );

    render(<ChatPage />);

    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId('profile-onboarding-modal'),
    ).not.toBeInTheDocument();
  });

  test('keeps the chat runtime blocked until onboarding completion refreshes user info', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );

    render(<ChatPage />);

    await screen.findByTestId('profile-onboarding-modal');
    expect(screen.queryByTestId('chat-ui')).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: completeOnboardingLabel }),
    );

    await waitFor(() => {
      expect(mockCompleteProfileOnboarding).toHaveBeenCalledWith({
        learner_profile: '我是产品经理，喜欢简洁表达。',
        trigger_source: 'pasted',
      });
    });
    await waitFor(() => expect(mockRefreshUserInfo).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
    });
  });

  test('mounts the course immediately for a non-blocking legacy upgrade prompt', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'non_blocking',
        legacy_handled: true,
      }),
    );

    render(<ChatPage />);

    await screen.findByTestId('profile-onboarding-modal');
    expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
  });

  test('persists “maybe later” through the separate skip endpoint', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );

    render(<ChatPage />);
    await screen.findByTestId('profile-onboarding-modal');
    fireEvent.click(screen.getByRole('button', { name: skipOnboardingLabel }));

    await waitFor(() => {
      expect(mockSkipProfileOnboarding).toHaveBeenCalledWith(undefined);
    });
    expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
  });

  test('passes the resolved selected lesson id to chat headers when the store id is stale', async () => {
    mockUiLayoutStoreState.frameLayout = 'mobile';
    mockCourseStoreState.lessonId = 'lesson-old';
    mockSelectedLessonId = 'lesson-new';
    mockLessonTreeLessons = [
      {
        id: 'lesson-new',
        name: 'New lesson title',
        status: 'not_started',
      },
    ];

    render(<ChatPage />);

    const mobileHeader = await screen.findByTestId('mobile-header');
    expect(mobileHeader).toHaveAttribute('data-lesson-id', 'lesson-new');
    expect(mobileHeader).toHaveAttribute(
      'data-lesson-title',
      'New lesson title',
    );

    const chatUi = await screen.findByTestId('chat-ui');
    expect(chatUi).toHaveAttribute('data-lesson-id', 'lesson-new');
  });

  test('keeps a retaken lesson in progress after reloading its reset tree state', async () => {
    let resolveReloadTree: (value: unknown) => void = () => {};
    mockReloadTree.mockReturnValueOnce(
      new Promise(resolve => {
        resolveReloadTree = resolve;
      }),
    );

    render(<ChatPage />);

    await screen.findByTestId('chat-ui');

    const resetChapterEventHandler = getResetChapterEventHandler();

    expect(resetChapterEventHandler).toBeDefined();

    const resetPromise = resetChapterEventHandler?.(
      new CustomEvent('RESET_CHAPTER', {
        detail: {
          chapter_id: 'chapter-1',
          lesson_id: 'lesson-1',
        },
      }),
    );

    expect(mockReloadTree).toHaveBeenCalledWith('chapter-1', 'lesson-1');
    expect(mockUpdateLesson).not.toHaveBeenCalled();

    resolveReloadTree(null);
    await resetPromise;

    expect(mockUpdateLesson).toHaveBeenCalledWith('lesson-1', {
      id: 'lesson-1',
      status: 'in_progress',
      status_value: 'in_progress',
    });
    expect(mockUpdateSelectedLesson).toHaveBeenCalledWith('lesson-1', true);
  });

  test('preserves a newer lesson status received while the reset tree reloads', async () => {
    let resolveReloadTree: (value: unknown) => void = () => {};
    mockReloadTree.mockReturnValueOnce(
      new Promise(resolve => {
        resolveReloadTree = resolve;
      }),
    );

    render(<ChatPage />);

    await screen.findByTestId('chat-ui');

    const resetChapterEventHandler = getResetChapterEventHandler();
    const latestChatUiCall =
      mockChatUi.mock.calls[mockChatUi.mock.calls.length - 1];
    const lessonUpdate = latestChatUiCall?.[0].lessonUpdate;

    expect(resetChapterEventHandler).toBeDefined();
    expect(lessonUpdate).toBeDefined();

    const resetPromise = resetChapterEventHandler?.(
      new CustomEvent('RESET_CHAPTER', {
        detail: {
          chapter_id: 'chapter-1',
          lesson_id: 'lesson-1',
        },
      }),
    );

    lessonUpdate?.({
      id: 'lesson-1',
      status: 'completed',
      status_value: 'completed',
    });

    resolveReloadTree(null);
    await resetPromise;

    expect(mockUpdateLesson).toHaveBeenLastCalledWith('lesson-1', {
      id: 'lesson-1',
      status: 'completed',
      status_value: 'completed',
    });
    expect(mockUpdateLesson).not.toHaveBeenCalledWith('lesson-1', {
      id: 'lesson-1',
      status: 'in_progress',
      status_value: 'in_progress',
    });
  });

  test('surfaces the backend onboarding error message when submit fails', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );
    mockCompleteProfileOnboarding.mockRejectedValue(
      new Error('昵称包含风险词'),
    );

    render(<ChatPage />);

    await screen.findByTestId('profile-onboarding-modal');

    fireEvent.click(
      screen.getByRole('button', { name: completeOnboardingLabel }),
    );

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('昵称包含风险词');
    });
    expect(screen.queryByTestId('chat-ui')).not.toBeInTheDocument();
  });

  test('shows a toast and unblocks chat when onboarding status load fails', async () => {
    mockGetProfileOnboarding.mockRejectedValue(new Error('画像配置暂时不可用'));

    render(<ChatPage />);

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: '画像配置暂时不可用',
        variant: 'destructive',
      });
    });
    expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
    expect(
      screen.queryByTestId('profile-onboarding-modal'),
    ).not.toBeInTheDocument();
  });

  test('shows a sync-pending toast when onboarding save succeeds but refresh lags', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );
    mockRefreshUserInfo.mockRejectedValue(new Error('refresh delayed'));

    render(<ChatPage />);

    await screen.findByTestId('profile-onboarding-modal');

    fireEvent.click(
      screen.getByRole('button', { name: completeOnboardingLabel }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'module.profileOnboarding.refreshPending',
      });
    });
    expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
  });
});

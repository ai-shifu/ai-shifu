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
const openLearnerProfileLabel = 'open learner profile';
const saveLearnerProfileLabel = 'save learner profile';
const laterLabel = 'later';
const completeOnboardingLabel = 'complete onboarding';
const skipOnboardingLabel = 'skip onboarding';
const dismissOnboardingLabel = 'dismiss onboarding';

interface MockChatMobileHeaderProps {
  lessonId?: string;
  lessonTitle?: string;
}

interface MockChatUiProps {
  lessonId?: string;
  runtimeReady?: boolean;
  lessonUpdate?: (value: {
    id: string;
    status: string;
    status_value: string;
  }) => void;
}

interface MockNavDrawerProps {
  onPersonalInfoClick?: () => void;
}

interface MockLearnerProfileDialogProps {
  autoStartCollection?: boolean;
  draftStorageScope: string;
  exitPolicy: 'blocking' | 'dismissible';
  externalErrorMessage?: string;
  externalSubmitting?: boolean;
  initialOnboardingStatus?: { presentation?: string };
  onClose: (reason: 'dismiss' | 'saved') => void | Promise<void>;
  onDefer?: (sessionId?: string) => boolean | void | Promise<boolean | void>;
  onSaved?: () => void | Promise<void>;
  open: boolean;
  presentation?: 'blocking' | 'non_blocking' | 'hidden';
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
const mockChatUi = jest.fn(({ lessonId, runtimeReady }: MockChatUiProps) => (
  <div
    data-testid='chat-ui'
    data-lesson-id={lessonId}
    data-runtime-ready={String(runtimeReady)}
  />
));
const mockNavDrawer = jest.fn(({ onPersonalInfoClick }: MockNavDrawerProps) => (
  <button
    type='button'
    onClick={onPersonalInfoClick}
  >
    {openLearnerProfileLabel}
  </button>
));
const mockLearnerProfileDialog = jest.fn(
  ({
    autoStartCollection,
    draftStorageScope,
    exitPolicy,
    externalErrorMessage,
    externalSubmitting,
    initialOnboardingStatus,
    onClose,
    onDefer,
    onSaved,
    open,
    presentation,
  }: MockLearnerProfileDialogProps) => {
    const [error, setError] = React.useState('');
    const [draft, setDraft] = React.useState('');
    if (!open) {
      return null;
    }
    return (
      <div
        data-testid='learner-profile-dialog'
        data-auto-start-collection={String(Boolean(autoStartCollection))}
        data-exit-policy={exitPolicy}
        data-presentation={presentation}
        data-scope={draftStorageScope}
        data-status-presentation={initialOnboardingStatus?.presentation}
        data-submitting={String(Boolean(externalSubmitting))}
      >
        <input
          aria-label='mock learner draft'
          value={draft}
          onChange={event => setDraft(event.target.value)}
        />
        <button
          type='button'
          onClick={() => {
            void (async () => {
              await onSaved?.();
              await onClose('saved');
            })();
          }}
        >
          {initialOnboardingStatus
            ? completeOnboardingLabel
            : saveLearnerProfileLabel}
        </button>
        {exitPolicy === 'blocking' ? (
          <>
            <button
              type='button'
              onClick={() => {
                void (async () => {
                  const deferred = await onDefer?.('session-1');
                  if (deferred !== false) {
                    await onClose('dismiss');
                  }
                })();
              }}
            >
              {skipOnboardingLabel}
            </button>
            <button
              type='button'
              onClick={() => {
                void onClose('dismiss');
              }}
            >
              {dismissOnboardingLabel}
            </button>
          </>
        ) : (
          <button
            type='button'
            onClick={() => {
              setError('');
              void Promise.resolve(onClose('dismiss')).catch(caughtError => {
                setError(
                  caughtError instanceof Error
                    ? caughtError.message
                    : 'dismiss failed',
                );
              });
            }}
          >
            {laterLabel}
          </button>
        )}
        {error || externalErrorMessage ? (
          <div role='alert'>{error || externalErrorMessage}</div>
        ) : null}
      </div>
    );
  },
);
const profileV2Status = (overrides: Record<string, unknown> = {}) => ({
  contract_version: 'profile-v2',
  enabled: true,
  should_show: false,
  presentation: 'hidden',
  guided_available: true,
  handled: false,
  legacy_handled: false,
  has_learner_profile: false,
  learner_profile: '',
  learner_profile_updated_at: null,
  max_length: 1000,
  config_revision: 1,
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
  userInfo: { ...defaultMockUserInfo },
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
    open: true,
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
  getProfileOnboarding: (...args: unknown[]) =>
    mockGetProfileOnboarding(...args),
  isProfileOnboardingV2Status: (value: unknown) =>
    typeof value === 'object' &&
    value !== null &&
    'contract_version' in value &&
    value.contract_version === 'profile-v2' &&
    'guided_available' in value,
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
  default: (props: MockNavDrawerProps) => mockNavDrawer(props),
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

jest.mock('@/components/profile-onboarding/LearnerProfileDialog', () => ({
  __esModule: true,
  default: (props: MockLearnerProfileDialogProps) =>
    mockLearnerProfileDialog(props),
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
    mockUserStoreState.userInfo = {
      user_id: 'user-1',
      name: 'Old name',
      email: 'user@example.com',
      language: 'zh-CN',
    };
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
    mockGetProfileOnboarding.mockResolvedValue(profileV2Status());
    mockSkipProfileOnboarding.mockResolvedValue({ skipped: true });
    mockReloadTree.mockResolvedValue(null);
    mockRefreshUserInfo.mockResolvedValue(undefined);
  });

  test('keeps the lesson shell visible without starting runtime while eligibility loads', async () => {
    let resolveStatus: (value: unknown) => void = () => {};
    mockGetProfileOnboarding.mockReturnValue(
      new Promise(resolve => {
        resolveStatus = resolve;
      }),
    );

    render(<ChatPage />);

    await waitFor(() => expect(mockGetProfileOnboarding).toHaveBeenCalled());
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );

    resolveStatus(profileV2Status());

    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });
  });

  test('keeps the chat runtime blocked until onboarding completion refreshes user info', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );

    render(<ChatPage />);

    const dialog = await screen.findByTestId('learner-profile-dialog');
    expect(dialog).toHaveAttribute('data-auto-start-collection', 'true');
    expect(dialog).toHaveAttribute('data-exit-policy', 'blocking');
    expect(dialog).toHaveAttribute('data-presentation', 'blocking');
    expect(dialog).toHaveAttribute('data-status-presentation', 'blocking');
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );

    fireEvent.click(
      screen.getByRole('button', { name: completeOnboardingLabel }),
    );

    await waitFor(() => expect(mockRefreshUserInfo).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });
    expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();

    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-auto-start-collection',
      'false',
    );
    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'dismissible',
    );
    fireEvent.click(screen.getByRole('button', { name: laterLabel }));
    await waitFor(() => {
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    });
  });

  test('ignores a direct dismiss while blocking onboarding is still eligible', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );

    render(<ChatPage />);

    await screen.findByTestId('learner-profile-dialog');
    fireEvent.click(
      screen.getByRole('button', { name: dismissOnboardingLabel }),
    );

    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'blocking',
    );
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );
    expect(mockSkipProfileOnboarding).not.toHaveBeenCalled();
  });

  test('lets a non-blocking prompt close locally and reuses its status from the menu', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'non_blocking',
        legacy_handled: true,
      }),
    );

    render(<ChatPage />);

    const dialog = await screen.findByTestId('learner-profile-dialog');
    expect(dialog).toHaveAttribute('data-auto-start-collection', 'true');
    expect(dialog).toHaveAttribute('data-exit-policy', 'dismissible');
    expect(dialog).toHaveAttribute('data-presentation', 'non_blocking');
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );

    fireEvent.click(screen.getByRole('button', { name: laterLabel }));

    await waitFor(() => {
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    });
    expect(mockSkipProfileOnboarding).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-auto-start-collection',
      'false',
    );
    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'dismissible',
    );
    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-status-presentation',
      'non_blocking',
    );
  });

  test('releases blocking runtime only after defer succeeds and the dialog closes itself', async () => {
    let resolveSkip: (value: { skipped: boolean }) => void = () => {};
    mockSkipProfileOnboarding.mockReturnValue(
      new Promise(resolve => {
        resolveSkip = resolve;
      }),
    );
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );

    render(<ChatPage />);
    await screen.findByTestId('learner-profile-dialog');
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );

    fireEvent.click(screen.getByRole('button', { name: skipOnboardingLabel }));

    expect(mockSkipProfileOnboarding).toHaveBeenCalledWith('session-1');
    expect(screen.getByTestId('learner-profile-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );

    await act(async () => {
      resolveSkip({ skipped: true });
    });

    await waitFor(() => {
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    });
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );
  });

  test.each([
    ['old backend', { enabled: true, should_show: true, markdownflow: '?[Q]' }],
    ['hidden presentation', profileV2Status({ should_show: true })],
    [
      'disabled guided config',
      profileV2Status({
        enabled: false,
        should_show: true,
        presentation: 'blocking',
      }),
    ],
    [
      'guided unavailable',
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
        guided_available: false,
      }),
    ],
  ])('fails open without a modal for %s', async (_caseName, status) => {
    mockGetProfileOnboarding.mockResolvedValue(status);

    render(<ChatPage />);

    expect(await screen.findByTestId('chat-ui')).toBeInTheDocument();
    expect(
      screen.queryByTestId('learner-profile-dialog'),
    ).not.toBeInTheDocument();
  });

  test('resets the gate and ignores a stale status after the account changes', async () => {
    let resolveFirstStatus: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding
      .mockImplementationOnce(
        () =>
          new Promise(resolve => {
            resolveFirstStatus = resolve;
          }),
      )
      .mockResolvedValueOnce(profileV2Status());

    const { rerender } = render(<ChatPage />);
    await waitFor(() =>
      expect(mockGetProfileOnboarding).toHaveBeenCalledTimes(1),
    );

    mockUserStoreState.userInfo = {
      ...defaultMockUserInfo,
      user_id: 'user-2',
      email: 'second@example.com',
    };
    mockUserStoreState.getToken = () => 'token-2';
    rerender(<ChatPage />);

    await waitFor(() =>
      expect(mockGetProfileOnboarding).toHaveBeenCalledTimes(2),
    );
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
      screen.queryByTestId('learner-profile-dialog'),
    ).not.toBeInTheDocument();
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

  test('keeps blocking and surfaces the backend error when defer fails', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );
    mockSkipProfileOnboarding.mockRejectedValue(new Error('暂时无法延后'));

    render(<ChatPage />);

    await screen.findByTestId('learner-profile-dialog');
    fireEvent.click(screen.getByRole('button', { name: skipOnboardingLabel }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('暂时无法延后');
    });
    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'blocking',
    );
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );
  });

  test('starts runtime and reports delayed user refresh after guided submission', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );
    mockRefreshUserInfo.mockRejectedValue(new Error('refresh delayed'));

    render(<ChatPage />);

    await screen.findByTestId('learner-profile-dialog');
    fireEvent.click(
      screen.getByRole('button', { name: completeOnboardingLabel }),
    );

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'module.profileOnboarding.refreshPending',
      });
    });
    expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );
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
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );
    expect(
      screen.queryByTestId('learner-profile-dialog'),
    ).not.toBeInTheDocument();
  });

  test('opens settings as a dialog without replacing the lesson runtime', async () => {
    render(<ChatPage />);

    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );

    const dialog = screen.getByTestId('learner-profile-dialog');
    expect(dialog).toHaveAttribute('data-exit-policy', 'dismissible');
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );
    fireEvent.click(screen.getByRole('button', { name: laterLabel }));
    await waitFor(() => {
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    });
  });

  test('keeps the active onboarding dialog mounted when the menu entry is used', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );

    render(<ChatPage />);

    expect(await screen.findByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'blocking',
    );
    fireEvent.change(screen.getByLabelText('mock learner draft'), {
      target: { value: 'answer already in progress' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'blocking',
    );
    expect(screen.getByLabelText('mock learner draft')).toHaveValue(
      'answer already in progress',
    );

    fireEvent.click(
      screen.getByRole('button', { name: completeOnboardingLabel }),
    );

    await waitFor(() => {
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });
    expect(mockRefreshUserInfo).toHaveBeenCalledTimes(1);
  });

  test('keeps runtime paused after settings dismiss until pending eligibility completes', async () => {
    let resolveStatus: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding.mockReturnValue(
      new Promise(resolve => {
        resolveStatus = resolve;
      }),
    );

    render(<ChatPage />);

    await waitFor(() => expect(mockGetProfileOnboarding).toHaveBeenCalled());
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'dismissible',
    );
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );

    fireEvent.click(screen.getByRole('button', { name: laterLabel }));
    await waitFor(() => {
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    });
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );

    await act(async () => {
      resolveStatus(profileV2Status());
    });

    expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );
  });

  test('releases runtime when negative eligibility arrives with settings still open', async () => {
    let resolveStatus: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding.mockReturnValue(
      new Promise(resolve => {
        resolveStatus = resolve;
      }),
    );

    render(<ChatPage />);

    await waitFor(() => expect(mockGetProfileOnboarding).toHaveBeenCalled());
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    await act(async () => {
      resolveStatus(profileV2Status());
    });

    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'dismissible',
    );
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );
  });

  test('opens guided onboarding when positive eligibility arrives after settings dismiss', async () => {
    let resolveStatus: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding.mockReturnValue(
      new Promise(resolve => {
        resolveStatus = resolve;
      }),
    );

    render(<ChatPage />);

    await waitFor(() => expect(mockGetProfileOnboarding).toHaveBeenCalled());
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    fireEvent.click(screen.getByRole('button', { name: laterLabel }));
    await waitFor(() => {
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    });

    await act(async () => {
      resolveStatus(
        profileV2Status({
          should_show: true,
          presentation: 'blocking',
        }),
      );
    });

    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'blocking',
    );
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );
  });

  test('upgrades an open menu dialog in place when blocking eligibility arrives', async () => {
    let resolveStatus: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding.mockReturnValue(
      new Promise(resolve => {
        resolveStatus = resolve;
      }),
    );

    render(<ChatPage />);

    await waitFor(() => expect(mockGetProfileOnboarding).toHaveBeenCalled());
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    fireEvent.change(screen.getByLabelText('mock learner draft'), {
      target: { value: 'keep this settings draft' },
    });

    await act(async () => {
      resolveStatus(
        profileV2Status({
          should_show: true,
          presentation: 'blocking',
        }),
      );
    });

    expect(screen.getByTestId('learner-profile-dialog')).toHaveAttribute(
      'data-exit-policy',
      'blocking',
    );
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );
    expect(screen.getByLabelText('mock learner draft')).toHaveValue(
      'keep this settings draft',
    );
    expect(
      screen.queryByRole('button', { name: laterLabel }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: skipOnboardingLabel }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );
  });

  test('canonical save resolves the gate and ignores late eligibility', async () => {
    let resolveStatus: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding.mockReturnValue(
      new Promise(resolve => {
        resolveStatus = resolve;
      }),
    );

    render(<ChatPage />);

    await waitFor(() => expect(mockGetProfileOnboarding).toHaveBeenCalled());
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );
    fireEvent.click(
      screen.getByRole('button', { name: saveLearnerProfileLabel }),
    );

    await waitFor(() => {
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });

    await act(async () => {
      resolveStatus(
        profileV2Status({
          should_show: true,
          presentation: 'blocking',
        }),
      );
    });

    expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );
  });

  test('closes stale profile UI and reloads eligibility after account switch', async () => {
    mockGetProfileOnboarding.mockResolvedValue(
      profileV2Status({
        should_show: true,
        presentation: 'blocking',
      }),
    );

    const { rerender } = render(<ChatPage />);

    expect(
      await screen.findByTestId('learner-profile-dialog'),
    ).toBeInTheDocument();
    mockGetProfileOnboarding.mockResolvedValue(profileV2Status());
    mockUserStoreState.userInfo = {
      ...defaultMockUserInfo,
      user_id: 'user-2',
    };

    rerender(<ChatPage />);

    await waitFor(() => {
      expect(mockGetProfileOnboarding).toHaveBeenCalledTimes(2);
      expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });
  });

  test('pauses runtime immediately when a ready account switches to a pending account', async () => {
    const { rerender } = render(<ChatPage />);

    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });

    let resolveUserB: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding.mockReturnValueOnce(
      new Promise(resolve => {
        resolveUserB = resolve;
      }),
    );
    mockUserStoreState.userInfo = {
      ...defaultMockUserInfo,
      user_id: 'user-2',
    };

    rerender(<ChatPage />);

    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'false',
    );
    await act(async () => {
      resolveUserB(profileV2Status());
    });

    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });
  });

  test('ignores a late eligibility result from the previous account', async () => {
    let resolveUserA: (value: unknown) => void = () => undefined;
    mockGetProfileOnboarding.mockReturnValueOnce(
      new Promise(resolve => {
        resolveUserA = resolve;
      }),
    );
    const { rerender } = render(<ChatPage />);
    await waitFor(() => expect(mockGetProfileOnboarding).toHaveBeenCalled());

    mockGetProfileOnboarding.mockResolvedValueOnce(profileV2Status());
    mockUserStoreState.userInfo = {
      ...defaultMockUserInfo,
      user_id: 'user-2',
    };
    rerender(<ChatPage />);

    await waitFor(() => {
      expect(mockGetProfileOnboarding).toHaveBeenCalledTimes(2);
      expect(screen.getByTestId('chat-ui')).toHaveAttribute(
        'data-runtime-ready',
        'true',
      );
    });
    await act(async () => {
      resolveUserA(
        profileV2Status({
          should_show: true,
          presentation: 'blocking',
        }),
      );
    });

    expect(screen.queryByTestId('learner-profile-dialog')).toBeNull();
    expect(screen.getByTestId('chat-ui')).toHaveAttribute(
      'data-runtime-ready',
      'true',
    );
  });
});

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ChatPage from './page';

const mockGetProfileOnboarding = jest.fn();
const mockCompleteProfileOnboarding = jest.fn();
const mockUpdateWxcode = jest.fn();
const mockRefreshUserInfo = jest.fn();
const mockUpdateCourseId = jest.fn();
const mockLoadTree = jest.fn();
const mockReloadTree = jest.fn();
const mockUpdateLessonId = jest.fn();
const mockUpdateChapterId = jest.fn();
const mockTrackEvent = jest.fn();
const completeOnboardingLabel = 'complete onboarding';
const skipOnboardingLabel = 'skip onboarding';

const mockUserStoreState = {
  userInfo: {
    user_id: 'user-1',
    name: 'Old name',
    email: 'user@example.com',
    language: 'zh-CN',
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
          lessons: [
            {
              id: 'lesson-1',
              name: 'Lesson title',
              status: 'not_started',
            },
          ],
        },
      ],
    },
    selectedLessonId: 'lesson-1',
    loadTree: mockLoadTree,
    reloadTree: mockReloadTree,
    updateSelectedLesson: jest.fn(),
    toggleCollapse: jest.fn(),
    getCurrElement: jest.fn().mockResolvedValue(null),
    updateLesson: jest.fn(),
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
  default: () => null,
}));

jest.mock('./Components/ChatUi/ChatUi', () => ({
  __esModule: true,
  default: () => <div data-testid='chat-ui' />,
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
  }: {
    open: boolean;
    onComplete: (variables: Record<string, string>) => void;
    onSkip: () => void;
  }) =>
    open ? (
      <div data-testid='profile-onboarding-modal'>
        <button
          type='button'
          onClick={() => onComplete({ sys_user_nickname: '小明' })}
        >
          {completeOnboardingLabel}
        </button>
        <button
          type='button'
          onClick={onSkip}
        >
          {skipOnboardingLabel}
        </button>
      </div>
    ) : null,
}));

describe('ChatPage profile onboarding gate', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.matchMedia = jest.fn().mockReturnValue({
      matches: false,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      addListener: jest.fn(),
      removeListener: jest.fn(),
    });
    mockCompleteProfileOnboarding.mockResolvedValue({
      completed: true,
    });
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

    resolveStatus({
      should_show: false,
      markdownflow: '',
      current_values: {},
    });

    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
    });
  });

  test('keeps the chat runtime blocked until onboarding completion refreshes user info', async () => {
    mockGetProfileOnboarding.mockResolvedValue({
      should_show: true,
      markdownflow: '?[%{{sys_user_nickname}}...怎么称呼你？]',
      current_values: {},
    });

    render(<ChatPage />);

    await screen.findByTestId('profile-onboarding-modal');
    expect(screen.queryByTestId('chat-ui')).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: completeOnboardingLabel }),
    );

    await waitFor(() => {
      expect(mockCompleteProfileOnboarding).toHaveBeenCalledWith({
        skipped: false,
        variables: {
          sys_user_nickname: '小明',
        },
      });
    });
    await waitFor(() => expect(mockRefreshUserInfo).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByTestId('chat-ui')).toBeInTheDocument();
    });
  });
});

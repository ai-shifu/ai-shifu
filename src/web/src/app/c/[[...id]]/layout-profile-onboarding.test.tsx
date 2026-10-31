import React from 'react';

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useCourseStore, useEnvStore } from '@/store';
import { useSystemStore } from '@/store/use-system-store';
import { useUserStore } from '@/store/use-user-store';
import ChatLayout from './layout';
import ChatPage from './page';

let mockQuery = '';
let mockInWechat = true;
let mockInMiniProgram = false;
const mockWechatLogin = jest.fn();
const mockUpdateWxcode = jest.fn();
const mockRefreshUserInfo = jest.fn();
const mockGetProfileOnboarding = jest.fn();
const mockGetLearnerProfile = jest.fn();
const mockCreateProfileOnboardingSession = jest.fn();
const mockRunProfileOnboardingSession = jest.fn();
const mockTrackEvent = jest.fn();
const mockI18n = {
  language: 'en-US',
  resolvedLanguage: 'en-US',
  changeLanguage: jest.fn(),
};
const mockTranslate = (key: string) => key;
const openLearnerProfileLabel = 'open learner profile';

jest.mock('sse.js', () => ({ SSE: jest.fn() }));
jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
jest.mock('next/dynamic', () => ({
  __esModule: true,
  default: () => () => null,
}));
jest.mock('next/navigation', () => ({
  useParams: () => ({ id: ['course-1'] }),
  useSearchParams: () => new URLSearchParams(mockQuery),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: mockTranslate, i18n: mockI18n }),
}));
jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    changeLanguage: jest.fn(),
    t: (key: string) => key,
    language: 'en-US',
    resolvedLanguage: 'en-US',
  },
  browserLanguage: 'en-US',
  normalizeLanguage: () => 'en-US',
}));
jest.mock('@/constants/ui-constants', () => ({
  FRAME_LAYOUT_MOBILE: 'mobile',
  LISTEN_MODE_VH_FALLBACK_CLASSNAME: 'listen-mode-vh-fallback',
  calcFrameLayout: () => 'desktop',
  inWechat: () => mockInWechat,
  inMiniProgram: () => mockInMiniProgram,
  wechatLogin: (...args: unknown[]) => mockWechatLogin(...args),
}));
jest.mock('@/store/use-user-store', () => {
  const { create } = jest.requireActual('zustand');
  return {
    useUserStore: create(() => ({
      userInfo: null,
      isInitialized: true,
      isLoggedIn: true,
      initUser: jest.fn(),
      getToken: () => 'token-1',
      refreshUserInfo: (...args: unknown[]) => mockRefreshUserInfo(...args),
    })),
  };
});
jest.mock('@/store', () => ({
  ...jest.requireActual('@/store/env-store'),
  ...jest.requireActual('@/store/use-course-store'),
  ...jest.requireActual('@/store/use-system-store'),
  ...jest.requireActual('@/store/use-ui-layout-store'),
  ...jest.requireMock('@/store/use-user-store'),
}));
jest.mock('@/api/course', () => ({
  getCourseInfo: jest.fn().mockResolvedValue({
    course_id: 'course-1',
    course_name: 'Course',
    course_desc: 'Description',
    course_keywords: [],
    course_avatar: '',
    course_price: 0,
    course_tts_enabled: false,
    default_listen_mode_enabled: false,
    course_is_owner: false,
  }),
}));
jest.mock('@/api/user', () => ({
  ...jest.requireActual('@/api/user'),
  updateWxcode: (...args: unknown[]) => mockUpdateWxcode(...args),
}));
jest.mock('@/api/learner-profile', () => ({
  ...jest.requireActual('@/api/learner-profile'),
  getProfileOnboarding: (...args: unknown[]) =>
    mockGetProfileOnboarding(...args),
  getLearnerProfile: (...args: unknown[]) => mockGetLearnerProfile(...args),
  createProfileOnboardingSession: (...args: unknown[]) =>
    mockCreateProfileOnboardingSession(...args),
  runProfileOnboardingSession: (...args: unknown[]) =>
    mockRunProfileOnboardingSession(...args),
}));
jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
  toast: jest.fn(),
}));
jest.mock('@/lib/shifu/shifu-runtime', () => ({
  shifu: {
    EventTypes: {
      OPEN_LOGIN_MODAL: 'OPEN_LOGIN_MODAL',
      RESET_CHAPTER: 'RESET_CHAPTER',
    },
    events: { addEventListener: jest.fn(), removeEventListener: jest.fn() },
  },
}));
jest.mock('./hooks/use-lesson-tree', () => ({
  useLessonTree: () => ({
    tree: {
      bannerInfo: null,
      catalogs: [
        {
          id: 'chapter-1',
          lessons: [{ id: 'lesson-1', name: 'Lesson', status: 'not_started' }],
        },
      ],
    },
    selectedLessonId: 'lesson-1',
    loadTree: jest.fn(),
    reloadTree: jest.fn().mockResolvedValue(null),
    updateSelectedLesson: jest.fn(),
    toggleCollapse: jest.fn(),
    getCurrElement: jest.fn().mockResolvedValue(null),
    updateLesson: jest.fn(),
    updateChapterStatus: jest.fn(),
    getChapterByLesson: jest.fn(() => ({ id: 'chapter-1' })),
    onTryLessonSelect: jest.fn(),
    getNextLessonId: jest.fn(),
  }),
}));
jest.mock('./components/navigation/NavDrawer', () => ({
  __esModule: true,
  default: ({ onPersonalInfoClick }: { onPersonalInfoClick?: () => void }) => (
    <button
      type='button'
      onClick={onPersonalInfoClick}
    >
      {openLearnerProfileLabel}
    </button>
  ),
}));
jest.mock('./components/chat/ChatUi', () => ({
  __esModule: true,
  default: ({ runtimeReady }: { runtimeReady: boolean }) => (
    <div
      data-testid='chat-runtime'
      data-ready={String(runtimeReady)}
    />
  ),
}));
jest.mock('./components/ChatMobileHeader', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('./components/feedback/FeedbackModal', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('@/components/debug/DebugConsoleOverlay', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('markdown-flow-ui/renderer', () => ({
  ContentRender: ({ content }: { content: string }) => <div>{content}</div>,
}));
jest.mock('markdown-flow-ui/scroll', () => ({
  ScrollToBottomControl: () => null,
}));

const onboardingStatus = {
  enabled: true,
  should_show: true,
  presentation: 'blocking',
  guided_available: true,
  handled: false,
  has_learner_profile: false,
  learner_profile: '',
  learner_profile_updated_at: null,
  max_length: 1000,
  config_revision: 1,
};

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
  });
};

const showPage = async (persisted: boolean) => {
  await act(async () => {
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted }));
  });
  await flush();
};

const courseRoute = (pageKey = 'page') => (
  <ChatLayout>
    <ChatPage key={pageKey} />
  </ChatLayout>
);

const expectNoProfileStart = () => {
  expect({
    dialogs: screen.queryAllByRole('dialog').length,
    conversations: screen.queryAllByTestId('profile-onboarding-conversation')
      .length,
    shown: mockTrackEvent.mock.calls.filter(
      ([event]) => event === 'profile_onboarding_shown',
    ).length,
    sessions: mockCreateProfileOnboardingSession.mock.calls.length,
    streams: mockRunProfileOnboardingSession.mock.calls.length,
  }).toEqual({
    dialogs: 0,
    conversations: 0,
    shown: 0,
    sessions: 0,
    streams: 0,
  });
};

const setQuery = (query: string) => {
  mockQuery = query;
  window.location.search = query ? `?${query}` : '';
  window.location.href = `http://localhost:3000/c/course-1${window.location.search}`;
};

const deferred = <Value,>() => {
  let resolve!: (value: Value) => void;
  const promise = new Promise<Value>(resolvePromise => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
};

const expectProfileStarted = () => {
  expect(
    screen.getByTestId('profile-onboarding-conversation'),
  ).toBeInTheDocument();
  expect(mockCreateProfileOnboardingSession).toHaveBeenCalledTimes(1);
  expect(mockRunProfileOnboardingSession).toHaveBeenCalledTimes(1);
  expect(
    mockTrackEvent.mock.calls.filter(
      ([event]) => event === 'profile_onboarding_shown',
    ),
  ).toHaveLength(1);
};

describe('course layout and page WeChat authorization integration', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    mockQuery = '';
    mockInWechat = true;
    mockInMiniProgram = false;
    window.location.pathname = '/c/course-1';
    window.location.search = '';
    window.location.href = 'http://localhost:3000/c/course-1';
    window.matchMedia = jest.fn().mockReturnValue({
      matches: false,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      addListener: jest.fn(),
      removeListener: jest.fn(),
    });
    useEnvStore.setState({
      runtimeConfigLoaded: true,
      courseId: 'course-1',
      enableWxcode: 'true',
      appId: 'wx-app-id',
    });
    useSystemStore.setState({
      channel: '',
      wechatCode: '',
      previewMode: false,
      skip: false,
      learningMode: 'read',
      canUseClassroomMode: null,
    });
    useCourseStore.setState({
      courseName: 'Course',
      lessonId: 'lesson-1',
      chapterId: 'chapter-1',
      courseSettingsCourseId: 'course-1',
      courseTtsEnabled: false,
    });
    useUserStore.setState({
      isInitialized: true,
      isLoggedIn: true,
      userInfo: {
        user_id: 'user-1',
        name: 'Learner',
        email: '',
        language: 'en-US',
        openid: 'bound-openid',
      },
    });
    mockGetProfileOnboarding.mockResolvedValue(onboardingStatus);
    mockGetLearnerProfile.mockResolvedValue(onboardingStatus);
    mockCreateProfileOnboardingSession.mockResolvedValue({
      session_id: 'session-1',
      turn_index: 0,
      done: false,
      expires_in: 600,
    });
    mockRunProfileOnboardingSession.mockReturnValue({ close: jest.fn() });
    mockRefreshUserInfo.mockResolvedValue(undefined);
    mockUpdateWxcode.mockResolvedValue('bound-openid');
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('blocks automatic and menu Profile startup while layout OAuth navigation is pending for an already bound account', async () => {
    render(courseRoute());
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expectNoProfileStart();
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    await flush();
    expectNoProfileStart();
    await act(async () => {
      jest.advanceTimersByTime(30_000);
    });
    expectNoProfileStart();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  test('ignores a retained store code while the URL has no code and layout is navigating', async () => {
    useSystemStore.setState({ wechatCode: 'retained-code' });
    render(courseRoute());
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectNoProfileStart();
    await act(async () => {
      jest.advanceTimersByTime(30_000);
    });
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectNoProfileStart();
  });

  test('exchanges only the returned URL code in a new document and waits for account refresh before starting Profile', async () => {
    useSystemStore.setState({ wechatCode: 'retained-code' });
    const navigatingDocument = render(courseRoute());
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectNoProfileStart();
    navigatingDocument.unmount();

    const exchange = deferred<string>();
    const refresh = deferred<void>();
    mockUpdateWxcode.mockReturnValue(exchange.promise);
    mockRefreshUserInfo.mockReturnValue(refresh.promise);
    setQuery('code=returned-code&state=oauth-return');
    render(courseRoute());
    await flush();
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).toHaveBeenCalledWith({ wxcode: 'returned-code' });
    expectNoProfileStart();

    await act(async () => {
      exchange.resolve('refreshed-openid');
    });
    expect(mockRefreshUserInfo).toHaveBeenCalledTimes(1);
    expectNoProfileStart();
    await act(async () => {
      useUserStore.setState({
        userInfo: {
          ...useUserStore.getState().userInfo!,
          openid: 'refreshed-openid',
        },
      });
      refresh.resolve();
    });
    await flush();
    expectProfileStarted();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
  });

  test('does not duplicate layout navigation under StrictMode effect replay', async () => {
    render(<React.StrictMode>{courseRoute()}</React.StrictMode>);
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectNoProfileStart();
    await act(async () => {
      jest.advanceTimersByTime(30_000);
    });
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expectNoProfileStart();
  });

  test('keeps an issued layout navigation locked across child remount and query changes in the same document', async () => {
    const view = render(courseRoute());
    await flush();
    setQuery('code=not-a-new-document');
    view.rerender(courseRoute('remounted-page'));
    await flush();
    await act(async () => {
      jest.advanceTimersByTime(30_000);
    });
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectNoProfileStart();
  });

  test('shares a recovery-hook navigation with the parent lock through child remount and timeout', async () => {
    setQuery('code=unusable-code');
    useSystemStore.setState({ wechatCode: 'unusable-code' });
    useUserStore.setState({
      userInfo: { ...useUserStore.getState().userInfo!, openid: '' },
    });
    mockUpdateWxcode.mockRejectedValue(new Error('exchange failed'));
    const view = render(courseRoute());
    await flush();
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expectNoProfileStart();

    view.rerender(courseRoute('remounted-page'));
    await flush();
    await act(async () => {
      jest.advanceTimersByTime(30_000);
    });
    fireEvent.click(
      screen.getByRole('button', { name: openLearnerProfileLabel }),
    );
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
    expectNoProfileStart();
  });

  test('restores Profile after BFCache return without retrying stale preparation for an unbound account', async () => {
    useSystemStore.setState({ wechatCode: 'retained-code' });
    useUserStore.setState({
      userInfo: { ...useUserStore.getState().userInfo!, openid: '' },
    });
    render(courseRoute());
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectNoProfileStart();

    await showPage(false);
    await act(async () => {
      jest.advanceTimersByTime(30_000);
    });
    expectNoProfileStart();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);

    await showPage(true);
    expectProfileStarted();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    await showPage(true);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectProfileStarted();
  });

  test('restores Profile after BFCache return from recovery without exchanging a spent code twice', async () => {
    setQuery('code=spent-code');
    useSystemStore.setState({ wechatCode: 'spent-code' });
    useUserStore.setState({
      userInfo: { ...useUserStore.getState().userInfo!, openid: '' },
    });
    mockUpdateWxcode.mockRejectedValue(new Error('exchange failed'));
    render(courseRoute());
    await flush();
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).toHaveBeenCalledWith({ wxcode: 'spent-code' });
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expectNoProfileStart();

    await showPage(true);
    expectProfileStarted();
    await act(async () => {
      jest.advanceTimersByTime(30_000);
    });
    expect(mockUpdateWxcode).toHaveBeenCalledTimes(1);
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expectProfileStarted();
  });

  test('keeps BFCache preparation abandoned when the child page remounts before Profile eligibility resolves', async () => {
    const eligibility = deferred<typeof onboardingStatus>();
    mockGetProfileOnboarding.mockReturnValue(eligibility.promise);
    useUserStore.setState({
      userInfo: { ...useUserStore.getState().userInfo!, openid: '' },
    });
    const view = render(courseRoute());
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    await showPage(true);
    view.rerender(courseRoute('restored-remounted-page'));
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectNoProfileStart();

    await act(async () => {
      eligibility.resolve(onboardingStatus);
    });
    await flush();
    expectProfileStarted();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
  });

  test.each([
    'ordinary browser',
    'mini program',
    'disabled wxcode',
    'missing appId',
  ])('preserves Profile startup in %s', async scenario => {
    if (scenario === 'ordinary browser') mockInWechat = false;
    if (scenario === 'mini program') mockInMiniProgram = true;
    if (scenario === 'disabled wxcode')
      useEnvStore.setState({ enableWxcode: 'false' });
    if (scenario === 'missing appId') useEnvStore.setState({ appId: '' });
    render(courseRoute());
    await flush();
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectProfileStarted();
  });

  test('keeps teacher preview runtime available without opening learner Profile during authorization', async () => {
    setQuery('preview=true');
    useSystemStore.setState({ previewMode: true });
    render(courseRoute());
    await flush();
    expect(screen.getByTestId('chat-runtime')).toHaveAttribute(
      'data-ready',
      'true',
    );
    expectNoProfileStart();
  });

  test('waits for runtime configuration before deciding whether layout authorization is required', async () => {
    useEnvStore.setState({ runtimeConfigLoaded: false });
    render(courseRoute());
    await flush();
    expect(mockWechatLogin).not.toHaveBeenCalled();
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expectNoProfileStart();
    await act(async () => {
      useEnvStore.setState({ runtimeConfigLoaded: true });
    });
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expectNoProfileStart();
  });

  test('allows Profile and user initialization when layout navigation throws synchronously', async () => {
    mockWechatLogin.mockImplementationOnce(() => {
      throw new Error('navigation unavailable');
    });
    render(courseRoute());
    await flush();
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(useUserStore.getState().initUser).toHaveBeenCalled();
    expectProfileStarted();
  });

  test('clears a retained code before releasing Profile after synchronous navigation failure', async () => {
    useSystemStore.setState({ wechatCode: 'retained-code' });
    mockWechatLogin.mockImplementationOnce(() => {
      throw new Error('navigation unavailable');
    });
    render(courseRoute());
    await flush();
    expect(mockUpdateWxcode).not.toHaveBeenCalled();
    expect(useSystemStore.getState().wechatCode).toBe('');
    expect(mockWechatLogin).toHaveBeenCalledTimes(1);
    expect(useUserStore.getState().initUser).toHaveBeenCalled();
    expectProfileStarted();
  });
});

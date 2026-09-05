import React, { useEffect } from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import ChatLayout from '@/app/c/[[...id]]/layout';
import LearningModeSwitch from '@/app/c/[[...id]]/Components/LearningModeSwitch';
import { CourseInfoFetchError, getCourseInfo } from '@/api/course';
import { useCourseStore, useEnvStore } from '@/store';
import { useSystemStore } from '@/store/useSystemStore';

let mockSearchParamsValue = '';
const mockTrackEvent = jest.fn();

jest.mock('sse.js', () => ({
  SSE: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: ['123'] }),
  useSearchParams: () => new URLSearchParams(mockSearchParamsValue),
}));

jest.mock('@/api/course', () => ({
  ...jest.requireActual('@/api/course'),
  getCourseInfo: jest.fn(),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/store', () => {
  const initUser = jest.fn();
  const useUserStore = jest.fn(() => ({
    userInfo: null,
    initUser,
  }));
  (useUserStore as any).getState = () => ({
    getToken: () => '',
  });
  return {
    __esModule: true,
    ...jest.requireActual('@/store/envStore'),
    ...jest.requireActual('@/store/useCourseStore'),
    ...jest.requireActual('@/store/useSystemStore'),
    ...jest.requireActual('@/store/useUiLayoutStore'),
    UserProvider: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    useUserStore,
  };
});

jest.mock('@/store/userProvider', () => ({
  UserProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

jest.mock('@/store/useUserStore', () => {
  const initUser = jest.fn();
  const useUserStore = jest.fn(() => ({
    userInfo: null,
    initUser,
    isInitialized: true,
    isLoggedIn: false,
  }));
  (useUserStore as any).getState = () => ({
    getToken: () => '',
  });
  return { useUserStore };
});

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

const i18nMock = {
  language: 'en-US',
  changeLanguage: jest.fn(),
};

jest.mock('react-i18next', () => {
  const t = (key: string) => key;
  return {
    useTranslation: () => ({
      t,
      i18n: i18nMock,
    }),
  };
});

describe('C preview layout', () => {
  const originalHref = window.location.href;
  const mockedGetCourseInfo = getCourseInfo as jest.MockedFunction<
    typeof getCourseInfo
  >;
  const contentLabel = 'content';
  const buildCourseInfo = (
    isOwner: boolean,
    courseId = 'course-transient',
    courseDescription = 'Description',
  ) => ({
    course_desc: courseDescription,
    course_id: courseId,
    course_keywords: ['test'],
    course_name: 'Course',
    course_price: '0',
    course_teacher_avatar: '',
    course_avatar: '',
    course_tts_enabled: true,
    default_listen_mode_enabled: false,
    course_is_owner: isOwner,
  });
  const createDeferredCourseInfo = () => {
    let resolve!: (value: ReturnType<typeof buildCourseInfo>) => void;
    const promise = new Promise<ReturnType<typeof buildCourseInfo>>(
      resolvePromise => {
        resolve = resolvePromise;
      },
    );
    return { promise, resolve };
  };

  afterEach(() => {
    jest.useRealTimers();
    mockSearchParamsValue = '';
    mockTrackEvent.mockReset();
    window.localStorage.clear();
    window.location.href = originalHref;
    mockedGetCourseInfo.mockReset();
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: false,
        courseId: '',
      });
    });
    act(() => {
      useSystemStore.setState({ previewMode: false, skip: false });
      useCourseStore.setState({
        courseSettingsCourseId: null,
        courseTtsEnabled: null,
        courseDescription: '',
        isCurrentUserCourseOwner: null,
      });
    });
  });

  test('tracks a stored mode once and only tracks selection after an explicit switch', async () => {
    window.history.replaceState({}, '', '/c/123');
    window.localStorage.setItem('course_learning_mode:123', 'read');
    act(() => {
      useSystemStore.setState({
        learningMode: 'read',
        canUseClassroomMode: false,
        previewMode: false,
        skip: false,
      });
      useCourseStore.setState({
        courseSettingsCourseId: '123',
        courseTtsEnabled: true,
      });
    });

    const view = render(
      <ChatLayout>
        <LearningModeSwitch />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_last_learning_mode',
        {
          shifu_bid: '123',
          learning_mode: 'read',
        },
      );
    });

    fireEvent.click(
      screen.getByRole('radio', {
        name: 'module.chat.learningModeListen',
      }),
    );

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_learning_mode_select',
        {
          from_learning_mode: 'read',
          to_learning_mode: 'listen',
          source: 'mobile_switch',
        },
      );
    });

    mockSearchParamsValue = 'mode=listen';
    view.rerender(
      <ChatLayout>
        <LearningModeSwitch />
      </ChatLayout>,
    );
    await act(async () => {});

    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_last_learning_mode',
      ),
    ).toHaveLength(1);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_learning_mode_select',
      ),
    ).toHaveLength(1);
  });

  test('does not report stored-mode restoration when a URL override initializes the route', async () => {
    mockSearchParamsValue = 'mode=listen';
    window.history.replaceState({}, '', '/c/123?mode=listen');
    window.localStorage.setItem('course_learning_mode:123', 'read');
    act(() => {
      useSystemStore.setState({
        learningMode: 'read',
        canUseClassroomMode: false,
        previewMode: false,
        skip: false,
      });
      useCourseStore.setState({
        courseSettingsCourseId: '123',
        courseTtsEnabled: true,
      });
    });

    render(
      <ChatLayout>
        <LearningModeSwitch />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(useSystemStore.getState().learningMode).toBe('listen');
    });
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_last_learning_mode',
      expect.anything(),
    );
  });

  test('does not report a stored listen mode when TTS is unavailable', async () => {
    window.history.replaceState({}, '', '/c/123');
    window.localStorage.setItem('course_learning_mode:123', 'listen');
    act(() => {
      useSystemStore.setState({
        learningMode: 'read',
        canUseClassroomMode: false,
        previewMode: false,
        skip: false,
      });
      useCourseStore.setState({
        courseSettingsCourseId: '123',
        courseTtsEnabled: false,
      });
    });

    render(
      <ChatLayout>
        <LearningModeSwitch />
      </ChatLayout>,
    );

    await act(async () => {});
    expect(useSystemStore.getState().learningMode).toBe('read');
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_last_learning_mode',
      expect.anything(),
    );
  });

  test('waits for TTS capability before reporting a stored listen mode', async () => {
    window.history.replaceState({}, '', '/c/123');
    window.localStorage.setItem('course_learning_mode:123', 'listen');
    act(() => {
      useSystemStore.setState({
        learningMode: 'read',
        canUseClassroomMode: false,
        previewMode: false,
        skip: false,
      });
      useCourseStore.setState({
        courseSettingsCourseId: '123',
        courseTtsEnabled: null,
      });
    });

    render(
      <ChatLayout>
        <LearningModeSwitch />
      </ChatLayout>,
    );

    await act(async () => {});
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_last_learning_mode',
      expect.anything(),
    );

    act(() => {
      useCourseStore.getState().updateCourseSettings('123', {
        ttsEnabled: true,
        defaultListenModeEnabled: false,
      });
    });

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_last_learning_mode',
        {
          shifu_bid: '123',
          learning_mode: 'listen',
        },
      );
    });
  });

  test('does not report the initial stored mode after an explicit selection while capability is pending', async () => {
    window.history.replaceState({}, '', '/c/123');
    window.localStorage.setItem('course_learning_mode:123', 'listen');
    act(() => {
      useSystemStore.setState({
        learningMode: 'read',
        canUseClassroomMode: false,
        previewMode: false,
        skip: false,
      });
      useCourseStore.setState({
        courseSettingsCourseId: '123',
        courseTtsEnabled: null,
      });
    });

    render(
      <ChatLayout>
        <LearningModeSwitch />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(useSystemStore.getState().learningMode).toBe('listen');
    });
    fireEvent.click(
      screen.getByRole('radio', {
        name: 'module.chat.learningModeRead',
      }),
    );
    await waitFor(() => {
      expect(window.localStorage.getItem('course_learning_mode:123')).toBe(
        'read',
      );
    });

    act(() => {
      useCourseStore.getState().updateCourseSettings('123', {
        ttsEnabled: true,
        defaultListenModeEnabled: false,
      });
    });
    await act(async () => {});

    expect(useSystemStore.getState().learningMode).toBe('read');
    expect(window.localStorage.getItem('course_learning_mode:123')).toBe(
      'read',
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_last_learning_mode',
      expect.anything(),
    );
  });

  test('applies preview mode before child effects run', async () => {
    mockSearchParamsValue = 'preview=true';
    window.history.replaceState({}, '', '/c/123?preview=true');
    act(() => {
      useSystemStore.setState({ previewMode: false, skip: false });
    });

    let observedPreviewMode: boolean | null = null;

    function Probe() {
      const previewMode = useSystemStore(state => state.previewMode);
      useEffect(() => {
        observedPreviewMode = previewMode;
      }, [previewMode]);
      return null;
    }

    render(
      <ChatLayout>
        <Probe />
      </ChatLayout>,
    );

    await act(async () => {});
    expect(observedPreviewMode).toBe(true);
  });

  test('waits for query state before rendering children', async () => {
    mockSearchParamsValue = 'preview=true&skip=true&channel=wechat';
    window.history.replaceState(
      {},
      '',
      '/c/123?preview=true&skip=true&channel=wechat',
    );
    act(() => {
      useSystemStore.setState({
        channel: '',
        previewMode: false,
        skip: false,
      });
    });

    const observedQueryState: Array<{
      channel: string;
      previewMode: boolean;
      skip: boolean;
    }> = [];

    function Probe() {
      const channel = useSystemStore(state => state.channel);
      const previewMode = useSystemStore(state => state.previewMode);
      const skip = useSystemStore(state => state.skip);
      observedQueryState.push({ channel, previewMode, skip });
      return null;
    }

    render(
      <ChatLayout>
        <Probe />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(observedQueryState).toEqual([
        {
          channel: 'wechat',
          previewMode: true,
          skip: true,
        },
      ]);
    });
  });

  test('marks course ownership unresolved while preview info is loading', async () => {
    mockSearchParamsValue = 'preview=true';
    window.history.replaceState({}, '', '/c/123?preview=true');
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-preview',
      });
      useCourseStore.setState({ isCurrentUserCourseOwner: true });
    });
    mockedGetCourseInfo.mockReturnValue(new Promise(() => {}));

    render(
      <ChatLayout>
        <div>{contentLabel}</div>
      </ChatLayout>,
    );

    await waitFor(() => expect(mockedGetCourseInfo).toHaveBeenCalled());
    expect(useCourseStore.getState().isCurrentUserCourseOwner).toBeNull();
  });

  test('updates query state after search params change', async () => {
    mockSearchParamsValue = 'preview=true&skip=false&channel=wechat';
    window.history.replaceState(
      {},
      '',
      '/c/123?preview=true&skip=false&channel=wechat',
    );
    act(() => {
      useSystemStore.setState({
        channel: '',
        previewMode: false,
        skip: false,
      });
    });

    const { rerender } = render(
      <ChatLayout>
        <div>{contentLabel}</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(useSystemStore.getState()).toMatchObject({
        channel: 'wechat',
        previewMode: true,
        skip: false,
      });
    });

    mockSearchParamsValue = 'preview=false&skip=true&channel=app';
    window.history.replaceState(
      {},
      '',
      '/c/123?preview=false&skip=true&channel=app',
    );

    rerender(
      <ChatLayout>
        <div>{contentLabel}</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(useSystemStore.getState()).toMatchObject({
        channel: 'app',
        previewMode: false,
        skip: true,
      });
    });
  });

  test('ignores stale course info responses after course navigation', async () => {
    const firstCourseInfo = createDeferredCourseInfo();
    const secondCourseInfo = createDeferredCourseInfo();
    mockedGetCourseInfo.mockImplementation(courseId => {
      return courseId === 'course-a'
        ? firstCourseInfo.promise
        : secondCourseInfo.promise;
    });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-a',
      });
      useCourseStore.setState({ courseDescription: 'Previous description' });
    });

    render(
      <ChatLayout>
        <div>{contentLabel}</div>
      </ChatLayout>,
    );

    await waitFor(() =>
      expect(mockedGetCourseInfo).toHaveBeenCalledWith(
        'course-a',
        false,
        undefined,
      ),
    );
    expect(useCourseStore.getState().courseDescription).toBe('');

    act(() => {
      useEnvStore.setState({ courseId: 'course-b' });
    });
    await waitFor(() =>
      expect(mockedGetCourseInfo).toHaveBeenCalledWith(
        'course-b',
        false,
        undefined,
      ),
    );

    await act(async () => {
      secondCourseInfo.resolve(
        buildCourseInfo(false, 'course-b', 'Course B description'),
      );
      await secondCourseInfo.promise;
    });
    expect(useCourseStore.getState().isCurrentUserCourseOwner).toBe(false);
    expect(useCourseStore.getState().courseDescription).toBe(
      'Course B description',
    );

    await act(async () => {
      firstCourseInfo.resolve(
        buildCourseInfo(true, 'course-a', 'Stale course A description'),
      );
      await firstCourseInfo.promise;
    });
    expect(useCourseStore.getState().isCurrentUserCourseOwner).toBe(false);
    expect(useCourseStore.getState().courseDescription).toBe(
      'Course B description',
    );
  });

  test('does not retain a previous description when course loading fails', async () => {
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-denied',
      });
      useCourseStore.setState({ courseDescription: 'Previous description' });
    });
    mockedGetCourseInfo.mockRejectedValue(
      new CourseInfoFetchError({
        status: 403,
        code: 403,
        message: 'Access denied',
      }),
    );

    render(
      <ChatLayout>
        <div>{contentLabel}</div>
      </ChatLayout>,
    );

    await waitFor(() => expect(mockedGetCourseInfo).toHaveBeenCalled());
    expect(useCourseStore.getState().courseDescription).toBe('');
  });

  test('redirects to /404 when course is not found', async () => {
    window.location.href = 'http://localhost:3000/c/123';
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-404',
      });
    });
    mockedGetCourseInfo.mockRejectedValue({
      isCourseNotFound: true,
      message: 'Course not found',
    });

    render(
      <ChatLayout>
        <div>{contentLabel}</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(window.location.href).toContain('/404');
    });
  });

  test.each([
    { status: 401, code: undefined },
    { status: 403, code: undefined },
    { status: 200, code: 401 },
    { status: 200, code: 403 },
    { status: 200, code: 404 },
  ])(
    'does not retry terminal course access status $status with business code $code',
    async ({ status, code }) => {
      jest.useFakeTimers();
      mockSearchParamsValue = 'preview=true';
      window.history.replaceState({}, '', '/c/123?preview=true');
      act(() => {
        useEnvStore.setState({
          runtimeConfigLoaded: true,
          courseId: `course-access-${status}-${code ?? 'none'}`,
        });
      });
      const courseInfoError = new CourseInfoFetchError({
        status,
        code,
        message: 'Access denied',
      });
      expect(courseInfoError.status).toBe(status);
      expect(courseInfoError.code).toBe(code);
      mockedGetCourseInfo.mockRejectedValue(courseInfoError);

      render(
        <ChatLayout>
          <div>{contentLabel}</div>
        </ChatLayout>,
      );

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(mockedGetCourseInfo).toHaveBeenCalledTimes(1);

      await act(async () => {
        jest.advanceTimersByTime(60000);
        await Promise.resolve();
      });
      expect(mockedGetCourseInfo).toHaveBeenCalledTimes(1);
      expect(window.location.href.includes('/404')).toBe(code === 404);
    },
  );

  test.each([
    { status: 500, code: 500 },
    { status: 200, code: 500 },
    { status: undefined, code: undefined },
  ])(
    'retries transient course info errors with status $status and code $code until ownership resolves',
    async ({ status, code }) => {
      jest.useFakeTimers();
      window.location.href = 'http://localhost:3000/c/123';
      act(() => {
        useEnvStore.setState({
          runtimeConfigLoaded: true,
          courseId: 'course-transient',
        });
      });
      mockedGetCourseInfo
        .mockRejectedValueOnce(
          new CourseInfoFetchError({
            status,
            code,
            message: 'Temporary failure',
          }),
        )
        .mockResolvedValueOnce(buildCourseInfo(true));

      render(
        <ChatLayout>
          <div>{contentLabel}</div>
        </ChatLayout>,
      );

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(mockedGetCourseInfo).toHaveBeenCalledTimes(1);
      expect(useCourseStore.getState().isCurrentUserCourseOwner).toBeNull();

      await act(async () => {
        jest.advanceTimersByTime(1000);
        await Promise.resolve();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(mockedGetCourseInfo).toHaveBeenCalledTimes(2);
      expect(useCourseStore.getState().isCurrentUserCourseOwner).toBe(true);
      expect(window.location.href).toContain('/c/123');
      expect(window.location.href).not.toContain('/404');
    },
  );
});

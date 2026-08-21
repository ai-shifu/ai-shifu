import React, { useEffect } from 'react';
import { act, render, waitFor } from '@testing-library/react';

import ChatLayout from '@/app/c/[[...id]]/layout';
import { getCourseInfo } from '@/c-api/course';
import { useCourseStore, useEnvStore } from '@/c-store';
import { useSystemStore } from '@/c-store/useSystemStore';

let mockSearchParamsValue = '';

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: ['123'] }),
  useSearchParams: () => new URLSearchParams(mockSearchParamsValue),
}));

jest.mock('@/c-api/course', () => ({
  getCourseInfo: jest.fn(),
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
  ) => ({
    course_desc: 'Description',
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
      useCourseStore.setState({ isCurrentUserCourseOwner: null });
    });
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

  test('ignores stale ownership responses after course navigation', async () => {
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
      secondCourseInfo.resolve(buildCourseInfo(false, 'course-b'));
      await secondCourseInfo.promise;
    });
    expect(useCourseStore.getState().isCurrentUserCourseOwner).toBe(false);

    await act(async () => {
      firstCourseInfo.resolve(buildCourseInfo(true, 'course-a'));
      await firstCourseInfo.promise;
    });
    expect(useCourseStore.getState().isCurrentUserCourseOwner).toBe(false);
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

  test.each([401, 403])(
    'does not retry terminal course access status %s',
    async status => {
      jest.useFakeTimers();
      act(() => {
        useEnvStore.setState({
          runtimeConfigLoaded: true,
          courseId: `course-access-${status}`,
        });
      });
      mockedGetCourseInfo.mockRejectedValue({
        isCourseNotFound: false,
        status,
        message: 'Access denied',
      });

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
    },
  );

  test('retries transient course info errors until ownership resolves', async () => {
    jest.useFakeTimers();
    window.location.href = 'http://localhost:3000/c/123';
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-transient',
      });
    });
    mockedGetCourseInfo
      .mockRejectedValueOnce({
        isCourseNotFound: false,
        code: 500,
        message: 'Temporary failure',
      })
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
  });
});

import React, { useEffect } from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';

import ChatLayout from '@/app/c/[[...id]]/layout';
import { getCourseInfo } from '@/c-api/course';
import { useEnvStore } from '@/c-store';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useSystemStore } from '@/c-store/useSystemStore';

const mockUseParams = jest.fn(() => ({ id: ['123'] }));

jest.mock('next/navigation', () => ({
  ...jest.requireActual('next/navigation'),
  useParams: () => mockUseParams(),
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
const mockTranslate = (key: string) => key;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockTranslate,
    i18n: i18nMock,
  }),
}));

describe('C preview layout', () => {
  const originalLocation = window.location;
  const originalHref = window.location.href;
  const mockedGetCourseInfo = getCourseInfo as jest.MockedFunction<
    typeof getCourseInfo
  >;
  const buildCourseInfo = ({
    courseId,
    courseName,
    courseTtsEnabled,
  }: {
    courseId: string;
    courseName: string;
    courseTtsEnabled: boolean;
  }): Awaited<ReturnType<typeof getCourseInfo>> => ({
    course_id: courseId,
    course_name: courseName,
    course_price: 0,
    course_avatar: '',
    course_teacher_avatar: '',
    course_tts_enabled: courseTtsEnabled,
    course_desc: '',
    course_keywords: '',
  });

  afterEach(() => {
    cleanup();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
    window.location.href = originalHref;
    window.localStorage.clear();
    mockUseParams.mockReturnValue({ id: ['123'] });
    mockedGetCourseInfo.mockReset();
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: false,
        courseId: '',
      });
    });
    act(() => {
      useSystemStore.setState({
        previewMode: false,
        skip: false,
        learningMode: 'read',
        showLearningModeToggle: false,
        canUseClassroomMode: null,
      });
    });
    act(() => {
      useCourseStore.setState({
        courseTtsEnabled: null,
        courseTtsStatusCourseId: null,
        courseTtsStatusPreviewMode: null,
      });
    });
  });

  test('applies preview mode before child effects run', async () => {
    window.location.href = 'http://localhost:3000/c/123?preview=true';
    act(() => {
      useSystemStore.setState({ previewMode: false, skip: false });
    });

    let observedPreviewMode: boolean | null = null;

    function Probe() {
      const previewMode = useSystemStore(state => state.previewMode);
      useEffect(() => {
        observedPreviewMode = previewMode;
      }, []);
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
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(window.location.href).toContain('/404');
    });
  });

  test('does not redirect to /404 for transient course info errors', async () => {
    window.location.href = 'http://localhost:3000/c/123';
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-transient',
      });
    });
    mockedGetCourseInfo.mockRejectedValue({
      isCourseNotFound: false,
      code: 500,
      message: 'Temporary failure',
    });

    render(
      <ChatLayout>
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(mockedGetCourseInfo).toHaveBeenCalled();
    });
    expect(window.location.href).toContain('/c/123');
    expect(window.location.href).not.toContain('/404');
  });

  test('ignores stale course info responses after route changes', async () => {
    window.location.href = 'http://localhost:3000/c/old-course';
    mockUseParams.mockReturnValue({ id: ['old-course'] });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'old-course',
      });
    });

    let resolveOldCourse:
      | ((value: Awaited<ReturnType<typeof getCourseInfo>>) => void)
      | undefined;

    mockedGetCourseInfo.mockImplementation(requestedCourseId => {
      if (requestedCourseId === 'old-course') {
        return new Promise(resolve => {
          resolveOldCourse = resolve;
        });
      }

      return Promise.resolve(
        buildCourseInfo({
          courseId: 'new-course',
          courseName: 'New course',
          courseTtsEnabled: true,
        }),
      );
    });

    const { rerender } = render(
      <ChatLayout>
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(mockedGetCourseInfo).toHaveBeenCalledWith('old-course', false);
    });

    window.location.href = 'http://localhost:3000/c/new-course';
    mockUseParams.mockReturnValue({ id: ['new-course'] });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'new-course',
      });
    });
    rerender(
      <ChatLayout>
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(document.title).toBe('New course - common.core.brandName');
    });

    await act(async () => {
      resolveOldCourse?.(
        buildCourseInfo({
          courseId: 'old-course',
          courseName: 'Old course',
          courseTtsEnabled: false,
        }),
      );
    });

    expect(useCourseStore.getState().courseTtsStatusCourseId).toBe(
      'new-course',
    );
    expect(useCourseStore.getState().courseTtsEnabled).toBe(true);
  });

  test('does not reuse published TTS status for preview mode defaults', async () => {
    window.location.href = 'http://localhost:3000/c/course-1?preview=true';
    mockUseParams.mockReturnValue({ id: ['course-1'] });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-1',
      });
      useCourseStore.setState({
        courseTtsEnabled: false,
        courseTtsStatusCourseId: 'course-1',
        courseTtsStatusPreviewMode: false,
      });
      useSystemStore.setState({ learningMode: 'read' });
    });
    mockedGetCourseInfo.mockImplementation(
      () => new Promise<Awaited<ReturnType<typeof getCourseInfo>>>(() => {}),
    );

    render(
      <ChatLayout>
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(mockedGetCourseInfo).toHaveBeenCalledWith('course-1', true);
    });
    await act(async () => {});
    expect(window.localStorage.getItem('course_learning_mode:course-1')).toBe(
      null,
    );
  });

  test('does not persist read for a new route before course-specific TTS status loads', async () => {
    window.location.href = 'http://localhost:3000/c/new-course';
    mockUseParams.mockReturnValue({ id: ['new-course'] });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'old-course',
      });
      useCourseStore.setState({
        courseTtsEnabled: false,
        courseTtsStatusCourseId: 'old-course',
        courseTtsStatusPreviewMode: false,
      });
      useSystemStore.setState({ learningMode: 'read' });
    });
    mockedGetCourseInfo.mockImplementation(requestedCourseId => {
      if (requestedCourseId === 'old-course') {
        return Promise.resolve(
          buildCourseInfo({
            courseId: 'old-course',
            courseName: 'Old course',
            courseTtsEnabled: false,
          }),
        );
      }

      return new Promise<Awaited<ReturnType<typeof getCourseInfo>>>(() => {});
    });

    render(
      <ChatLayout>
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(mockedGetCourseInfo).toHaveBeenCalledWith('new-course', false);
    });
    await act(async () => {});
    expect(window.localStorage.getItem('course_learning_mode:new-course')).toBe(
      null,
    );
  });

  test('keeps course content mounted while waiting for course-specific TTS', async () => {
    window.location.href = 'http://localhost:3000/c/course-1';
    mockUseParams.mockReturnValue({ id: ['course-1'] });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-1',
      });
      useSystemStore.setState({ learningMode: 'read' });
    });

    let resolveCourseInfo:
      | ((value: Awaited<ReturnType<typeof getCourseInfo>>) => void)
      | undefined;
    mockedGetCourseInfo.mockImplementation(
      () =>
        new Promise(resolve => {
          resolveCourseInfo = resolve;
        }),
    );

    render(
      <ChatLayout>
        <div>course content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(mockedGetCourseInfo).toHaveBeenCalledWith('course-1', false);
    });
    expect(screen.getByText('course content')).toBeInTheDocument();

    await act(async () => {
      resolveCourseInfo?.(
        buildCourseInfo({
          courseId: 'course-1',
          courseName: 'Course 1',
          courseTtsEnabled: true,
        }),
      );
    });

    await waitFor(() => {
      expect(useSystemStore.getState().learningMode).toBe('listen');
    });
  });

  test('does not persist automatic listen defaults as course preferences', async () => {
    window.location.href = 'http://localhost:3000/c/course-1';
    mockUseParams.mockReturnValue({ id: ['course-1'] });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-1',
      });
      useSystemStore.setState({ learningMode: 'read' });
    });
    mockedGetCourseInfo.mockResolvedValue(
      buildCourseInfo({
        courseId: 'course-1',
        courseName: 'Course 1',
        courseTtsEnabled: true,
      }),
    );

    render(
      <ChatLayout>
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(useSystemStore.getState().learningMode).toBe('listen');
    });
    expect(window.localStorage.getItem('course_learning_mode:course-1')).toBe(
      null,
    );
  });

  test('does not persist automatic read defaults when course TTS is disabled', async () => {
    window.location.href = 'http://localhost:3000/c/course-1';
    mockUseParams.mockReturnValue({ id: ['course-1'] });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-1',
      });
      useSystemStore.setState({ learningMode: 'read' });
    });
    mockedGetCourseInfo.mockResolvedValue(
      buildCourseInfo({
        courseId: 'course-1',
        courseName: 'Course 1',
        courseTtsEnabled: false,
      }),
    );

    render(
      <ChatLayout>
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(mockedGetCourseInfo).toHaveBeenCalledWith('course-1', false);
    });
    await waitFor(() => {
      expect(screen.getByText('content')).toBeInTheDocument();
    });
    expect(window.localStorage.getItem('course_learning_mode:course-1')).toBe(
      null,
    );
  });

  test('normalizes listen URL mode to read when course TTS is disabled', async () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        href: 'http://localhost:3000/c/course-1?mode=listen',
        pathname: '/c/course-1',
        search: '?mode=listen',
        hash: '',
      },
    });
    const replaceStateSpy = jest
      .spyOn(window.history, 'replaceState')
      .mockImplementation(() => undefined);
    mockUseParams.mockReturnValue({ id: ['course-1'] });
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'course-1',
      });
      useSystemStore.setState({ learningMode: 'read' });
    });
    mockedGetCourseInfo.mockResolvedValue(
      buildCourseInfo({
        courseId: 'course-1',
        courseName: 'Course 1',
        courseTtsEnabled: false,
      }),
    );

    render(
      <ChatLayout>
        <div>content</div>
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(useSystemStore.getState().learningMode).toBe('read');
      expect(replaceStateSpy).toHaveBeenCalledWith(
        window.history.state,
        '',
        '/c/course-1?mode=read',
      );
    });
    replaceStateSpy.mockRestore();
  });
});

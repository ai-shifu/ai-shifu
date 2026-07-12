import React, { useEffect } from 'react';
import { act, render, waitFor } from '@testing-library/react';

import ChatLayout from '@/app/c/[[...id]]/layout';
import { getCourseInfo } from '@/c-api/course';
import { useEnvStore } from '@/c-store';
import { useSystemStore } from '@/c-store/useSystemStore';

jest.mock('@/c-api/course', () => ({
  getCourseInfo: jest.fn(),
}));

jest.mock('@/c-api/lesson', () => ({
  resetChapter: jest.fn(),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: jest.fn() }),
}));

jest.mock('@/c-common/tools/tracking', () => ({
  tracking: jest.fn(),
}));

jest.mock('@/c-constants/uiConstants', () => ({
  calcFrameLayout: () => 1,
  inMiniProgram: () => false,
  inWechat: () => false,
  wechatLogin: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: ['123'] }),
}));

jest.mock('@/store/userProvider', () => ({
  UserProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

jest.mock('@/store/useUserStore', () => {
  const state = {
    userInfo: null,
    initUser: jest.fn(),
    isInitialized: true,
    isLoggedIn: false,
    getToken: () => '',
  };
  return {
    useUserStore: Object.assign(() => state, {
      getState: () => state,
    }),
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
const translate = (key: string) => key;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: translate,
    i18n: i18nMock,
  }),
}));

describe('C preview layout', () => {
  const originalHref = window.location.href;
  const mockedGetCourseInfo = getCourseInfo as jest.MockedFunction<
    typeof getCourseInfo
  >;

  afterEach(() => {
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
    });
  });

  test('applies preview mode before child effects run', async () => {
    window.location.href = 'http://localhost:3000/c/123?preview=true';
    act(() => {
      useEnvStore.setState({
        runtimeConfigLoaded: true,
        courseId: 'preview-course',
      });
      useSystemStore.setState({ previewMode: false, skip: false });
    });
    mockedGetCourseInfo.mockResolvedValue({
      course_id: 'preview-course',
      course_slug: 'preview-course-primary-link',
      course_canonical_url: '/c/preview-course-primary-link',
      course_name: 'Preview course',
      course_desc: 'Preview course description',
      course_keywords: 'preview',
      course_price: 0,
      course_teacher_avatar: '',
      course_avatar: '',
      course_tts_enabled: false,
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

    await waitFor(() => {
      expect(observedPreviewMode).toBe(true);
    });
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
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
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
    warnSpy.mockRestore();
  });
});

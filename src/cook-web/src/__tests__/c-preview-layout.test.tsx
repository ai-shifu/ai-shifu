import React, { useEffect } from 'react';
import { act, render, waitFor } from '@testing-library/react';

import ChatLayout from '@/app/c/[[...id]]/layout';
import { getCourseInfo } from '@/c-api/course';
import { useEnvStore } from '@/c-store';
import { useSystemStore } from '@/c-store/useSystemStore';

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

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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
});

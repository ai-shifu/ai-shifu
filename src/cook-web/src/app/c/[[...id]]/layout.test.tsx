import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { getCourseInfo } from '@/c-api/course';
import { useCourseStore, useEnvStore, useSystemStore } from '@/c-store';
import { getQueryParams } from '@/c-utils/urlUtils';
import ChatLayout from './layout';

let mockRouteIdentifier = 'legacy-bid';
const mockInitUser = jest.fn();
const mockUpdateCanUseClassroomMode = jest.fn((value: boolean | null) => {
  useSystemStore.setState({ canUseClassroomMode: value });
});
const mockReplaceState = jest
  .spyOn(window.history, 'replaceState')
  .mockImplementation(() => {});

jest.mock('next/navigation', () => ({
  useParams: () =>
    mockRouteIdentifier ? { id: [mockRouteIdentifier] } : { id: undefined },
}));

jest.mock('react-i18next', () => {
  const i18n = {
    changeLanguage: jest.fn(),
  };
  const t = (key: string) => key;
  return {
    useTranslation: () => ({
      t,
      i18n,
    }),
  };
});

jest.mock('@/i18n', () => ({
  __esModule: true,
  browserLanguage: 'en-US',
  default: {
    language: 'en-US',
    resolvedLanguage: 'en-US',
  },
}));

jest.mock('@/c-api/course', () => ({
  getCourseInfo: jest.fn(),
}));

jest.mock('@/c-api/lesson', () => ({
  resetChapter: jest.fn(),
}));

jest.mock('@/c-constants/uiConstants', () => ({
  calcFrameLayout: () => 1,
  inMiniProgram: () => false,
  inWechat: () => false,
  wechatLogin: jest.fn(),
}));

jest.mock('@/c-common/tools/tracking', () => ({
  tracking: jest.fn(),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: jest.fn(),
  }),
}));

jest.mock('@/store/userProvider', () => ({
  UserProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

jest.mock('@/store/useUserStore', () => {
  const state = {
    userInfo: null,
    initUser: (...args: unknown[]) => mockInitUser(...args),
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

const courseInfo = {
  course_id: 'canonical-bid',
  course_slug: 'practical-ai-teaching-methods',
  course_canonical_url: '/c/practical-ai-teaching-methods',
  course_name: 'Practical AI Teaching Methods',
  course_desc: 'Course description',
  course_keywords: 'ai,teaching',
  course_price: 0,
  course_teacher_avatar: '/avatar.png',
  course_avatar: '/avatar.png',
  course_tts_enabled: true,
};

describe('learner course identity bootstrap', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRouteIdentifier = 'legacy-bid';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/legacy-bid?lessonid=lesson-1&mode=listen&preview=true#follow-up',
      pathname: '/c/legacy-bid',
      search: '?lessonid=lesson-1&mode=listen&preview=true',
      hash: '#follow-up',
    });
    useEnvStore.setState({
      courseId: '',
      courseSlug: '',
      courseCanonicalUrl: '',
      runtimeConfigLoaded: true,
      enableWxcode: 'false',
    });
    useCourseStore.setState({
      courseName: '',
      courseAvatar: '',
      courseTtsEnabled: null,
    });
    useSystemStore.setState({
      previewMode: false,
      skip: false,
      learningMode: 'read',
      canUseClassroomMode: null,
      showLearningModeToggle: false,
      updateCanUseClassroomMode: mockUpdateCanUseClassroomMode,
    });
  });

  test('gates children until a route identifier resolves to the canonical BID', async () => {
    let resolveCourseInfo: (value: typeof courseInfo) => void = () => {};
    (getCourseInfo as jest.Mock).mockReturnValue(
      new Promise(resolve => {
        resolveCourseInfo = resolve;
      }),
    );

    render(
      <ChatLayout>
        <div data-testid='learner-child' />
      </ChatLayout>,
    );

    expect(getQueryParams(window.location.href)).toMatchObject({
      preview: 'true',
    });
    expect(screen.queryByTestId('learner-child')).not.toBeInTheDocument();
    expect(getCourseInfo).toHaveBeenCalledWith('legacy-bid', true);

    await act(async () => {
      resolveCourseInfo(courseInfo);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId('learner-child')).toBeInTheDocument();
    });
    expect(useEnvStore.getState()).toMatchObject({
      courseId: 'canonical-bid',
      courseSlug: 'practical-ai-teaching-methods',
      courseCanonicalUrl: '/c/practical-ai-teaching-methods',
    });
    await waitFor(() => {
      expect(mockUpdateCanUseClassroomMode).toHaveBeenLastCalledWith(true);
      expect(useSystemStore.getState().canUseClassroomMode).toBe(true);
    });
    expect(mockReplaceState).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/practical-ai-teaching-methods?lessonid=lesson-1&mode=listen&preview=true#follow-up',
    );
  });

  test('keeps the custom-domain /c route while storing its canonical link', async () => {
    mockRouteIdentifier = '';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c?lessonid=lesson-1#follow-up',
      pathname: '/c',
      search: '?lessonid=lesson-1',
      hash: '#follow-up',
    });
    useEnvStore.setState({ courseId: 'canonical-bid' });
    (getCourseInfo as jest.Mock).mockResolvedValue(courseInfo);

    render(
      <ChatLayout>
        <div data-testid='learner-child' />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('learner-child')).toBeInTheDocument();
    });
    expect(window.location.pathname).toBe('/c');
    expect(window.location.search).toBe('?lessonid=lesson-1');
    expect(window.location.hash).toBe('#follow-up');
    expect(mockReplaceState).not.toHaveBeenCalled();
  });

  test('keeps children gated and lets a transient bootstrap failure retry', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    (getCourseInfo as jest.Mock)
      .mockRejectedValueOnce({ status: 500 })
      .mockResolvedValueOnce(courseInfo);

    render(
      <ChatLayout>
        <div data-testid='learner-child' />
      </ChatLayout>,
    );

    expect(
      await screen.findByText('common.core.requestFailed'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('learner-child')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'common.core.retry' }));

    await waitFor(() => {
      expect(screen.getByTestId('learner-child')).toBeInTheDocument();
    });
    expect(getCourseInfo).toHaveBeenCalledTimes(2);
    warnSpy.mockRestore();
  });
});

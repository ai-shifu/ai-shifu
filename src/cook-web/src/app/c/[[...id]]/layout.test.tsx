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

afterAll(() => {
  mockReplaceState.mockRestore();
});

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

const DownstreamCourseProbe = ({
  onMount,
}: {
  onMount: (courseId: string) => void;
}) => {
  const courseId = useEnvStore(state => state.courseId);

  React.useEffect(() => {
    onMount(courseId);
  }, [courseId, onMount]);

  return <div data-testid='downstream-course-probe'>{courseId}</div>;
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
    const downstreamRequest = jest.fn();
    let resolveCourseInfo: (value: typeof courseInfo) => void = () => {};
    (getCourseInfo as jest.Mock).mockReturnValue(
      new Promise(resolve => {
        resolveCourseInfo = resolve;
      }),
    );

    render(
      <ChatLayout>
        <DownstreamCourseProbe onMount={downstreamRequest} />
      </ChatLayout>,
    );

    expect(getQueryParams(window.location.href)).toMatchObject({
      preview: 'true',
    });
    expect(
      screen.queryByTestId('downstream-course-probe'),
    ).not.toBeInTheDocument();
    expect(downstreamRequest).not.toHaveBeenCalled();
    expect(getCourseInfo).toHaveBeenCalledWith('legacy-bid', true);

    await act(async () => {
      resolveCourseInfo(courseInfo);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId('downstream-course-probe')).toHaveTextContent(
        'canonical-bid',
      );
    });
    expect(downstreamRequest).toHaveBeenCalledTimes(1);
    expect(downstreamRequest).toHaveBeenCalledWith('canonical-bid');
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

  test('does not replace an already-canonical slug route', async () => {
    mockRouteIdentifier = 'practical-ai-teaching-methods';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/practical-ai-teaching-methods?mode=read#lesson',
      pathname: '/c/practical-ai-teaching-methods',
      search: '?mode=read',
      hash: '#lesson',
    });
    (getCourseInfo as jest.Mock).mockResolvedValue(courseInfo);

    render(
      <ChatLayout>
        <div data-testid='learner-child' />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('learner-child')).toBeInTheDocument();
    });
    expect(getCourseInfo).toHaveBeenCalledWith(
      'practical-ai-teaching-methods',
      false,
    );
    expect(mockReplaceState).not.toHaveBeenCalled();
    expect(useEnvStore.getState()).toMatchObject({
      courseId: 'canonical-bid',
      courseSlug: 'practical-ai-teaching-methods',
      courseCanonicalUrl: '/c/practical-ai-teaching-methods',
    });
  });

  test('converges a historical slug to the current slug while preserving query and hash', async () => {
    mockRouteIdentifier = 'historical-ai-teaching-course';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/historical-ai-teaching-course?preview=true&mode=listen&lessonid=lesson-2&utm_source=history#follow-up',
      pathname: '/c/historical-ai-teaching-course',
      search: '?preview=true&mode=listen&lessonid=lesson-2&utm_source=history',
      hash: '#follow-up',
    });
    (getCourseInfo as jest.Mock).mockResolvedValue(courseInfo);

    render(
      <ChatLayout>
        <div data-testid='learner-child' />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('learner-child')).toBeInTheDocument();
    });
    expect(getCourseInfo).toHaveBeenCalledWith(
      'historical-ai-teaching-course',
      true,
    );
    expect(mockReplaceState).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/practical-ai-teaching-methods?preview=true&mode=listen&lessonid=lesson-2&utm_source=history#follow-up',
    );
    expect(useEnvStore.getState()).toMatchObject({
      courseId: 'canonical-bid',
      courseSlug: 'practical-ai-teaching-methods',
      courseCanonicalUrl: '/c/practical-ai-teaching-methods',
    });
  });

  test('keeps a canonical BID route when the course does not have a slug yet', async () => {
    mockRouteIdentifier = 'canonical-bid';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/canonical-bid?preview=true#lesson',
      pathname: '/c/canonical-bid',
      search: '?preview=true',
      hash: '#lesson',
    });
    (getCourseInfo as jest.Mock).mockResolvedValue({
      ...courseInfo,
      course_slug: '',
      course_canonical_url: '/c/canonical-bid',
    });

    render(
      <ChatLayout>
        <div data-testid='learner-child' />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('learner-child')).toBeInTheDocument();
    });
    expect(mockReplaceState).not.toHaveBeenCalled();
    expect(useEnvStore.getState()).toMatchObject({
      courseId: 'canonical-bid',
      courseSlug: '',
      courseCanonicalUrl: '/c/canonical-bid',
    });
  });

  test('gates an already-mounted course immediately while the next course resolves', async () => {
    type CourseInfo = typeof courseInfo;
    const downstreamRequest = jest.fn();
    let resolveCourseB: (value: CourseInfo) => void = () => {};
    const courseAInfo: CourseInfo = {
      ...courseInfo,
      course_id: 'canonical-bid-a',
      course_slug: 'current-course-a-link',
      course_canonical_url: '/c/current-course-a-link',
      course_name: 'Current Course A',
    };
    const courseBInfo: CourseInfo = {
      ...courseInfo,
      course_id: 'canonical-bid-b',
      course_slug: 'current-course-b-link',
      course_canonical_url: '/c/current-course-b-link',
      course_name: 'Current Course B',
    };
    (getCourseInfo as jest.Mock).mockImplementation((identifier: string) => {
      if (identifier === 'current-course-a-link') {
        return Promise.resolve(courseAInfo);
      }
      if (identifier === 'historical-course-b-link') {
        return new Promise<CourseInfo>(resolve => {
          resolveCourseB = resolve;
        });
      }
      throw new Error(`Unexpected course identifier: ${identifier}`);
    });
    mockRouteIdentifier = 'current-course-a-link';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/current-course-a-link',
      pathname: '/c/current-course-a-link',
      search: '',
      hash: '',
    });

    const { rerender } = render(
      <ChatLayout>
        <DownstreamCourseProbe onMount={downstreamRequest} />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('downstream-course-probe')).toHaveTextContent(
        'canonical-bid-a',
      );
    });
    expect(downstreamRequest).toHaveBeenCalledWith('canonical-bid-a');
    downstreamRequest.mockClear();

    mockRouteIdentifier = 'historical-course-b-link';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/historical-course-b-link',
      pathname: '/c/historical-course-b-link',
    });
    rerender(
      <ChatLayout>
        <DownstreamCourseProbe onMount={downstreamRequest} />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(getCourseInfo).toHaveBeenCalledWith(
        'historical-course-b-link',
        false,
      );
    });
    expect(
      screen.queryByTestId('downstream-course-probe'),
    ).not.toBeInTheDocument();
    expect(downstreamRequest).not.toHaveBeenCalled();

    await act(async () => {
      resolveCourseB(courseBInfo);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getByTestId('downstream-course-probe')).toHaveTextContent(
        'canonical-bid-b',
      );
    });
    expect(downstreamRequest).toHaveBeenCalledTimes(1);
    expect(downstreamRequest).toHaveBeenCalledWith('canonical-bid-b');
  });

  test('ignores a late bootstrap response after navigating to another course', async () => {
    type CourseInfo = typeof courseInfo;
    let resolveCourseA: (value: CourseInfo) => void = () => {};
    let resolveCourseB: (value: CourseInfo) => void = () => {};
    const courseBInfo: CourseInfo = {
      ...courseInfo,
      course_id: 'canonical-bid-b',
      course_slug: 'advanced-course-design-methods',
      course_canonical_url: '/c/advanced-course-design-methods',
      course_name: 'Advanced Course Design Methods',
    };
    (getCourseInfo as jest.Mock).mockImplementation((identifier: string) => {
      if (identifier === 'legacy-bid-a') {
        return new Promise<CourseInfo>(resolve => {
          resolveCourseA = resolve;
        });
      }
      if (identifier === 'legacy-bid-b') {
        return new Promise<CourseInfo>(resolve => {
          resolveCourseB = resolve;
        });
      }
      throw new Error(`Unexpected course identifier: ${identifier}`);
    });
    mockRouteIdentifier = 'legacy-bid-a';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/legacy-bid-a',
      pathname: '/c/legacy-bid-a',
      search: '',
      hash: '',
    });

    const { rerender } = render(
      <ChatLayout>
        <div data-testid='learner-child' />
      </ChatLayout>,
    );
    expect(getCourseInfo).toHaveBeenCalledWith('legacy-bid-a', false);

    mockRouteIdentifier = 'legacy-bid-b';
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/legacy-bid-b',
      pathname: '/c/legacy-bid-b',
    });
    rerender(
      <ChatLayout>
        <div data-testid='learner-child' />
      </ChatLayout>,
    );

    await waitFor(() => {
      expect(getCourseInfo).toHaveBeenCalledWith('legacy-bid-b', false);
    });
    await act(async () => {
      resolveCourseB(courseBInfo);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getByTestId('learner-child')).toBeInTheDocument();
    });

    await act(async () => {
      resolveCourseA(courseInfo);
      await Promise.resolve();
    });

    expect(useEnvStore.getState()).toMatchObject({
      courseId: 'canonical-bid-b',
      courseSlug: 'advanced-course-design-methods',
      courseCanonicalUrl: '/c/advanced-course-design-methods',
    });
    expect(mockReplaceState).toHaveBeenCalledTimes(1);
    expect(mockReplaceState).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/advanced-course-design-methods',
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

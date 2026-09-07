import React from 'react';
import { act, render, screen } from '@testing-library/react';

import { useCourseStore } from '@/store/useCourseStore';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';
import { buildCoursePageUrl } from '@/lib/urlUtils';
import LearnerCourseShareButton from './LearnerCourseShareButton';

let mockRouteParams: { id?: string[] } = { id: ['course-1'] };

type MockCourseShareButtonProps = {
  courseTitle: string;
  courseDescription?: string;
  shifuBid: string;
  resolveShareUrl: () => string | null;
  surface: string;
};

const mockCourseShareButton = jest.fn(
  ({ surface }: MockCourseShareButtonProps) => (
    <button
      type='button'
      data-testid='course-share-button'
      data-surface={surface}
    />
  ),
);

jest.mock('sse.js', () => ({
  SSE: jest.fn(),
}));

jest.mock('@/api/lesson', () => ({
  resetChapter: jest.fn(),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  browserLanguage: 'en-US',
  default: {
    language: 'en-US',
    resolvedLanguage: 'en-US',
  },
}));

jest.mock('@/components/course-share', () => ({
  CourseShareButton: (props: MockCourseShareButtonProps) =>
    mockCourseShareButton(props),
}));

jest.mock('next/navigation', () => ({
  useParams: () => mockRouteParams,
}));

jest.mock('@/lib/urlUtils', () => ({
  buildCoursePageUrl: jest.fn(),
}));

describe('LearnerCourseShareButton', () => {
  const mockedBuildCoursePageUrl = buildCoursePageUrl as jest.MockedFunction<
    typeof buildCoursePageUrl
  >;

  beforeEach(() => {
    jest.clearAllMocks();
    mockRouteParams = { id: ['course-1'] };
    mockedBuildCoursePageUrl.mockReturnValue(
      'https://courses.example.com/c/course-1',
    );
    window.history.replaceState(
      {},
      '',
      '/c/course-1?lessonid=lesson-2&mode=listen#content-3',
    );
    act(() => {
      useEnvStore.setState({ courseId: 'course-1' });
      useSystemStore.setState({ previewMode: false });
      useCourseStore.setState({
        courseName: 'Course one',
        courseDescription: 'Course description',
        courseSettingsCourseId: 'course-1',
      });
    });
  });

  afterEach(() => {
    act(() => {
      useEnvStore.setState({ courseId: '' });
      useSystemStore.setState({ previewMode: false });
      useCourseStore.setState({
        courseName: '',
        courseDescription: '',
        courseSettingsCourseId: null,
      });
    });
  });

  it('binds the current learner course and resolves a clean course-root URL', () => {
    render(<LearnerCourseShareButton surface='learner_desktop_header' />);

    expect(screen.getByTestId('course-share-button')).toHaveAttribute(
      'data-surface',
      'learner_desktop_header',
    );
    expect(mockCourseShareButton).toHaveBeenCalledWith(
      expect.objectContaining({
        courseTitle: 'Course one',
        courseDescription: 'Course description',
        shifuBid: 'course-1',
        surface: 'learner_desktop_header',
      }),
    );

    const props = mockCourseShareButton.mock.calls[0]?.[0];
    expect(props.resolveShareUrl()).toBe(
      'https://courses.example.com/c/course-1',
    );
    expect(mockedBuildCoursePageUrl).toHaveBeenCalledWith(window.location.href);
  });

  it('does not expose sharing in preview mode', () => {
    act(() => {
      useSystemStore.setState({ previewMode: true });
    });

    render(<LearnerCourseShareButton surface='learner_mobile_header' />);

    expect(screen.queryByTestId('course-share-button')).not.toBeInTheDocument();
    expect(mockCourseShareButton).not.toHaveBeenCalled();
  });

  it('does not combine the previous course content with a newly selected course URL', () => {
    mockRouteParams = { id: ['course-2'] };

    render(<LearnerCourseShareButton surface='learner_mobile_header' />);

    expect(screen.queryByTestId('course-share-button')).not.toBeInTheDocument();
    expect(mockCourseShareButton).not.toHaveBeenCalled();
  });

  it('waits for course settings when the environment has switched courses', () => {
    act(() => {
      useEnvStore.setState({ courseId: 'course-2' });
    });

    render(<LearnerCourseShareButton surface='learner_mobile_header' />);

    expect(screen.queryByTestId('course-share-button')).not.toBeInTheDocument();
    expect(mockCourseShareButton).not.toHaveBeenCalled();
  });
});

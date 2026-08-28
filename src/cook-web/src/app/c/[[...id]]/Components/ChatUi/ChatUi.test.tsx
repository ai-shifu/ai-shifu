import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { ChatUi } from './ChatUi';
import {
  FRAME_LAYOUT_MOBILE,
  FRAME_LAYOUT_PAD_INTENSIVE,
  FRAME_LAYOUT_PC,
} from '@/c-constants/uiConstants';

let mockFrameLayout = FRAME_LAYOUT_PC;
let mockPreviewMode = false;
let mockShowLearningModeToggle = false;
let mockLearningMode: 'read' | 'listen' | 'classroom' = 'read';
let mockChatComponentProps: Record<string, any> = {};

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('zustand/react/shallow', () => ({
  useShallow: (selector: unknown) => selector,
}));

jest.mock('next/dynamic', () => () => {
  function MockChatComponents(props: Record<string, any>) {
    mockChatComponentProps = props;
    return <div data-testid='chat-components' />;
  }

  return MockChatComponents;
});

jest.mock('@/c-store', () => ({
  useCourseStore: (selector: (state: any) => unknown) =>
    selector({
      courseAvatar: '',
      courseName: 'Test course',
    }),
  useUiLayoutStore: (selector: (state: any) => unknown) =>
    selector({ frameLayout: mockFrameLayout }),
}));

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: (selector: (state: any) => unknown) =>
    selector({
      learningMode: mockLearningMode,
      previewMode: mockPreviewMode,
      showLearningModeToggle: mockShowLearningModeToggle,
      skip: false,
      updateSkip: jest.fn(),
    }),
}));

jest.mock(
  '../CourseHeaderSummary',
  () =>
    function MockCourseHeaderSummary() {
      return <div data-testid='course-summary' />;
    },
);
jest.mock(
  '../LearningModeSwitch',
  () =>
    function MockLearningModeSwitch({ size }: { size?: string }) {
      return (
        <div
          data-testid='learning-mode-switch'
          data-size={size}
        />
      );
    },
);
jest.mock(
  '../LearnerCourseShareButton',
  () =>
    function MockLearnerCourseShareButton({ surface }: { surface: string }) {
      return (
        <button
          type='button'
          data-testid='course-share-button'
          data-surface={surface}
        />
      );
    },
);
jest.mock(
  '../PreviewHeaderBanner',
  () =>
    function MockPreviewHeaderBanner({ courseId, lessonId }: any) {
      return (
        <div
          data-testid='preview-header-banner'
          data-course-id={courseId}
          data-lesson-id={lessonId}
        />
      );
    },
);
jest.mock(
  '../LessonUpdateNotice',
  () =>
    function MockLessonUpdateNotice() {
      return <div />;
    },
);
jest.mock(
  '@/components/ui/MarkdownFlowLink',
  () =>
    function MockMarkdownFlowLink() {
      return <span />;
    },
);

const pdfAction = {
  lessonId: 'lesson-1',
  isFollowUpStreaming: false,
  isPreparing: false,
  onDownload: jest.fn(),
};

const createChatUi = (lessonId = 'lesson-1') => (
  <ChatUi
    courseId='course-1'
    chapterId='chapter-1'
    chapterUpdate={jest.fn()}
    getNextLessonId={jest.fn()}
    lessonId={lessonId}
    lessonStatus='completed'
    lessonTitle='Lesson one'
    lessonUpdate={jest.fn()}
    onGoChapter={jest.fn()}
    onPurchased={jest.fn()}
    updateSelectedLesson={jest.fn()}
  />
);

const renderChatUi = (lessonId = 'lesson-1') => render(createChatUi(lessonId));

describe('ChatUi lesson PDF action', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFrameLayout = FRAME_LAYOUT_PC;
    mockPreviewMode = false;
    mockShowLearningModeToggle = false;
    mockLearningMode = 'read';
    mockChatComponentProps = {};
  });

  it('keeps the action visible and disabled before the lesson content is ready', () => {
    renderChatUi();

    expect(
      screen.getByRole('button', {
        name: 'module.chat.lessonPdfDownload',
      }),
    ).toHaveAttribute('aria-disabled', 'true');
    expect(
      screen.queryByTestId('learning-mode-switch'),
    ).not.toBeInTheDocument();
  });

  it('keeps the disabled action visible before a lesson is selected', () => {
    renderChatUi('');

    expect(
      screen.getByRole('button', {
        name: 'module.chat.lessonPdfDownload',
      }),
    ).toHaveAttribute('aria-disabled', 'true');
  });

  it('shows the action in the desktop titlebar without requiring a mode switch', () => {
    renderChatUi();

    act(() => {
      mockChatComponentProps.onLessonPdfActionChange(pdfAction);
    });

    expect(
      screen.getByRole('button', {
        name: 'module.chat.lessonPdfDownload',
      }),
    ).toHaveAttribute('aria-disabled', 'false');
    expect(
      screen.queryByTestId('learning-mode-switch'),
    ).not.toBeInTheDocument();
  });

  it('orders share, lesson PDF, and learning mode actions in the desktop header', () => {
    mockShowLearningModeToggle = true;
    renderChatUi();

    const share = screen.getByTestId('course-share-button');
    const pdf = screen.getByRole('button', {
      name: 'module.chat.lessonPdfDownload',
    });
    const learningMode = screen.getByTestId('learning-mode-switch');
    const actions = Array.from(share.parentElement?.children ?? []);

    expect(share).toHaveAttribute('data-surface', 'learner_desktop_header');
    expect(actions).toEqual([share, pdf, learningMode]);
  });

  it.each(['read', 'listen', 'classroom'] as const)(
    'keeps the desktop share action available in %s mode',
    learningMode => {
      mockLearningMode = learningMode;

      renderChatUi();

      expect(screen.getByTestId('course-share-button')).toBeInTheDocument();
    },
  );

  it('does not render the action in the mobile layout', () => {
    mockFrameLayout = FRAME_LAYOUT_MOBILE;
    renderChatUi();

    act(() => {
      mockChatComponentProps.onLessonPdfActionChange(pdfAction);
    });

    expect(
      screen.queryByRole('button', {
        name: 'module.chat.lessonPdfDownload',
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('course-share-button')).not.toBeInTheDocument();
  });

  it('disables a stale action immediately when the lesson changes', () => {
    const { rerender } = renderChatUi();

    act(() => {
      mockChatComponentProps.onLessonPdfActionChange(pdfAction);
    });
    expect(
      screen.getByRole('button', {
        name: 'module.chat.lessonPdfDownload',
      }),
    ).toBeInTheDocument();

    rerender(createChatUi('lesson-2'));

    const button = screen.getByRole('button', {
      name: 'module.chat.lessonPdfDownload',
    });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(button);
    expect(pdfAction.onDownload).not.toHaveBeenCalled();

    act(() => {
      mockChatComponentProps.onLessonPdfActionChange({
        ...pdfAction,
        lessonId: 'lesson-2',
      });
    });
    expect(button).toHaveAttribute('aria-disabled', 'false');
    fireEvent.click(button);
    expect(pdfAction.onDownload).toHaveBeenCalledTimes(1);
  });

  it('uses the compact mode switch in narrow desktop layouts', () => {
    mockFrameLayout = FRAME_LAYOUT_PAD_INTENSIVE;
    mockShowLearningModeToggle = true;

    renderChatUi();

    expect(screen.getByTestId('learning-mode-switch')).toHaveAttribute(
      'data-size',
      'mobile',
    );
  });
});

describe('ChatUi runtime gate', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFrameLayout = FRAME_LAYOUT_PC;
    mockPreviewMode = false;
    mockShowLearningModeToggle = false;
    mockLearningMode = 'read';
    mockChatComponentProps = {};
  });

  it('keeps the lesson shell visible without mounting the chat runtime', () => {
    render(
      <ChatUi
        courseId='course-1'
        chapterId='chapter-1'
        chapterUpdate={jest.fn()}
        getNextLessonId={jest.fn()}
        lessonId='lesson-1'
        lessonUpdate={jest.fn()}
        onGoChapter={jest.fn()}
        onPurchased={jest.fn()}
        runtimeReady={false}
        updateSelectedLesson={jest.fn()}
      />,
    );

    expect(screen.getByTestId('course-summary')).toBeInTheDocument();
    const loadingStatus = screen.getByRole('status');
    expect(loadingStatus).toBe(screen.getByTestId('chat-runtime-placeholder'));
    expect(loadingStatus).toHaveAttribute('aria-busy', 'true');
    expect(loadingStatus).toHaveTextContent('module.chat.loading');
    expect(
      loadingStatus.querySelector('[aria-hidden="true"]'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('chat-components')).not.toBeInTheDocument();
  });
});

describe('ChatUi preview banner', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFrameLayout = FRAME_LAYOUT_PC;
    mockPreviewMode = false;
    mockShowLearningModeToggle = false;
    mockLearningMode = 'read';
    mockChatComponentProps = {};
  });

  it('does not render outside preview mode', () => {
    renderChatUi();

    expect(
      screen.queryByTestId('preview-header-banner'),
    ).not.toBeInTheDocument();
  });

  it('passes the current course and lesson to the preview banner', () => {
    mockPreviewMode = true;

    renderChatUi('lesson-2');

    expect(screen.getByTestId('preview-header-banner')).toHaveAttribute(
      'data-course-id',
      'course-1',
    );
    expect(screen.getByTestId('preview-header-banner')).toHaveAttribute(
      'data-lesson-id',
      'lesson-2',
    );
    expect(screen.queryByTestId('course-share-button')).not.toBeInTheDocument();
  });
});

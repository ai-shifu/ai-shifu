import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { ChatUi } from './ChatUi';
import {
  FRAME_LAYOUT_MOBILE,
  FRAME_LAYOUT_PAD_INTENSIVE,
  FRAME_LAYOUT_PC,
} from '@/c-constants/uiConstants';

let mockFrameLayout = FRAME_LAYOUT_PC;
let mockShowLearningModeToggle = false;
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
      learningMode: 'read',
      previewMode: false,
      showLearningModeToggle: mockShowLearningModeToggle,
      skip: false,
      updateSkip: jest.fn(),
    }),
}));

jest.mock(
  '../Settings/UserSettings',
  () =>
    function MockUserSettings() {
      return <div />;
    },
);
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
  '../PreviewHeaderBanner',
  () =>
    function MockPreviewHeaderBanner() {
      return <div />;
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
    chapterId='chapter-1'
    chapterUpdate={jest.fn()}
    getNextLessonId={jest.fn()}
    lessonId={lessonId}
    lessonStatus='completed'
    lessonTitle='Lesson one'
    lessonUpdate={jest.fn()}
    onGoChapter={jest.fn()}
    onPurchased={jest.fn()}
    showUserSettings={false}
    updateSelectedLesson={jest.fn()}
  />
);

const renderChatUi = (lessonId = 'lesson-1') => render(createChatUi(lessonId));

describe('ChatUi lesson PDF action', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFrameLayout = FRAME_LAYOUT_PC;
    mockShowLearningModeToggle = false;
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

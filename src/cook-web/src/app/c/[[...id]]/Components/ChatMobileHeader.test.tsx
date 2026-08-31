import React from 'react';
import { render, screen } from '@testing-library/react';

import { ChatMobileHeader } from './ChatMobileHeader';

let mockPreviewMode = false;
let mockShowLearningModeToggle = true;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('zustand/react/shallow', () => ({
  useShallow: (selector: unknown) => selector,
}));

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      previewMode: mockPreviewMode,
      showLearningModeToggle: mockShowLearningModeToggle,
    }),
}));

jest.mock('@/c-service/Shifu', () => ({
  shifu: {
    ControlTypes: {
      MOBILE_HEADER_ICON_POPOVER: 'mobile-header-icon-popover',
    },
    hasControl: () => false,
  },
}));

jest.mock('@/c-common/hooks/useDisclosure', () => ({
  useDisclosure: () => ({
    onOpen: jest.fn(),
    onClose: jest.fn(),
  }),
}));

jest.mock('./CourseHeaderSummary', () => ({
  __esModule: true,
  default: () => <div data-testid='course-summary' />,
}));

jest.mock('./LearningModeSwitch', () => ({
  __esModule: true,
  default: () => <div data-testid='learning-mode-switch' />,
}));

jest.mock('./LearnerCourseShareButton', () => ({
  __esModule: true,
  default: ({ surface }: { surface: string }) => (
    <button
      type='button'
      data-testid='course-share-button'
      data-surface={surface}
    />
  ),
}));

jest.mock('./PreviewHeaderBanner', () => ({
  __esModule: true,
  default: () => <div data-testid='preview-header-banner' />,
}));

jest.mock('./LessonUpdateNotice', () => ({
  __esModule: true,
  default: () => <div data-testid='lesson-update-notice' />,
}));

jest.mock('./MobileHeaderIconPopover', () => ({
  __esModule: true,
  default: () => <div />,
}));

const renderHeader = () =>
  render(
    <ChatMobileHeader
      className=''
      navOpen={false}
      onSettingClick={jest.fn()}
      iconPopoverPayload={undefined}
      courseId='course-1'
      chapterId='chapter-1'
      lessonId='lesson-1'
      lessonTitle='Lesson one'
    />,
  );

describe('ChatMobileHeader course share action', () => {
  beforeEach(() => {
    mockPreviewMode = false;
    mockShowLearningModeToggle = true;
  });

  it('orders learning mode, share, and catalog actions', () => {
    renderHeader();

    const learningMode = screen.getByTestId('learning-mode-switch');
    const share = screen.getByTestId('course-share-button');
    const catalog = screen.getByRole('button', {
      name: 'module.chat.openCatalog',
    });

    expect(share).toHaveAttribute('data-surface', 'learner_mobile_header');
    expect(Array.from(share.parentElement?.children ?? [])).toEqual([
      learningMode,
      share,
      catalog,
    ]);
  });

  it('hides the share action in preview mode', () => {
    mockPreviewMode = true;

    renderHeader();

    expect(screen.getByTestId('preview-header-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('course-share-button')).not.toBeInTheDocument();
  });
});

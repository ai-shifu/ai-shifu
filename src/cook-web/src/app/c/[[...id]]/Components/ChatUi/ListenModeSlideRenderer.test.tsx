import { render, screen } from '@testing-library/react';
import type React from 'react';
import ListenModeSlideRenderer from './ListenModeSlideRenderer';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('next/image', () => ({
  __esModule: true,
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      {...props}
      alt={props.alt ?? ''}
    />
  ),
}));

jest.mock('markdown-flow-ui/slide', () => ({
  Slide: () => <div data-testid='listen-slide' />,
}));

jest.mock('./useChatLogicHook', () => ({
  ChatContentItemType: {
    ASK: 'ask',
    CONTENT: 'content',
    ERROR: 'error',
    INTERACTION: 'interaction',
    LIKE_STATUS: 'likeStatus',
  },
}));

jest.mock('./AskBlock', () => ({
  __esModule: true,
  default: () => <div data-testid='ask-block' />,
}));

jest.mock('@/c-utils/lesson-feedback-interaction-defaults', () => ({
  lessonFeedbackInteractionDefaultValueOptions: {},
}));

jest.mock('@/c-utils/lesson-feedback-interaction', () => ({
  isLessonFeedbackInteractionContent: () => false,
}));

jest.mock('@/c-utils/system-interaction', () => ({
  isPaySystemInteractionContent: () => false,
}));

jest.mock('@/c-api/studyV2', () => ({
  SYS_INTERACTION_TYPE: {},
}));

const createChatRef = () =>
  ({
    current: document.createElement('div'),
  }) as React.RefObject<HTMLDivElement>;

describe('ListenModeSlideRenderer', () => {
  it('shows the audio preparation overlay while listen backfill is waiting', () => {
    render(
      <ListenModeSlideRenderer
        items={[]}
        mobileStyle={false}
        chatRef={createChatRef()}
        isPreparingAudio
      />,
    );

    expect(
      screen.getByText('module.chat.slideAudioBufferingWaitingForAudio'),
    ).toBeInTheDocument();
  });

  it('does not show the audio preparation text for normal loading', () => {
    render(
      <ListenModeSlideRenderer
        items={[]}
        mobileStyle={false}
        chatRef={createChatRef()}
        isLoading
      />,
    );

    expect(
      screen.queryByText('module.chat.slideAudioBufferingWaitingForAudio'),
    ).not.toBeInTheDocument();
  });
});

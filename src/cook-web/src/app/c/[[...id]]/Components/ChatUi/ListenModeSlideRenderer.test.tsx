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
  Slide: jest.fn(() => null),
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

const getMockSlide = () =>
  jest.requireMock('markdown-flow-ui/slide').Slide as jest.Mock;

describe('ListenModeSlideRenderer', () => {
  beforeEach(() => {
    getMockSlide().mockClear();
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
    expect(
      screen.getByRole('status', {
        name: 'module.chat.slideAudioBufferingLoadingAudio',
      }),
    ).toBeInTheDocument();
  });

  it('passes finalized stream segments to slide with the complete url', () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            is_speakable: true,
            audioTracks: [
              {
                position: 0,
                audioUrl: '/api/storage/default/tts-audio/complete.mp3',
                isAudioStreaming: false,
                audioSegments: [
                  {
                    segmentIndex: 0,
                    audioData: 'streamed-audio',
                    durationMs: 100,
                    isFinal: true,
                    position: 0,
                  },
                ],
              },
            ],
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | { elementList?: Array<Record<string, unknown>> }
      | undefined;
    const contentElement = slideProps?.elementList?.find(
      element => element.blockBid === 'content-1',
    );
    expect(contentElement?.audio_url).toBe(
      '/api/storage/default/tts-audio/complete.mp3',
    );
    expect(contentElement?.audio_segments).toEqual([
      expect.objectContaining({
        segment_index: 0,
        audio_data: 'streamed-audio',
        duration_ms: 100,
        is_final: true,
        position: 0,
      }),
    ]);
  });

  it('passes selected interaction user input to the slide during playback', () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            is_speakable: true,
          },
          {
            type: 'interaction',
            content: '?[%{{knowledge_level}} 完全不了解 | 略知一二 | 比较熟悉]',
            element_bid: 'interaction-1',
            is_renderable: false,
            user_input: '比较熟悉',
            readonly: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | { elementList?: Array<Record<string, unknown>> }
      | undefined;
    const interactionElement = slideProps?.elementList?.find(
      element => element.blockBid === 'interaction-1',
    );

    expect(interactionElement).toEqual(
      expect.objectContaining({
        type: 'interaction',
        user_input: '比较熟悉',
        readonly: true,
      }),
    );
  });
});

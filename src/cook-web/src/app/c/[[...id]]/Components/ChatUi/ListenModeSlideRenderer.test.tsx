import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type React from 'react';
import ListenModeSlideRenderer from './ListenModeSlideRenderer';
import {
  readListenPlaybackSpeedFromStorage,
  writeListenPlaybackSpeedToStorage,
} from './listenPlaybackSpeed';
import {
  isListenLessonFeedbackPromptReady,
  shouldDelayListenFeedbackPromptForTailInteraction,
} from './lessonFeedbackPromptState';

const mockIsLessonFeedbackInteractionContent = jest.fn(
  (content?: string) => content?.includes('lesson_feedback') ?? false,
);
const mockAskBlock = jest.fn(
  ({
    element_bid,
    isExpanded,
  }: {
    element_bid?: string;
    isExpanded?: boolean;
  }) => (
    <div
      data-element-bid={element_bid ?? ''}
      data-expanded={isExpanded ? 'true' : 'false'}
      data-testid='ask-block'
    />
  ),
);

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

jest.mock('markdown-flow-ui/slide', () => {
  const slideCustomActionContext = {
    currentElement: {
      blockBid: 'content-1',
      type: 'content',
    },
    currentIndex: 0,
    isActive: false,
    setActive: jest.fn(),
    toggleActive: jest.fn(),
  };

  return {
    Slide: jest.fn(
      (props: {
        playerCustomActions?:
          | React.ReactNode
          | ((context: typeof slideCustomActionContext) => React.ReactNode);
      }) => (
        <div data-testid='mock-slide'>
          <audio data-testid='slide-audio' />
          <div data-testid='slide-custom-actions'>
            {typeof props.playerCustomActions === 'function'
              ? props.playerCustomActions(slideCustomActionContext)
              : props.playerCustomActions}
          </div>
        </div>
      ),
    ),
  };
});

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
  default: (props: { element_bid?: string; isExpanded?: boolean }) =>
    mockAskBlock(props),
}));

jest.mock('@/c-utils/lesson-feedback-interaction-defaults', () => ({
  lessonFeedbackInteractionDefaultValueOptions: {},
}));

jest.mock('@/c-utils/lesson-feedback-interaction', () => ({
  isLessonFeedbackInteractionContent: (content?: string) =>
    mockIsLessonFeedbackInteractionContent(content),
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
    window.localStorage.clear();
    getMockSlide().mockClear();
    mockAskBlock.mockClear();
    mockIsLessonFeedbackInteractionContent.mockClear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
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

  it('keeps the mobile ask block mounted and collapsed after closing the listen panel', async () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            is_speakable: true,
          },
        ]}
        mobileStyle={true}
        chatRef={createChatRef()}
      />,
    );

    const askButton = screen.getByText('module.chat.ask').closest('button');

    expect(askButton).toBeTruthy();
    await act(async () => {
      fireEvent.click(askButton as HTMLButtonElement);
    });
    expect(screen.getByTestId('ask-block')).toHaveAttribute(
      'data-expanded',
      'true',
    );

    await act(async () => {
      fireEvent.click(askButton as HTMLButtonElement);
    });
    expect(screen.getByTestId('ask-block')).toHaveAttribute(
      'data-expanded',
      'false',
    );
    expect(screen.getByTestId('ask-block')).toHaveAttribute(
      'data-element-bid',
      'content-1',
    );
  });

  it('applies the stored course playback speed to slide audio', async () => {
    writeListenPlaybackSpeedToStorage('course-1', 1.5);

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            is_speakable: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        shifuBid='course-1'
      />,
    );

    const audioElement = screen.getByTestId('slide-audio') as HTMLAudioElement;

    await waitFor(() => {
      expect(audioElement.defaultPlaybackRate).toBe(1.5);
      expect(audioElement.playbackRate).toBe(1.5);
    });
  });

  it('uses an icon-only control for opening playback speed options', () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            is_speakable: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        shifuBid='course-1'
      />,
    );

    const speedButton = screen.getByRole('button', {
      name: 'module.chat.listenPlaybackSpeedAriaLabel',
    });

    expect(speedButton.querySelector('svg')).toBeInTheDocument();
    expect(speedButton).not.toHaveTextContent(/x/i);
  });

  it('uses fixed SVG icons instead of text nodes for playback speed options', async () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            is_speakable: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        shifuBid='course-1'
      />,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.chat.listenPlaybackSpeedAriaLabel',
      }),
    );

    for (const label of ['0.75x', '1x', '1.25x', '1.5x', '2x']) {
      const option = await screen.findByRole('radio', { name: label });

      expect(option.querySelector('img')).toBeInTheDocument();
      expect(option).not.toHaveTextContent(/x/i);
    }
  });

  it('updates current audio and local storage when selecting another playback speed', async () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            is_speakable: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        shifuBid='course-1'
      />,
    );

    const audioElement = screen.getByTestId('slide-audio') as HTMLAudioElement;

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.chat.listenPlaybackSpeedAriaLabel',
      }),
    );
    fireEvent.click(await screen.findByRole('radio', { name: '2x' }));

    await waitFor(() => {
      expect(audioElement.defaultPlaybackRate).toBe(2);
      expect(audioElement.playbackRate).toBe(2);
      expect(readListenPlaybackSpeedFromStorage('course-1')).toBe(2);
    });
  });

  it('keeps the current course playback speed for audio created after slide changes', async () => {
    writeListenPlaybackSpeedToStorage('course-1', 1.25);

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            is_speakable: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        shifuBid='course-1'
      />,
    );

    const newAudioElement = document.createElement('audio');
    await act(async () => {
      screen.getByTestId('mock-slide').appendChild(newAudioElement);
    });

    await waitFor(() => {
      expect(newAudioElement.defaultPlaybackRate).toBe(1.25);
      expect(newAudioElement.playbackRate).toBe(1.25);
    });
  });

  it('keeps lesson feedback pending until the trailing visible interaction settles', () => {
    expect(
      shouldDelayListenFeedbackPromptForTailInteraction({
        lastItemIsLessonFeedbackInteraction: true,
        markerStepCount: 3,
        currentStepIndex: 2,
        currentStepHasAudio: false,
        currentStepHasBlockingInteraction: false,
        currentStepElementType: 'interaction',
      }),
    ).toBe(true);

    expect(
      isListenLessonFeedbackPromptReady({
        lastItemIsLessonFeedbackInteraction: true,
        markerStepCount: 3,
        currentStepIndex: 2,
        isPlaybackSequenceActive: false,
        hasSettledTailInteraction: false,
      }),
    ).toBe(false);

    expect(
      isListenLessonFeedbackPromptReady({
        lastItemIsLessonFeedbackInteraction: true,
        markerStepCount: 3,
        currentStepIndex: 2,
        isPlaybackSequenceActive: false,
        hasSettledTailInteraction: true,
      }),
    ).toBe(true);
  });
});

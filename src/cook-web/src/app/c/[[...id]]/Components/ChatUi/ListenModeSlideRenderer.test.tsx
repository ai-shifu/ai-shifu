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
import type { ChatContentItem } from '@/c-types/chatUi';

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
  isSystemInteractionContent: (content?: string) =>
    content?.includes('_sys_') ?? false,
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

const originalRequestFullscreen = HTMLElement.prototype.requestFullscreen;

describe('ListenModeSlideRenderer', () => {
  beforeEach(() => {
    window.localStorage.clear();
    getMockSlide().mockClear();
    mockAskBlock.mockClear();
    mockIsLessonFeedbackInteractionContent.mockClear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
    if (originalRequestFullscreen) {
      Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', {
        configurable: true,
        value: originalRequestFullscreen,
      });
    } else {
      delete (HTMLElement.prototype as Partial<HTMLElement>).requestFullscreen;
    }
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

  it('keeps the next lesson system interaction clickable when lesson feedback follows', () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Finished lesson',
            element_bid: 'content-1',
            is_speakable: true,
          },
          {
            type: 'interaction',
            content: '?[下一节//_sys_next_chapter]',
            element_bid: 'next-lesson',
            is_renderable: false,
            user_input: 'stale-system-value',
          },
          {
            type: 'interaction',
            content: '?[%{{lesson_feedback}} lesson_feedback]',
            element_bid: 'lesson-feedback',
            is_renderable: false,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | { elementList?: Array<Record<string, unknown>> }
      | undefined;
    const nextLessonElement = slideProps?.elementList?.find(
      element => element.blockBid === 'next-lesson',
    );

    expect(nextLessonElement).toEqual(
      expect.objectContaining({
        type: 'interaction',
        readonly: false,
        user_input: '',
      }),
    );
  });

  it('shows classroom paging tips on the empty title placeholder', () => {
    render(
      <ListenModeSlideRenderer
        variant='classroom'
        items={[]}
        mobileStyle={false}
        chatRef={createChatRef()}
        sectionTitle='Section title'
      />,
    );

    const classroomSlideProps = getMockSlide().mock.calls[0]?.[0] as
      | { elementList?: Array<Record<string, unknown>>; showPlayer?: boolean }
      | undefined;
    expect(classroomSlideProps?.elementList?.[0]?.blockBid).toBe('empty-ppt');
    expect(classroomSlideProps?.showPlayer).toBe(false);

    const { unmount: unmountClassroomPlaceholder } = render(
      classroomSlideProps?.elementList?.[0]?.content as React.ReactElement,
    );
    expect(screen.getByText('Section title')).toBeInTheDocument();
    expect(
      screen.getByText('module.chat.classroomTitlePlaceholderTips'),
    ).toBeInTheDocument();
    unmountClassroomPlaceholder();
  });

  it('does not prepend the classroom title placeholder once a slide is available', () => {
    render(
      <ListenModeSlideRenderer
        variant='classroom'
        items={[
          {
            type: 'content',
            content: '<section>First slide</section>',
            element_bid: 'first-slide',
            element_type: 'html',
            is_speakable: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        sectionTitle='Section title'
      />,
    );

    const classroomSlideProps = getMockSlide().mock.calls[0]?.[0] as
      | { elementList?: Array<Record<string, unknown>> }
      | undefined;
    expect(classroomSlideProps?.elementList).toHaveLength(1);
    expect(classroomSlideProps?.elementList?.[0]?.blockBid).toBe('first-slide');
  });

  it('keeps listen leading text placeholder without classroom tips', () => {
    const items: ChatContentItem[] = [
      {
        type: 'content',
        content: 'Opening narration',
        element_bid: 'intro-text',
        element_type: 'text',
        is_speakable: true,
      },
      {
        type: 'content',
        content: '<section>First slide</section>',
        element_bid: 'first-slide',
        element_type: 'html',
        is_speakable: true,
      },
    ];

    render(
      <ListenModeSlideRenderer
        items={items}
        mobileStyle={false}
        chatRef={createChatRef()}
        sectionTitle='Section title'
      />,
    );

    const listenSlideProps = getMockSlide().mock.calls[0]?.[0] as
      | { elementList?: Array<Record<string, unknown>> }
      | undefined;
    expect(listenSlideProps?.elementList?.[0]?.blockBid).toBe('empty-ppt');
    const { unmount: unmountListenPlaceholder } = render(
      listenSlideProps?.elementList?.[0]?.content as React.ReactElement,
    );
    expect(
      screen.queryByText('module.chat.classroomTitlePlaceholderTips'),
    ).not.toBeInTheDocument();
    unmountListenPlaceholder();
  });

  it('omits audio data and disables loading overlay in classroom mode', async () => {
    const requestFullscreen = jest
      .fn()
      .mockRejectedValue(new Error('fullscreen blocked'));
    Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    });

    render(
      <ListenModeSlideRenderer
        variant='classroom'
        items={[
          {
            type: 'content',
            content: 'Slide',
            element_bid: 'content-1',
            element_type: 'html',
            is_speakable: true,
            audio_url: '/tts.mp3',
            audio_segments: [
              {
                segment_index: 0,
                audio_data: 'abc',
                duration_ms: 100,
                is_final: true,
              },
            ],
            payload: {
              audio: {
                subtitle_cues: [
                  {
                    text: 'caption',
                    start_ms: 0,
                    end_ms: 100,
                  },
                ],
              },
            },
            ask_list: [
              {
                type: 'ask',
                content: '',
                element_bid: 'ask-1',
                anchor_element_bid: 'content-1',
              } as ChatContentItem & { anchor_element_bid: string },
            ],
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | {
          elementList?: Array<Record<string, unknown>>;
          playerCustomActions?: unknown;
          playerClassName?: string;
          className?: string;
          disableLoadingOverlay?: boolean;
          showPlayer?: boolean;
        }
      | undefined;
    const contentElement = slideProps?.elementList?.find(
      element => element.blockBid === 'content-1',
    );

    expect(contentElement).toEqual(
      expect.objectContaining({
        is_speakable: true,
        ask_list: expect.arrayContaining([
          expect.objectContaining({
            element_bid: 'ask-1',
          }),
        ]),
      }),
    );
    expect(contentElement).not.toHaveProperty('audio_url');
    expect(contentElement).not.toHaveProperty('audio_segments');
    expect(contentElement).not.toHaveProperty('subtitle_cues');
    expect(contentElement).not.toHaveProperty('is_audio_streaming');
    expect(contentElement).not.toHaveProperty('isAudioStreaming');
    expect(slideProps?.playerCustomActions).toBeNull();
    expect(slideProps?.disableLoadingOverlay).toBe(true);
    expect(slideProps?.showPlayer).toBe(true);
    expect(slideProps?.playerClassName ?? '').toContain(
      'classroom-slide-player',
    );
    expect(slideProps?.className ?? '').toContain('listen-slide-root');
    expect(slideProps?.className ?? '').not.toContain('classroom-slide-root');
    expect(
      screen.getByTestId('mock-slide').closest('.listen-reveal-wrapper'),
    ).not.toHaveClass('listen-reveal-wrapper--classroom');
    expect(
      screen.queryByRole('button', {
        name: 'module.chat.listenPlaybackSpeedAriaLabel',
      }),
    ).not.toBeInTheDocument();

    const fullscreenButton = await screen.findByRole('button', {
      name: 'module.chat.classroomEnterFullscreen',
    });
    expect(requestFullscreen).not.toHaveBeenCalled();

    fireEvent.click(fullscreenButton);

    await waitFor(() => {
      expect(requestFullscreen).toHaveBeenCalledTimes(1);
    });
  });

  it('maps classroom vertical page shortcuts to slide player navigation shortcuts', () => {
    const forwardedKeys: string[] = [];
    const handleForwardedShortcut = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        forwardedKeys.push(event.key);
      }
    };
    document.addEventListener('keydown', handleForwardedShortcut);

    try {
      render(
        <ListenModeSlideRenderer
          variant='classroom'
          items={[
            {
              type: 'content',
              content: 'Slide',
              element_bid: 'content-1',
              is_speakable: true,
            },
          ]}
          mobileStyle={false}
          chatRef={createChatRef()}
        />,
      );

      fireEvent.keyDown(document, { key: 'ArrowDown' });
      fireEvent.keyDown(document, { key: 'PageUp' });

      expect(forwardedKeys).toEqual(['ArrowRight', 'ArrowLeft']);
    } finally {
      document.removeEventListener('keydown', handleForwardedShortcut);
    }
  });

  it('keeps the classroom fullscreen entry aligned to the slide corner in preview', async () => {
    render(
      <ListenModeSlideRenderer
        variant='classroom'
        previewMode={true}
        items={[
          {
            type: 'content',
            content: 'Slide',
            element_bid: 'content-1',
            is_speakable: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
      />,
    );

    expect(
      await screen.findByRole('button', {
        name: 'module.chat.classroomEnterFullscreen',
      }),
    ).not.toHaveClass('classroom-fullscreen-button--preview');
  });

  it('maps classroom space shortcuts to next slide without bubbling the original space key', () => {
    const observedKeys: string[] = [];
    const handleKeyDown = (event: KeyboardEvent) => {
      observedKeys.push(event.key);
    };
    document.addEventListener('keydown', handleKeyDown);

    try {
      render(
        <ListenModeSlideRenderer
          variant='classroom'
          items={[
            {
              type: 'content',
              content: 'Slide',
              element_bid: 'content-1',
              is_speakable: true,
            },
          ]}
          mobileStyle={false}
          chatRef={createChatRef()}
        />,
      );

      fireEvent.keyDown(document, { code: 'Space', key: ' ' });

      expect(observedKeys).toEqual(['ArrowRight']);
    } finally {
      document.removeEventListener('keydown', handleKeyDown);
    }
  });

  it('does not map space shortcuts outside classroom mode', () => {
    const forwardedKeys: string[] = [];
    const handleForwardedShortcut = (event: KeyboardEvent) => {
      if (event.key === 'ArrowRight') {
        forwardedKeys.push(event.key);
      }
    };
    document.addEventListener('keydown', handleForwardedShortcut);

    try {
      render(
        <ListenModeSlideRenderer
          variant='listen'
          items={[
            {
              type: 'content',
              content: 'Slide',
              element_bid: 'content-1',
              is_speakable: true,
            },
          ]}
          mobileStyle={false}
          chatRef={createChatRef()}
        />,
      );

      fireEvent.keyDown(document, { code: 'Space', key: ' ' });

      expect(forwardedKeys).toEqual([]);
    } finally {
      document.removeEventListener('keydown', handleForwardedShortcut);
    }
  });

  it('does not map classroom space shortcuts from native interactive targets', async () => {
    const forwardedKeys: string[] = [];
    const handleForwardedShortcut = (event: KeyboardEvent) => {
      if (event.key === 'ArrowRight') {
        forwardedKeys.push(event.key);
      }
    };
    document.addEventListener('keydown', handleForwardedShortcut);

    try {
      render(
        <ListenModeSlideRenderer
          variant='classroom'
          items={[
            {
              type: 'content',
              content: 'Slide',
              element_bid: 'content-1',
              is_speakable: true,
            },
          ]}
          mobileStyle={false}
          chatRef={createChatRef()}
        />,
      );

      fireEvent.keyDown(
        await screen.findByRole('button', {
          name: 'module.chat.classroomEnterFullscreen',
        }),
        { code: 'Space', key: ' ' },
      );

      const input = document.createElement('input');
      document.body.append(input);
      try {
        fireEvent.keyDown(input, { code: 'Space', key: ' ' });
      } finally {
        input.remove();
      }

      expect(forwardedKeys).toEqual([]);
    } finally {
      document.removeEventListener('keydown', handleForwardedShortcut);
    }
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

  it('renders the current playback speed as text in the trigger control', () => {
    writeListenPlaybackSpeedToStorage('course-1', 2);

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

    expect(speedButton).toHaveTextContent('2x');
    expect(speedButton.querySelector('img')).not.toBeInTheDocument();
  });

  it('renders playback speed options as text labels', async () => {
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

      expect(option).toHaveTextContent(label);
      expect(option.querySelector('img')).not.toBeInTheDocument();
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

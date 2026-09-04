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
  readListenPlaybackPositionFromStorage,
  writeListenPlaybackPositionToStorage,
} from './listenPlaybackPosition';
import {
  isListenLessonFeedbackPromptReady,
  shouldDelayListenFeedbackPromptForTailInteraction,
} from './lessonFeedbackPromptState';
import type { ChatContentItem } from '@/c-types/chatUi';

const mockIsLessonFeedbackInteractionContent = jest.fn(
  (content?: string) => content?.includes('lesson_feedback') ?? false,
);
const mockTrackEvent = jest.fn();
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
let mockSlideMountId = 0;
let mockSlideAudioInitialReadyState: number | null = null;
let mockSlideAudioInitialDuration: number | null = null;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'zh-CN',
      resolvedLanguage: 'zh-CN',
    },
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    EVENT_NAMES: {
      LEARNER_LISTEN_TIMELINE_SEEK: 'learner_listen_timeline_seek',
    },
    trackEvent: mockTrackEvent,
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
  const ReactRuntime = jest.requireActual('react') as typeof React;
  const slideBuiltInActionClick = jest.fn();
  const slideCustomActionElement = {
    blockBid: 'content-1',
    type: 'content',
    audio_url: '',
  };
  type SlideCustomActionContext = {
    currentElement: typeof slideCustomActionElement;
    currentIndex: number;
    isActive: boolean;
    setActive: (active: boolean) => void;
    toggleActive: () => void;
  };

  return {
    mockSlideBuiltInActionClick: slideBuiltInActionClick,
    Slide: jest.fn(
      (props: {
        playerClassName?: string;
        fullscreenHeader?: { content?: React.ReactNode };
        onPlayerVisibilityChange?: (visible: boolean) => void;
        playerCustomActions?:
          | React.ReactNode
          | ((context: SlideCustomActionContext) => React.ReactNode);
        elementList?: Array<typeof slideCustomActionElement>;
        requestedStepIndex?: number;
      }) => {
        const [isActive, setIsActive] = ReactRuntime.useState(false);
        const currentElement =
          (typeof props.requestedStepIndex === 'number'
            ? props.elementList?.[props.requestedStepIndex]
            : undefined) ??
          props.elementList?.find(element => Boolean(element.audio_url)) ??
          props.elementList?.[0] ??
          slideCustomActionElement;
        const toggleActive = ReactRuntime.useCallback(() => {
          setIsActive(currentActive => !currentActive);
        }, []);
        const slideCustomActionContext = ReactRuntime.useMemo(
          () => ({
            currentElement,
            currentIndex: 0,
            isActive,
            setActive: setIsActive,
            toggleActive,
          }),
          [currentElement, isActive, toggleActive],
        );
        const mountId = ReactRuntime.useMemo(() => {
          mockSlideMountId += 1;
          return mockSlideMountId;
        }, []);

        return (
          <div
            data-testid='mock-slide'
            data-mount-id={mountId}
          >
            <audio
              data-testid='slide-audio'
              ref={audioElement => {
                if (!audioElement || mockSlideAudioInitialReadyState === null) {
                  return;
                }

                Object.defineProperty(audioElement, 'readyState', {
                  configurable: true,
                  value: mockSlideAudioInitialReadyState,
                });
                Object.defineProperty(audioElement, 'duration', {
                  configurable: true,
                  value: mockSlideAudioInitialDuration,
                });
              }}
              src={String(currentElement.audio_url ?? '')}
            />
            <button
              aria-hidden='true'
              aria-label='Notes'
              className='slide-player__action slide-player__action--active'
              onClick={slideBuiltInActionClick}
              tabIndex={-1}
              type='button'
            />
            <div data-testid='slide-custom-actions'>
              {typeof props.playerCustomActions === 'function'
                ? props.playerCustomActions(slideCustomActionContext)
                : props.playerCustomActions}
            </div>
          </div>
        );
      },
    ),
  };
});

const getClassTokens = (className?: string) =>
  (className ?? '').split(/\s+/).filter(Boolean);

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
  localizeSystemInteractionContent: (
    content: string,
    translate: (key: string) => string,
  ) =>
    content.replace(
      '?[' + 'Next//_sys_next_chapter]',
      `?[${translate('server.learn.nextChapterButton')}//_sys_next_chapter]`,
    ),
}));

jest.mock('@/c-api/studyV2', () => ({
  SYS_INTERACTION_TYPE: {},
}));

jest.mock('../LearnerCourseShareButton', () => ({
  __esModule: true,
  default: ({ surface }: { surface: string }) => (
    <button
      type='button'
      data-testid='course-share-button'
      data-surface={surface}
    />
  ),
}));

const createChatRef = () =>
  ({
    current: document.createElement('div'),
  }) as React.RefObject<HTMLDivElement>;

const getMockSlide = () =>
  jest.requireMock('markdown-flow-ui/slide').Slide as jest.Mock;

const getMockSlideBuiltInActionClick = () =>
  jest.requireMock('markdown-flow-ui/slide')
    .mockSlideBuiltInActionClick as jest.Mock;

const originalRequestFullscreen = HTMLElement.prototype.requestFullscreen;

describe('ListenModeSlideRenderer', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockSlideMountId = 0;
    mockSlideAudioInitialReadyState = null;
    mockSlideAudioInitialDuration = null;
    getMockSlide().mockClear();
    getMockSlideBuiltInActionClick().mockClear();
    mockAskBlock.mockClear();
    mockTrackEvent.mockClear();
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

    expect(screen.queryByText('module.chat.thinking')).not.toBeInTheDocument();
    expect(
      screen.getByRole('status', {
        name: 'module.chat.audioLoading',
      }),
    ).toBeInTheDocument();
  });

  it('relies on slide locale defaults for matching built-in copy', () => {
    render(
      <ListenModeSlideRenderer
        items={[]}
        mobileStyle={false}
        chatRef={createChatRef()}
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | {
          bufferingText?: Record<string, string>;
          fullscreenHeader?: { backAriaLabel?: string };
          interactionTexts?: Record<string, string>;
          locale?: string;
          playerTexts?: Record<string, string>;
        }
      | undefined;

    expect(slideProps?.locale).toBe('zh-CN');
    expect(slideProps?.bufferingText).toEqual({
      waitingForAudio: 'module.chat.thinking',
    });
    expect(slideProps?.interactionTexts).toEqual({
      title: 'module.chat.listenInteractionHint',
    });
    expect(slideProps?.fullscreenHeader).not.toHaveProperty('backAriaLabel');
    expect(slideProps).not.toHaveProperty('playerTexts');
  });

  it.each(['listen', 'classroom'] as const)(
    'keeps the course summary left and share action right in the mobile fullscreen %s header',
    variant => {
      render(
        <ListenModeSlideRenderer
          items={[]}
          mobileStyle
          chatRef={createChatRef()}
          courseName='Course one'
          sectionTitle='Lesson one'
          variant={variant}
        />,
      );

      const slideProps = getMockSlide().mock.calls[0]?.[0] as
        | { fullscreenHeader?: { content?: React.ReactNode } }
        | undefined;
      render(<>{slideProps?.fullscreenHeader?.content}</>);

      const share = screen.getByTestId('course-share-button');
      const headerRow = share.parentElement;

      expect(screen.getByText('Course one')).toBeInTheDocument();
      expect(screen.getByText('Lesson one')).toBeInTheDocument();
      expect(share).toHaveAttribute(
        'data-surface',
        'learner_mobile_fullscreen',
      );
      expect(headerRow?.lastElementChild).toBe(share);
      expect(headerRow?.firstElementChild).toContainElement(
        screen.getByText('Course one'),
      );
    },
  );

  it('hides the mobile fullscreen share action in preview mode', () => {
    render(
      <ListenModeSlideRenderer
        items={[]}
        mobileStyle
        chatRef={createChatRef()}
        courseName='Course preview'
        sectionTitle='Lesson preview'
        previewMode
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | { fullscreenHeader?: { content?: React.ReactNode } }
      | undefined;
    render(<>{slideProps?.fullscreenHeader?.content}</>);

    expect(screen.getByText('Course preview')).toBeInTheDocument();
    expect(screen.queryByTestId('course-share-button')).not.toBeInTheDocument();
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

  it('passes a stable listen player class for footer-safe positioning', () => {
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
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | { playerClassName?: string }
      | undefined;

    const playerClassTokens = getClassTokens(slideProps?.playerClassName);

    expect(playerClassTokens).toContain('listen-slide-player');
    expect(playerClassTokens).not.toContain('classroom-slide-player');
  });

  it('keeps the desktop ask overlay above reserved player space when controls hide', async () => {
    const onPlayerVisibilityChange = jest.fn();
    const { container } = render(
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
        onPlayerVisibilityChange={onPlayerVisibilityChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'module.chat.ask' }));

    await waitFor(() => {
      expect(screen.getByTestId('ask-block')).toHaveAttribute(
        'data-expanded',
        'true',
      );
    });

    const askOverlay = container.querySelector('.slide-ask-overlay');
    expect(askOverlay).toHaveClass('slide-ask-overlay--with-player');
    expect(askOverlay).not.toHaveClass('slide-ask-overlay--standalone');

    const slideCalls = getMockSlide().mock.calls;
    const slideProps = slideCalls[slideCalls.length - 1]?.[0] as
      | { onPlayerVisibilityChange?: (visible: boolean) => void }
      | undefined;

    act(() => {
      slideProps?.onPlayerVisibilityChange?.(false);
    });

    expect(onPlayerVisibilityChange).toHaveBeenLastCalledWith(false);
    expect(askOverlay).toHaveClass('slide-ask-overlay--with-player');
    expect(askOverlay).not.toHaveClass('slide-ask-overlay--standalone');
  });

  it('keeps the mobile slide layout reserved when controls hide', () => {
    const onPlayerVisibilityChange = jest.fn();
    const { container } = render(
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
        onPlayerVisibilityChange={onPlayerVisibilityChange}
      />,
    );

    const revealWrapper = container.querySelector('.listen-reveal-wrapper');
    expect(revealWrapper).toHaveClass('listen-reveal-wrapper--with-player');

    const slideCalls = getMockSlide().mock.calls;
    const slideProps = slideCalls[slideCalls.length - 1]?.[0] as
      | { onPlayerVisibilityChange?: (visible: boolean) => void }
      | undefined;

    act(() => {
      slideProps?.onPlayerVisibilityChange?.(false);
    });

    expect(onPlayerVisibilityChange).toHaveBeenLastCalledWith(false);
    expect(revealWrapper).toHaveClass('listen-reveal-wrapper--with-player');
  });

  it('does not reserve player layout for an empty disabled slide', () => {
    const { container } = render(
      <ListenModeSlideRenderer
        items={[]}
        mobileStyle={false}
        chatRef={createChatRef()}
      />,
    );

    expect(container.querySelector('.listen-reveal-wrapper')).not.toHaveClass(
      'listen-reveal-wrapper--with-player',
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | { playerEnabled?: boolean }
      | undefined;
    expect(slideProps?.playerEnabled).toBe(false);
  });

  it('delegates desktop ask activation without clicking built-in player actions', async () => {
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
      />,
    );

    const askButton = screen.getByRole('button', {
      name: 'module.chat.ask',
    });
    fireEvent.click(askButton);

    await waitFor(() => {
      expect(askButton).toHaveAttribute('aria-pressed', 'true');
    });
    expect(getMockSlideBuiltInActionClick()).not.toHaveBeenCalled();
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
        readonly: false,
      }),
    );
  });

  it('keeps a resolved interaction stable when feedback narration is appended', () => {
    const chatRef = createChatRef();
    const baseItems: ChatContentItem[] = [
      {
        type: 'content',
        content: 'Hello',
        element_bid: 'content-1',
        is_speakable: true,
      },
      {
        type: 'interaction',
        content: '?[1945 年 | 1946 年 | 1947 年]',
        element_bid: 'interaction-1',
        is_renderable: false,
      },
    ];

    const { rerender } = render(
      <ListenModeSlideRenderer
        items={baseItems}
        mobileStyle={false}
        chatRef={chatRef}
      />,
    );

    rerender(
      <ListenModeSlideRenderer
        items={[
          baseItems[0],
          {
            ...baseItems[1],
            user_input: '1946 年',
          },
        ]}
        mobileStyle={false}
        chatRef={chatRef}
      />,
    );

    const resolvedSlideProps = getMockSlide().mock.calls.at(-1)?.[0] as
      | { elementList?: Array<Record<string, unknown>> }
      | undefined;
    const resolvedInteraction = resolvedSlideProps?.elementList?.find(
      element => element.blockBid === 'interaction-1',
    );

    rerender(
      <ListenModeSlideRenderer
        items={[
          baseItems[0],
          {
            ...baseItems[1],
            user_input: '1946 年',
          },
          {
            type: 'content',
            content: '答对了，继续看下一个坑。',
            element_bid: 'feedback-answer-1',
            generated_block_bid: 'feedback-generated-1',
            is_speakable: true,
            audioUrl: '/feedback.mp3',
          },
        ]}
        mobileStyle={false}
        chatRef={chatRef}
      />,
    );

    const appendedSlideProps = getMockSlide().mock.calls.at(-1)?.[0] as
      | { elementList?: Array<Record<string, unknown>> }
      | undefined;
    const appendedInteraction = appendedSlideProps?.elementList?.find(
      element => element.blockBid === 'interaction-1',
    );
    const feedbackElement = appendedSlideProps?.elementList?.find(
      element => element.blockBid === 'feedback-answer-1',
    );

    expect(appendedInteraction).toBe(resolvedInteraction);
    expect(feedbackElement).toEqual(
      expect.objectContaining({
        type: 'text',
        audio_url: '/feedback.mp3',
      }),
    );
  });

  it('keeps resolved button-and-input interactions editable and forwards reselection', () => {
    const onSend = jest.fn();
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
            content: '?[%{{nickname}} 老师 || 同学 || ...怎么称呼你？]',
            element_bid: 'nickname-1',
            user_input: '老师, 小王',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        onSend={onSend}
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | {
          elementList?: Array<Record<string, unknown>>;
          onSend?: (
            content: Record<string, unknown>,
            element?: Record<string, unknown>,
          ) => void;
        }
      | undefined;
    const interactionElement = slideProps?.elementList?.find(
      element => element.blockBid === 'nickname-1',
    );

    expect(interactionElement).toEqual(
      expect.objectContaining({
        type: 'interaction',
        user_input: '老师, 小王',
        readonly: false,
      }),
    );

    act(() => {
      slideProps?.onSend?.(
        {
          variableName: 'nickname',
          selectedValues: ['同学'],
          inputText: '小李',
        },
        interactionElement,
      );
    });

    expect(onSend).toHaveBeenCalledWith(
      {
        variableName: 'nickname',
        selectedValues: ['同学'],
        inputText: '小李',
      },
      'nickname-1',
    );
  });

  it('keeps resolved interactions visually locked while output is in progress', () => {
    const onSend = jest.fn();
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
            content: '?[%{{nickname}} 老师 || 同学 || ...怎么称呼你？]',
            element_bid: 'nickname-1',
            user_input: '老师, 小王',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        onSend={onSend}
        disableInteractionEdits={true}
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | {
          elementList?: Array<Record<string, unknown>>;
          onSend?: (
            content: Record<string, unknown>,
            element?: Record<string, unknown>,
          ) => void;
        }
      | undefined;
    const interactionElement = slideProps?.elementList?.find(
      element => element.blockBid === 'nickname-1',
    );

    expect(interactionElement).toEqual(
      expect.objectContaining({
        type: 'interaction',
        user_input: '老师, 小王',
        readonly: true,
      }),
    );

    act(() => {
      slideProps?.onSend?.(
        {
          variableName: 'nickname',
          selectedValues: ['同学'],
          inputText: '小李',
        },
        interactionElement,
      );
    });

    expect(onSend).not.toHaveBeenCalled();
  });

  it('passes a variable-free ellipsis interaction through to the slide unchanged', () => {
    // markdown-flow-ui >= 0.2.8 (remark-flow >= 1.2.0) parses variable-free
    // text-input interactions natively; no host-side rewrite is needed.
    const onSend = jest.fn();
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
            content: '?[...你叫什么名字]',
            element_bid: 'anonymous-input',
            user_input: '小明',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        onSend={onSend}
      />,
    );

    const slideProps = getMockSlide().mock.calls[0]?.[0] as
      | {
          elementList?: Array<Record<string, unknown>>;
          onSend?: (
            content: Record<string, unknown>,
            element?: Record<string, unknown>,
          ) => void;
        }
      | undefined;
    const interactionElement = slideProps?.elementList?.find(
      element => element.blockBid === 'anonymous-input',
    );

    expect(interactionElement).toEqual(
      expect.objectContaining({
        content: '?[...你叫什么名字]',
        user_input: '小明',
      }),
    );

    act(() => {
      slideProps?.onSend?.(
        { variableName: '', inputText: '小红' },
        interactionElement,
      );
    });

    expect(onSend).toHaveBeenCalledWith(
      { variableName: '', inputText: '小红' },
      'anonymous-input',
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

  it('pauses listen playback when the regenerate confirm dialog is open', () => {
    const container = document.createElement('div');
    const audio = document.createElement('audio');
    const pauseSpy = jest.spyOn(audio, 'pause').mockImplementation(() => {});
    Object.defineProperty(audio, 'paused', {
      configurable: true,
      get: () => false,
    });
    container.append(audio);

    render(
      <ListenModeSlideRenderer
        items={[]}
        mobileStyle={false}
        chatRef={{ current: container }}
        pausePlaybackWhen={true}
      />,
    );

    expect(pauseSpy).toHaveBeenCalled();
  });

  it('refreshes the empty title placeholder when the section title changes', () => {
    // The placeholder renders its title inside a React node and always carries
    // the same blockBid, so the slide reuse cache used to hand back the previous
    // lesson's placeholder after switching lessons.
    const { rerender } = render(
      <ListenModeSlideRenderer
        items={[]}
        mobileStyle={false}
        chatRef={createChatRef()}
        sectionTitle='First lesson'
      />,
    );

    rerender(
      <ListenModeSlideRenderer
        items={[]}
        mobileStyle={false}
        chatRef={createChatRef()}
        sectionTitle='Second lesson'
      />,
    );

    const slideCalls = getMockSlide().mock.calls;
    const latestSlideProps = slideCalls[slideCalls.length - 1]?.[0] as
      | { elementList?: Array<Record<string, unknown>> }
      | undefined;

    const { unmount } = render(
      latestSlideProps?.elementList?.[0]?.content as React.ReactElement,
    );
    expect(screen.getByText('Second lesson')).toBeInTheDocument();
    expect(screen.queryByText('First lesson')).not.toBeInTheDocument();
    unmount();
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
      | {
          elementList?: Array<Record<string, unknown>>;
          playerEnabled?: boolean;
        }
      | undefined;
    expect(classroomSlideProps?.elementList?.[0]?.blockBid).toBe('empty-ppt');
    expect(classroomSlideProps?.playerEnabled).toBe(false);

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
          playerEnabled?: boolean;
          locale?: string;
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
    expect(slideProps?.playerEnabled).toBe(true);
    expect(slideProps?.locale).toBe('zh-CN');
    const playerClassTokens = getClassTokens(slideProps?.playerClassName);

    expect(playerClassTokens).toContain('classroom-slide-player');
    expect(playerClassTokens).not.toContain('listen-slide-player');
    expect(slideProps?.className ?? '').toContain('listen-slide-root');
    expect(slideProps?.className ?? '').not.toContain('classroom-slide-root');
    expect(
      screen.getByTestId('mock-slide').closest('.listen-reveal-wrapper'),
    ).toHaveClass('listen-reveal-wrapper--classroom');
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
    expect(askButton).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('ask-block')).toHaveAttribute(
      'data-expanded',
      'true',
    );

    await act(async () => {
      fireEvent.click(askButton as HTMLButtonElement);
    });
    expect(askButton).toHaveAttribute('aria-pressed', 'false');
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

  it('restores a saved finalized audio position after metadata without starting playback', async () => {
    writeListenPlaybackPositionToStorage({
      scope: {
        courseId: 'course-1',
        lessonId: 'lesson-1',
        elementBid: 'content-1',
        source: 'https://audio.example.com/content-1.mp3',
      },
      positionSeconds: 24,
      durationSeconds: 60,
    });

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            audio_url: 'https://audio.example.com/content-1.mp3',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        lessonId='lesson-1'
        shifuBid='course-1'
      />,
    );

    const audioElement = screen.getByTestId('slide-audio') as HTMLAudioElement;
    Object.defineProperty(audioElement, 'duration', {
      configurable: true,
      value: 60,
    });
    const playSpy = jest.spyOn(audioElement, 'play');

    fireEvent.loadedMetadata(audioElement);

    await waitFor(() => {
      expect(audioElement.currentTime).toBe(24);
      expect(playSpy).not.toHaveBeenCalled();
      expect(
        screen.getByRole('slider', {
          name: 'module.chat.listenPlaybackTimelineAriaLabel',
        }),
      ).toBeInTheDocument();
    });
  });

  it('restores the position for the audio source selected after the first slide', async () => {
    writeListenPlaybackPositionToStorage({
      scope: {
        courseId: 'course-1',
        lessonId: 'lesson-1',
        elementBid: 'content-1',
        source: 'https://audio.example.com/content-1.mp3',
      },
      positionSeconds: 12,
      durationSeconds: 60,
    });
    writeListenPlaybackPositionToStorage({
      scope: {
        courseId: 'course-1',
        lessonId: 'lesson-1',
        elementBid: 'content-2',
        source: 'https://audio.example.com/content-2.mp3',
      },
      positionSeconds: 36,
      durationSeconds: 60,
    });

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'First',
            element_bid: 'content-1',
            audio_url: 'https://audio.example.com/content-1.mp3',
          },
          {
            type: 'content',
            content: 'Second',
            element_bid: 'content-2',
            audio_url: 'https://audio.example.com/content-2.mp3',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        lessonId='lesson-1'
        shifuBid='course-1'
      />,
    );

    const audioElement = screen.getByTestId('slide-audio') as HTMLAudioElement;
    Object.defineProperty(audioElement, 'duration', {
      configurable: true,
      value: 60,
    });
    audioElement.src = 'https://audio.example.com/content-2.mp3';
    fireEvent.loadedMetadata(audioElement);

    await waitFor(() => {
      expect(audioElement.currentTime).toBe(36);
    });
  });

  it('returns to the last resumable audio in a lesson before restoring its position', async () => {
    writeListenPlaybackPositionToStorage({
      scope: {
        courseId: 'course-1',
        lessonId: 'lesson-1',
        elementBid: 'content-2',
        source: 'https://audio.example.com/content-2.mp3',
      },
      positionSeconds: 36,
      durationSeconds: 60,
    });

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'First',
            element_bid: 'content-1',
            audio_url: 'https://audio.example.com/content-1.mp3',
          },
          {
            type: 'content',
            content: 'Second',
            element_bid: 'content-2',
            audio_url: 'https://audio.example.com/content-2.mp3',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        lessonId='lesson-1'
        shifuBid='course-1'
      />,
    );

    const audioElement = await screen.findByTestId('slide-audio');
    await waitFor(() => {
      expect(audioElement).toHaveAttribute(
        'src',
        'https://audio.example.com/content-2.mp3',
      );
    });
    Object.defineProperty(audioElement, 'duration', {
      configurable: true,
      value: 60,
    });
    fireEvent.loadedMetadata(audioElement);

    await waitFor(() => {
      expect((audioElement as HTMLAudioElement).currentTime).toBe(36);
    });
  });

  it('restores cached metadata that loaded before the audio listener registered', async () => {
    writeListenPlaybackPositionToStorage({
      scope: {
        courseId: 'course-1',
        lessonId: 'lesson-1',
        elementBid: 'content-1',
        source: 'https://audio.example.com/content-1.mp3',
      },
      positionSeconds: 24,
      durationSeconds: 60,
    });
    mockSlideAudioInitialReadyState = HTMLMediaElement.HAVE_METADATA;
    mockSlideAudioInitialDuration = 60;

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            audio_url: 'https://audio.example.com/content-1.mp3',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        lessonId='lesson-1'
        shifuBid='course-1'
      />,
    );

    await waitFor(() => {
      expect(
        (screen.getByTestId('slide-audio') as HTMLAudioElement).currentTime,
      ).toBe(24);
    });
  });

  it('removes the timeline when its active audio element is removed', async () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            audio_url: 'https://audio.example.com/content-1.mp3',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        lessonId='lesson-1'
        shifuBid='course-1'
      />,
    );

    const audioElement = screen.getByTestId('slide-audio') as HTMLAudioElement;
    Object.defineProperty(audioElement, 'duration', {
      configurable: true,
      value: 60,
    });
    fireEvent.loadedMetadata(audioElement);
    expect(await screen.findByRole('slider')).toBeInTheDocument();

    audioElement.remove();

    await waitFor(() => {
      expect(screen.queryByRole('slider')).not.toBeInTheDocument();
    });
  });

  it('persists an accepted timeline seek and records the surface without audio details', async () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            audio_url: 'https://audio.example.com/content-1.mp3',
          },
        ]}
        mobileStyle={true}
        chatRef={createChatRef()}
        lessonId='lesson-1'
        shifuBid='course-1'
      />,
    );

    const audioElement = screen.getByTestId('slide-audio') as HTMLAudioElement;
    Object.defineProperty(audioElement, 'duration', {
      configurable: true,
      value: 60,
    });
    fireEvent.loadedMetadata(audioElement);

    const timeline = await screen.findByRole('slider', {
      name: 'module.chat.listenPlaybackTimelineAriaLabel',
    });
    audioElement.currentTime = 12;
    fireEvent.timeUpdate(audioElement);
    expect(timeline).toHaveValue('12');

    fireEvent.pointerDown(timeline);
    fireEvent.change(timeline, { target: { value: '30' } });
    fireEvent.pointerUp(timeline);

    await waitFor(() => {
      expect(audioElement.currentTime).toBe(30);
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_listen_timeline_seek',
        { surface: 'learner_mobile' },
      );
      expect(
        readListenPlaybackPositionFromStorage({
          courseId: 'course-1',
          lessonId: 'lesson-1',
          elementBid: 'content-1',
          source: 'https://audio.example.com/content-1.mp3',
        }),
      ).toBe(30);
    });
  });

  it('keeps timeline seeking functional when analytics tracking fails', async () => {
    mockTrackEvent.mockRejectedValueOnce(new Error('tracking unavailable'));

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            audio_url: 'https://audio.example.com/content-1.mp3',
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        lessonId='lesson-1'
        shifuBid='course-1'
      />,
    );

    const audioElement = screen.getByTestId('slide-audio') as HTMLAudioElement;
    Object.defineProperty(audioElement, 'duration', {
      configurable: true,
      value: 60,
    });
    fireEvent.loadedMetadata(audioElement);

    const timeline = await screen.findByRole('slider');
    fireEvent.pointerDown(timeline);
    fireEvent.change(timeline, { target: { value: '30' } });
    fireEvent.pointerUp(timeline);

    await waitFor(() => {
      expect(audioElement.currentTime).toBe(30);
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    });
  });

  it('does not show a timeline or emit events for streaming audio', () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Hello',
            element_bid: 'content-1',
            audio_url: 'https://audio.example.com/content-1.mp3',
            isAudioStreaming: true,
          },
        ]}
        mobileStyle={false}
        chatRef={createChatRef()}
        lessonId='lesson-1'
        shifuBid='course-1'
      />,
    );

    const audioElement = screen.getByTestId('slide-audio') as HTMLAudioElement;
    Object.defineProperty(audioElement, 'duration', {
      configurable: true,
      value: 60,
    });
    fireEvent.loadedMetadata(audioElement);

    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalled();
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

  it('refreshes mobile interaction elements on viewport orientation changes without remounting the slide', async () => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      value: 390,
    });
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      value: 844,
    });

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Slide',
            element_bid: 'content-1',
            element_type: 'html',
          },
          {
            type: 'interaction',
            content: '?[A | B]',
            element_bid: 'interaction-1',
          },
        ]}
        mobileStyle={true}
        chatRef={createChatRef()}
        lessonId='lesson-1'
      />,
    );

    const initialSlideProps = getMockSlide().mock.calls.at(-1)?.[0] as
      | {
          elementList?: Array<{ type?: string; content?: unknown }>;
        }
      | undefined;
    const initialInteractionElement = initialSlideProps?.elementList?.find(
      element => element.type === 'interaction',
    );
    const initialMountId = screen
      .getByTestId('mock-slide')
      .getAttribute('data-mount-id');

    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      value: 844,
    });
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      value: 390,
    });

    act(() => {
      window.dispatchEvent(new Event('orientationchange'));
    });

    await waitFor(() => {
      const nextSlideProps = getMockSlide().mock.calls.at(-1)?.[0] as
        | {
            elementList?: Array<{ type?: string; content?: unknown }>;
          }
        | undefined;
      const nextInteractionElement = nextSlideProps?.elementList?.find(
        element => element.type === 'interaction',
      );

      expect(screen.getByTestId('mock-slide')).toHaveAttribute(
        'data-mount-id',
        initialMountId ?? '',
      );
      expect(nextInteractionElement).not.toBe(initialInteractionElement);
      expect(nextInteractionElement?.content).toBe('?[A | B]');
    });
  });

  it('refreshes mobile interaction elements when orientation events fire before viewport dimensions settle', async () => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      value: 390,
    });
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      value: 844,
    });

    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Slide',
            element_bid: 'content-1',
            element_type: 'html',
          },
          {
            type: 'interaction',
            content: '?[A | B]',
            element_bid: 'interaction-1',
          },
        ]}
        mobileStyle={true}
        chatRef={createChatRef()}
        lessonId='lesson-1'
      />,
    );

    const initialSlideProps = getMockSlide().mock.calls.at(-1)?.[0] as
      | {
          elementList?: Array<{ type?: string; content?: unknown }>;
        }
      | undefined;
    const initialInteractionElement = initialSlideProps?.elementList?.find(
      element => element.type === 'interaction',
    );
    const initialMountId = screen
      .getByTestId('mock-slide')
      .getAttribute('data-mount-id');

    act(() => {
      window.dispatchEvent(new Event('orientationchange'));
    });

    await waitFor(() => {
      const nextSlideProps = getMockSlide().mock.calls.at(-1)?.[0] as
        | {
            elementList?: Array<{ type?: string; content?: unknown }>;
          }
        | undefined;
      const nextInteractionElement = nextSlideProps?.elementList?.find(
        element => element.type === 'interaction',
      );

      expect(screen.getByTestId('mock-slide')).toHaveAttribute(
        'data-mount-id',
        initialMountId ?? '',
      );
      expect(nextInteractionElement).not.toBe(initialInteractionElement);
      expect(nextInteractionElement?.content).toBe('?[A | B]');
    });
  });

  it('refreshes mobile interaction elements without remounting the slide for manual view mode changes', async () => {
    render(
      <ListenModeSlideRenderer
        items={[
          {
            type: 'content',
            content: 'Slide',
            element_bid: 'content-1',
            element_type: 'html',
          },
          {
            type: 'interaction',
            content: '?[A | B]',
            element_bid: 'interaction-1',
          },
        ]}
        mobileStyle={true}
        chatRef={createChatRef()}
        lessonId='lesson-1'
      />,
    );

    const initialMountId = screen
      .getByTestId('mock-slide')
      .getAttribute('data-mount-id');
    const initialSlideProps = getMockSlide().mock.calls.at(-1)?.[0] as
      | {
          elementList?: Array<{ type?: string; content?: unknown }>;
        }
      | undefined;
    const initialInteractionElement = initialSlideProps?.elementList?.find(
      element => element.type === 'interaction',
    );
    const slideProps = getMockSlide().mock.calls.at(-1)?.[0] as
      | {
          onMobileViewModeChange?: (viewMode: 'fullscreen') => void;
        }
      | undefined;

    act(() => {
      slideProps?.onMobileViewModeChange?.('fullscreen');
    });

    await waitFor(() => {
      const nextSlideProps = getMockSlide().mock.calls.at(-1)?.[0] as
        | {
            elementList?: Array<{ type?: string; content?: unknown }>;
          }
        | undefined;
      const nextInteractionElement = nextSlideProps?.elementList?.find(
        element => element.type === 'interaction',
      );

      expect(screen.getByTestId('mock-slide')).toHaveAttribute(
        'data-mount-id',
        initialMountId ?? '',
      );
      expect(nextInteractionElement).not.toBe(initialInteractionElement);
      expect(nextInteractionElement?.content).toBe('?[A | B]');
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

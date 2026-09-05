import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import AskBlock from './AskBlock';
import { AppContext } from '../AppContext';
import { BLOCK_TYPE, SSE_OUTPUT_TYPE } from '@/api/studyV2';
import { toast, toastOnce } from '@/hooks/useToast';
import { useAskStateStore } from './useAskStateStore';
import { mockLiveVoiceController } from '@/components/live-follow-up/liveVoiceFollowUp.test-support';

const mockTrackEvent = jest.fn();
let mockLanguage = 'zh-CN';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: mockLanguage,
      resolvedLanguage: mockLanguage,
    },
  }),
}));

jest.mock('i18next', () => ({
  t: (key: string) => key,
}));

// Production embeds locale metadata through Next config; Jest has no build env.
jest.mock('@/lib/i18n-locales', () => ({
  isRtlLocale: (locale: string) => locale === 'ar-SA',
}));

jest.mock('@/lib/markdownUtils', () => ({
  fixMarkdownStream: (_previous: string, delta: string) => delta,
}));

jest.mock('markdown-flow-ui/renderer', () => ({
  ContentRender: ({
    content,
    enableTypewriter,
    typewriterPacing,
    typingSpeed,
  }: {
    content: string;
    enableTypewriter?: boolean;
    typewriterPacing?: 'fixed' | 'content-aware';
    typingSpeed?: number;
  }) => (
    <div
      data-testid='follow-up-answer'
      data-typewriter={String(Boolean(enableTypewriter))}
      data-typewriter-pacing={typewriterPacing}
      data-typing-speed={typingSpeed}
    >
      {content}
    </div>
  ),
  MarkdownFlowInput: ({
    value,
    onChange,
    onSend,
    sendShortcut,
    textareaClassName,
  }: {
    value: string;
    onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
    onSend: () => void;
    sendShortcut?: 'enter' | 'none';
    textareaClassName?: string;
  }) => (
    <div
      data-testid='ask-input-wrapper'
      data-send-shortcut={sendShortcut}
    >
      <textarea
        aria-label='ask-input'
        className={textareaClassName}
        value={value}
        onChange={onChange}
        onKeyDown={event => {
          if (
            sendShortcut === 'enter' &&
            event.key === 'Enter' &&
            !event.shiftKey &&
            !event.nativeEvent.isComposing
          ) {
            onSend();
          }
        }}
      />
      <button onClick={onSend}>send</button>
    </div>
  ),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
  toastOnce: jest.fn(),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('next/image', () => {
  return function MockImage({ alt, src }: { alt?: string; src?: string }) {
    return (
      <img
        alt={alt || ''}
        src={src || ''}
      />
    );
  };
});

jest.mock('@/assets/newchat/light/icon_shifu.svg', () => ({
  __esModule: true,
  default: '/icon_shifu.svg',
}));

let mockIsCurrentUserCourseOwner: boolean | null = false;

jest.mock('@/store/useCourseStore', () => ({
  useCourseStore: (
    selector?: (state: {
      courseAvatar: string;
      isCurrentUserCourseOwner: boolean | null;
    }) => unknown,
  ) => {
    const state = {
      courseAvatar: '',
      get isCurrentUserCourseOwner() {
        return mockIsCurrentUserCourseOwner;
      },
    };
    return selector ? selector(state) : state;
  },
}));

const mockSystemState: {
  showLearningModeToggle: boolean;
  learningMode: 'read' | 'listen' | 'classroom';
} = {
  showLearningModeToggle: true,
  learningMode: 'read',
};

jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: (selector?: (state: typeof mockSystemState) => unknown) => {
    return selector ? selector(mockSystemState) : mockSystemState;
  },
}));

const mockCheckIsRunning = jest.fn();
const mockGetRunMessage = jest.fn();

jest.mock('@/api/studyV2', () => ({
  BLOCK_TYPE: {
    CONTENT: 'content',
    INTERACTION: 'interaction',
    ASK: 'ask',
    ANSWER: 'answer',
    ERROR: 'error_message',
  },
  SSE_INPUT_TYPE: {
    NORMAL: 'normal',
    ASK: 'ask',
  },
  SSE_OUTPUT_TYPE: {
    ELEMENT: 'element',
    CONTENT: 'content',
    ERROR: 'error',
    BREAK: 'break',
    ASK: 'ask',
    TEXT_END: 'done',
    HEARTBEAT: 'heartbeat',
  },
  checkIsRunning: (...args: unknown[]) => mockCheckIsRunning(...args),
  getRunMessage: (...args: unknown[]) => mockGetRunMessage(...args),
}));

type Listener = (event?: Event) => void;

class MockRunSource {
  readyState = 0;

  private listeners = new Map<string, Listener[]>();

  addEventListener = jest.fn((type: string, listener: Listener) => {
    const existing = this.listeners.get(type) ?? [];
    existing.push(listener);
    this.listeners.set(type, existing);
  });

  close = jest.fn(() => {
    this.readyState = 2;
    this.emit('readystatechange');
  });

  emit(type: string, event?: Event) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

describe('AskBlock', () => {
  it('mirrors the in-input microphone with the existing Send action in RTL', () => {
    mockLanguage = 'ar-SA';
    render(
      <AskBlock
        shifu_bid='course-1'
        outline_bid='lesson-1'
        element_bid='element-1'
        isExpanded
        followUpMode='live_voice'
        liveVoice={mockLiveVoiceController()}
      />,
    );
    const composer = screen.getByTestId('ask-input-wrapper').parentElement;
    expect(composer).toHaveAttribute('dir', 'rtl');
    expect(composer).toContainElement(
      screen.getByRole('button', {
        name: 'module.chat.liveVoiceStartMicrophone',
      }),
    );
  });

  it('leaves the ordinary text input without a voice adornment', () => {
    render(
      <AskBlock
        shifu_bid='course-1'
        outline_bid='lesson-1'
        element_bid='element-1'
        isExpanded
      />,
    );
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    expect(screen.getByRole('textbox')).not.toHaveClass('liveTextarea');
    expect(
      screen.queryByRole('button', {
        name: 'module.chat.liveVoiceStartMicrophone',
      }),
    ).not.toBeInTheDocument();
  });

  it.each([false, true])(
    'uses the original input for Live without opening the microphone (mobile=%s)',
    async mobileStyle => {
      const liveVoice = mockLiveVoiceController();
      render(
        <AppContext.Provider value={{ mobileStyle } as any}>
          <AskBlock
            shifu_bid='course-1'
            outline_bid='lesson-1'
            element_bid='element-1'
            isExpanded
            followUpMode='live_voice'
            liveVoice={liveVoice}
          />
        </AppContext.Provider>,
      );
      expect(screen.getAllByRole('textbox')).toHaveLength(1);
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(liveVoice.start).not.toHaveBeenCalled();
      expect(liveVoice.startMicrophone).not.toHaveBeenCalled();
      const composer = screen.getByTestId('ask-input-wrapper').parentElement;
      expect(composer).toHaveClass('liveInput');
      expect(composer).toContainElement(
        screen.getByRole('button', {
          name: 'module.chat.liveVoiceStartMicrophone',
        }),
      );
      expect(composer).toContainElement(
        screen.getByRole('button', { name: 'send' }),
      );
      expect(screen.getByRole('textbox')).toHaveClass('liveTextarea');
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'Typed question' },
      });
      expect(liveVoice.stopMicrophone).toHaveBeenCalled();
      if (mobileStyle)
        fireEvent.click(screen.getByRole('button', { name: 'send' }));
      else
        fireEvent.keyDown(screen.getByRole('textbox'), {
          key: 'Enter',
          code: 'Enter',
        });
      await waitFor(() =>
        expect(liveVoice.sendText).toHaveBeenCalledWith(
          { anchorElementBid: 'element-1', surface: 'read_content' },
          'Typed question',
          mobileStyle ? 'button' : 'keyboard',
        ),
      );
      expect(mockGetRunMessage).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
      await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''));
    },
  );

  it('retains the draft on failed Live delivery and never uses credit/SSE gating', async () => {
    mockIsCurrentUserCourseOwner = null;
    const liveVoice = mockLiveVoiceController({
      sendText: jest.fn().mockResolvedValue(false),
    });
    render(
      <AskBlock
        shifu_bid='course-1'
        outline_bid='lesson-1'
        element_bid='element-1'
        isExpanded
        followUpMode='live_voice'
        liveVoice={liveVoice}
      />,
    );
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Keep this draft' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));
    await waitFor(() => expect(liveVoice.sendText).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('textbox')).toHaveValue('Keep this draft');
    expect(mockGetRunMessage).not.toHaveBeenCalled();
  });

  it('pauses only its own Live session when the original panel collapses', () => {
    const liveVoice = mockLiveVoiceController({
      anchorElementBid: 'element-1',
      open: true,
      state: 'listening',
    });
    const props = {
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      element_bid: 'element-1',
      followUpMode: 'live_voice' as const,
      liveVoice,
    };
    const { rerender } = render(
      <AskBlock
        {...props}
        isExpanded
      />,
    );
    rerender(
      <AskBlock
        {...props}
        isExpanded={false}
      />,
    );
    expect(liveVoice.pause).toHaveBeenCalledTimes(1);
    expect(liveVoice.close).not.toHaveBeenCalled();
  });

  it('renders Live history with the existing bubbles and no typewriter', () => {
    render(
      <AskBlock
        shifu_bid='course-1'
        outline_bid='lesson-1'
        element_bid='element-1'
        isExpanded
        followUpMode='live_voice'
        readonlyHistory
        askList={[
          {
            type: 'ask',
            content: 'Question',
            element_bid: 'ask-1',
            interaction_mode: 'live_voice',
          },
          {
            type: 'answer',
            content: 'Spoken answer',
            element_bid: 'answer-1',
            interaction_mode: 'live_voice',
            shouldUseTypewriter: false,
          },
        ]}
      />,
    );
    expect(screen.getByText('Question')).toBeInTheDocument();
    expect(screen.getByTestId('follow-up-answer')).toHaveAttribute(
      'data-typewriter',
      'false',
    );
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
  let activeRun:
    | {
        source: MockRunSource;
        onMessage: (response: {
          type: string;
          content?: string | Record<string, unknown>;
          is_terminal?: boolean;
        }) => Promise<void> | void;
      }
    | undefined;

  beforeEach(() => {
    jest.clearAllMocks();
    mockLanguage = 'zh-CN';
    activeRun = undefined;
    mockSystemState.showLearningModeToggle = true;
    mockSystemState.learningMode = 'read';
    mockIsCurrentUserCourseOwner = false;
    useAskStateStore.getState().clearLessonScope();
    mockCheckIsRunning.mockResolvedValue({
      is_running: false,
      running_time: 0,
    });
    mockGetRunMessage.mockImplementation(
      (
        _shifuBid: string,
        _outlineBid: string,
        _previewMode: boolean,
        _body: Record<string, unknown>,
        _creditInsufficientAudience: string,
        onMessage: (response: {
          type: string;
          content?: string | Record<string, unknown>;
          is_terminal?: boolean;
        }) => Promise<void> | void,
      ) => {
        const source = new MockRunSource();
        activeRun = { source, onMessage };
        return source;
      },
    );
  });

  it('tracks an accepted desktop Enter submission with a privacy-safe payload', async () => {
    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: false,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
        />
      </AppContext.Provider>,
    );

    fireEvent.change(screen.getByLabelText('ask-input'), {
      target: { value: 'private question' },
    });
    fireEvent.keyDown(screen.getByLabelText('ask-input'), { key: 'Enter' });

    await waitFor(() => expect(activeRun).toBeDefined());

    expect(mockTrackEvent).toHaveBeenCalledWith('learner_follow_up_submit', {
      surface: 'learner_desktop',
      submission_method: 'keyboard',
    });
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('content');
    expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('shifu_bid');
  });

  it('tracks an accepted mobile button submission and isolates tracking failures', async () => {
    mockTrackEvent.mockImplementationOnce(() => {
      throw new Error('tracking unavailable');
    });

    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
        />
      </AppContext.Provider>,
    );

    fireEvent.change(screen.getByLabelText('ask-input'), {
      target: { value: 'private question' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => expect(activeRun).toBeDefined());
    expect(mockTrackEvent).toHaveBeenCalledWith('learner_follow_up_submit', {
      surface: 'learner_mobile',
      submission_method: 'button',
    });
  });

  it.each([
    ['desktop', false, 'enter'],
    ['mobile', true, 'none'],
  ] as const)(
    'uses the %s input shortcut policy',
    (_surface, mobileStyle, expectedShortcut) => {
      render(
        <AppContext.Provider
          value={{
            isLoggedIn: false,
            mobileStyle,
            userInfo: null,
            theme: 'light',
            frameLayout: 0,
          }}
        >
          <AskBlock
            isExpanded={true}
            shifu_bid='shifu-1'
            outline_bid='lesson-1'
            element_bid='block-1'
            askList={[]}
          />
        </AppContext.Provider>,
      );

      expect(screen.getByTestId('ask-input-wrapper')).toHaveAttribute(
        'data-send-shortcut',
        expectedShortcut,
      );
    },
  );

  it('renders Live voice history inline on mobile without a text input or panel', () => {
    const onToggleAskExpanded = jest.fn();
    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={false}
          readonlyHistory
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          onToggleAskExpanded={onToggleAskExpanded}
          askList={[
            { type: BLOCK_TYPE.ASK, content: 'Transcribed question' },
            { type: BLOCK_TYPE.ANSWER, content: 'Transcribed answer' },
          ]}
        />
      </AppContext.Provider>,
    );

    expect(screen.getByText('Transcribed question')).toBeInTheDocument();
    expect(screen.getByText('Transcribed answer')).toBeInTheDocument();
    expect(screen.queryByLabelText('ask-input')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Close' }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Transcribed question'));
    expect(onToggleAskExpanded).not.toHaveBeenCalled();
    expect(document.body.style.overflow).toBe('');
  });

  it.each(['read', 'listen'] as const)(
    'sends follow-up requests without TTS in %s mode',
    async learningMode => {
      mockSystemState.learningMode = learningMode;

      render(
        <AppContext.Provider
          value={{
            isLoggedIn: false,
            mobileStyle: false,
            userInfo: null,
            theme: 'light',
            frameLayout: 0,
          }}
        >
          <AskBlock
            isExpanded={true}
            shifu_bid='shifu-1'
            outline_bid='lesson-1'
            element_bid='block-1'
            askList={[]}
          />
        </AppContext.Provider>,
      );

      fireEvent.change(screen.getByLabelText('ask-input'), {
        target: { value: 'follow up question' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'send' }));

      await waitFor(() => expect(activeRun).toBeDefined());
      expect(mockGetRunMessage.mock.calls[0][3]).toMatchObject({
        input: 'follow up question',
        input_type: 'ask',
        listen: false,
        reload_generated_block_bid: 'block-1',
        reload_element_bid: 'block-1',
      });

      await act(async () => {
        await activeRun?.onMessage({
          type: SSE_OUTPUT_TYPE.CONTENT,
          content: 'answer chunk',
        });
      });

      expect(screen.getByText('follow up question')).toBeInTheDocument();
      expect(screen.getByText('answer chunk')).toBeInTheDocument();

      await act(async () => {
        await activeRun?.onMessage({
          type: SSE_OUTPUT_TYPE.TEXT_END,
          is_terminal: true,
        });
      });

      await waitFor(() => expect(activeRun?.source.close).toHaveBeenCalled());
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1'],
      ).toHaveLength(2);
    },
  );

  it('does not start a preview follow-up before ownership is resolved', async () => {
    mockIsCurrentUserCourseOwner = null;

    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: false,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
          preview_mode={true}
        />
      </AppContext.Provider>,
    );

    fireEvent.change(screen.getByLabelText('ask-input'), {
      target: { value: 'follow up question' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await act(async () => {});
    expect(mockGetRunMessage).not.toHaveBeenCalled();
    expect(
      useAskStateStore.getState().askListByAnchorElementBid['block-1'] ?? [],
    ).toHaveLength(0);
  });

  it('rolls back a partial follow-up answer when the transport fails', async () => {
    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: false,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
        />
      </AppContext.Provider>,
    );

    fireEvent.change(screen.getByLabelText('ask-input'), {
      target: { value: 'follow up question' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => expect(activeRun).toBeDefined());
    await act(async () => {
      await activeRun?.onMessage({
        type: SSE_OUTPUT_TYPE.CONTENT,
        content: 'partial answer',
      });
    });

    expect(screen.getByText('partial answer')).toBeInTheDocument();

    act(() => {
      activeRun?.source.emit('error');
    });

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1'] ?? [],
      ).toHaveLength(0),
    );
    expect(screen.queryByText('partial answer')).not.toBeInTheDocument();
    expect(
      (screen.getByLabelText('ask-input') as HTMLTextAreaElement).value,
    ).toBe('follow up question');
    expect(activeRun?.source.close).toHaveBeenCalled();
  });

  it('rolls back and closes the follow-up stream when response handling throws', async () => {
    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: false,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
        />
      </AppContext.Provider>,
    );

    fireEvent.change(screen.getByLabelText('ask-input'), {
      target: { value: 'follow up question' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));
    await waitFor(() => expect(activeRun).toBeDefined());

    const invalidResponse = {
      type: SSE_OUTPUT_TYPE.ELEMENT,
      get content(): Record<string, unknown> {
        throw new Error('invalid response payload');
      },
    };
    await act(async () => {
      await activeRun?.onMessage(invalidResponse);
    });

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1'] ?? [],
      ).toHaveLength(0),
    );
    expect(activeRun?.source.close).toHaveBeenCalled();
    expect(
      (screen.getByLabelText('ask-input') as HTMLTextAreaElement).value,
    ).toBe('follow up question');
  });

  it('updates the live answer when the server emits answer element patches', async () => {
    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: false,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
        />
      </AppContext.Provider>,
    );

    fireEvent.change(screen.getByLabelText('ask-input'), {
      target: { value: 'follow up question' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        type: 'element',
        content: {
          element_type: 'answer',
          content: 'first chunk',
        },
      });
    });

    expect(screen.getByText('first chunk')).toBeInTheDocument();

    await act(async () => {
      await activeRun?.onMessage({
        type: 'element',
        content: {
          element_type: 'answer',
          content: 'first chunk and more',
        },
      });
    });

    expect(screen.getByText('first chunk and more')).toBeInTheDocument();

    await act(async () => {
      await activeRun?.onMessage({
        type: SSE_OUTPUT_TYPE.TEXT_END,
        is_terminal: true,
      });
    });

    await waitFor(() => expect(activeRun?.source.close).toHaveBeenCalled());
  });

  it('keeps typewriter enabled when follow-up done is non-terminal', async () => {
    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: false,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
        />
      </AppContext.Provider>,
    );

    fireEvent.change(screen.getByLabelText('ask-input'), {
      target: { value: 'follow up question' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_type: 'answer',
          content: 'first chunk',
          element_bid: 'answer-1',
        },
      });
    });

    await act(async () => {
      await activeRun?.onMessage({
        type: SSE_OUTPUT_TYPE.TEXT_END,
        is_terminal: false,
      });
    });

    expect(activeRun?.source.close).not.toHaveBeenCalled();
    expect(
      useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[1],
    ).toMatchObject({
      content: 'first chunk',
      isStreaming: true,
      shouldUseTypewriter: true,
      element_bid: 'answer-1',
    });
  });

  it('keeps the streaming answer typewriter enabled when the panel expands', async () => {
    const askList = [
      {
        type: 'answer',
        content: 'streaming answer',
        isStreaming: true,
        shouldUseTypewriter: true,
        element_bid: 'answer-1',
      },
    ] as const;

    const { rerender } = render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={false}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[...askList]}
        />
      </AppContext.Provider>,
    );

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[0]
          ?.shouldUseTypewriter,
      ).toBe(true),
    );

    rerender(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[...askList]}
        />
      </AppContext.Provider>,
    );

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[0]
          ?.shouldUseTypewriter,
      ).toBe(true),
    );
  });

  it('disables the answer typewriter when the panel collapses', async () => {
    const askList = [
      {
        type: 'answer',
        content: 'finished answer',
        isStreaming: false,
        shouldUseTypewriter: true,
        element_bid: 'answer-1',
      },
    ] as const;

    const { rerender } = render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[...askList]}
        />
      </AppContext.Provider>,
    );

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[0]
          ?.shouldUseTypewriter,
      ).toBe(true),
    );

    rerender(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={false}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[...askList]}
        />
      </AppContext.Provider>,
    );

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[0]
          ?.shouldUseTypewriter,
      ).toBe(false),
    );
  });

  it('keeps the streaming answer typewriter enabled when the panel collapses', async () => {
    const askList = [
      {
        type: 'ask',
        content: 'follow up question',
      },
      {
        type: 'answer',
        content: 'streaming answer',
        isStreaming: true,
        shouldUseTypewriter: true,
        element_bid: 'answer-1',
      },
    ] as const;

    const { rerender } = render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[...askList]}
        />
      </AppContext.Provider>,
    );

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[1]
          ?.shouldUseTypewriter,
      ).toBe(true),
    );
    expect(screen.getByTestId('follow-up-answer')).toHaveAttribute(
      'data-typewriter-pacing',
      'content-aware',
    );
    expect(screen.getByTestId('follow-up-answer')).toHaveAttribute(
      'data-typing-speed',
      '30',
    );

    rerender(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={false}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[...askList]}
        />
      </AppContext.Provider>,
    );

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[1]
          ?.shouldUseTypewriter,
      ).toBe(true),
    );
  });

  it('keeps the streaming answer mounted while the mobile panel is collapsed', async () => {
    const askList = [
      {
        type: 'ask',
        content: 'follow up question',
      },
      {
        type: 'answer',
        content: 'streaming answer',
        isStreaming: true,
        shouldUseTypewriter: true,
        element_bid: 'answer-1',
      },
    ] as const;

    const { rerender } = render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[...askList]}
        />
      </AppContext.Provider>,
    );

    expect(screen.getByText('streaming answer')).toBeInTheDocument();

    rerender(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={false}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[...askList]}
        />
      </AppContext.Provider>,
    );

    expect(screen.getByText('streaming answer')).toBeInTheDocument();
  });

  it('disables the streaming answer typewriter when the stream finishes while the panel is collapsed', async () => {
    const { rerender } = render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
        />
      </AppContext.Provider>,
    );

    fireEvent.change(screen.getByLabelText('ask-input'), {
      target: { value: 'follow up question' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => expect(activeRun).toBeDefined());
    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[1]
          ?.shouldUseTypewriter,
      ).toBe(true),
    );

    rerender(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={false}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[]}
        />
      </AppContext.Provider>,
    );

    await act(async () => {
      await activeRun?.onMessage({
        type: SSE_OUTPUT_TYPE.TEXT_END,
        is_terminal: true,
      });
    });

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['block-1']?.[1],
      ).toMatchObject({
        isStreaming: false,
        shouldUseTypewriter: false,
      }),
    );
  });

  it('renders every follow-up inline without controls or typewriter in print mode', () => {
    render(
      <AppContext.Provider
        value={{
          isLoggedIn: false,
          mobileStyle: true,
          userInfo: null,
          theme: 'light',
          frameLayout: 0,
        }}
      >
        <AskBlock
          isExpanded={false}
          printMode={true}
          shifu_bid='shifu-1'
          outline_bid='lesson-1'
          element_bid='block-1'
          askList={[
            { type: 'ask', content: '第一条追问问题' },
            {
              type: 'answer',
              content: '第一条追问回答',
              shouldUseTypewriter: true,
            },
            { type: 'ask', content: '第二条追问问题' },
            {
              type: 'answer',
              content: '第二条追问回答',
              shouldUseTypewriter: true,
            },
          ]}
        />
      </AppContext.Provider>,
    );

    expect(screen.getByText('第一条追问问题')).toBeInTheDocument();
    expect(screen.getByText('第一条追问回答')).toBeInTheDocument();
    expect(screen.getByText('第二条追问问题')).toBeInTheDocument();
    expect(screen.getByText('第二条追问回答')).toBeInTheDocument();
    expect(screen.queryByLabelText('ask-input')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    screen
      .getAllByTestId('follow-up-answer')
      .forEach(answer =>
        expect(answer).toHaveAttribute('data-typewriter', 'false'),
      );
  });

  describe('when the backend rejects the ask via SSE error', () => {
    const renderAskBlock = (previewMode = false) =>
      render(
        <AppContext.Provider
          value={{
            isLoggedIn: false,
            mobileStyle: false,
            userInfo: null,
            theme: 'light',
            frameLayout: 0,
          }}
        >
          <AskBlock
            isExpanded={true}
            shifu_bid='shifu-1'
            outline_bid='lesson-1'
            element_bid='block-1'
            preview_mode={previewMode}
            askList={[]}
          />
        </AppContext.Provider>,
      );

    it('rolls back the local ask/answer placeholders, refills the input, and toasts the backend message', async () => {
      renderAskBlock();

      fireEvent.change(screen.getByLabelText('ask-input'), {
        target: { value: 'follow up question' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'send' }));

      await waitFor(() => expect(activeRun).toBeDefined());
      await waitFor(() =>
        expect(
          useAskStateStore.getState().askListByAnchorElementBid['block-1']
            ?.length,
        ).toBe(2),
      );

      await act(async () => {
        await activeRun?.onMessage({
          type: SSE_OUTPUT_TYPE.ERROR,
          content: 'Content is still generating. Please wait before retrying.',
        });
      });

      await waitFor(() =>
        expect(
          useAskStateStore.getState().askListByAnchorElementBid['block-1']
            ?.length ?? 0,
        ).toBe(0),
      );

      expect(toast).toHaveBeenCalledWith({
        title: 'Content is still generating. Please wait before retrying.',
      });
      expect(activeRun?.source.close).toHaveBeenCalled();
      expect(
        (screen.getByLabelText('ask-input') as HTMLTextAreaElement).value,
      ).toBe('follow up question');
    });

    it('falls back to the local i18n message when the error event carries no content', async () => {
      renderAskBlock();

      fireEvent.change(screen.getByLabelText('ask-input'), {
        target: { value: 'another question' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'send' }));

      await waitFor(() => expect(activeRun).toBeDefined());

      await act(async () => {
        await activeRun?.onMessage({
          type: SSE_OUTPUT_TYPE.ERROR,
        });
      });

      await waitFor(() =>
        expect(
          useAskStateStore.getState().askListByAnchorElementBid['block-1']
            ?.length ?? 0,
        ).toBe(0),
      );

      expect(toast).toHaveBeenCalledWith({
        title: 'module.chat.outputInProgress',
      });
      expect(
        (screen.getByLabelText('ask-input') as HTMLTextAreaElement).value,
      ).toBe('another question');
    });

    it('shows a deduped friendly toast for technical AI service errors', async () => {
      renderAskBlock();

      fireEvent.change(screen.getByLabelText('ask-input'), {
        target: { value: 'technical question' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'send' }));

      await waitFor(() => expect(activeRun).toBeDefined());

      await act(async () => {
        await activeRun?.onMessage({
          type: SSE_OUTPUT_TYPE.ERROR,
          content: '模型 deepseek 调用失败：provider unavailable',
        });
      });

      expect(toast).not.toHaveBeenCalledWith(
        expect.objectContaining({
          title: expect.stringContaining('deepseek'),
        }),
      );
      expect(toastOnce).toHaveBeenCalledWith(
        expect.objectContaining({
          dedupeKey: 'ai-service-unavailable',
          title: 'module.chat.contentGenerationUnavailable',
          variant: 'destructive',
          duration: 8000,
        }),
      );
    });

    it('uses the permanent course-specific learner notice for credit errors', async () => {
      renderAskBlock();

      fireEvent.change(screen.getByLabelText('ask-input'), {
        target: { value: 'credit question' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'send' }));

      await waitFor(() => expect(activeRun).toBeDefined());

      await act(async () => {
        await activeRun?.onMessage({
          type: SSE_OUTPUT_TYPE.ERROR,
          content: { code: 7101 },
        });
      });

      expect(toast).not.toHaveBeenCalled();
      expect(toastOnce).toHaveBeenCalledWith(
        expect.objectContaining({
          dedupeKey: 'credit-insufficient:learner:7101',
          dedupeWindowMs: Number.POSITIVE_INFINITY,
          title: 'module.billing.creditInsufficient.learner',
          duration: 0,
          action: undefined,
        }),
      );
    });

    it('tells a preview collaborator to contact the course owner', async () => {
      renderAskBlock(true);

      fireEvent.change(screen.getByLabelText('ask-input'), {
        target: { value: 'collaborator question' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'send' }));

      await waitFor(() => expect(activeRun).toBeDefined());
      expect(mockGetRunMessage.mock.calls.at(-1)?.[4]).toBe(
        'teacher-collaborator',
      );

      await act(async () => {
        await activeRun?.onMessage({
          type: SSE_OUTPUT_TYPE.ERROR,
          content: { code: 7101 },
        });
      });

      expect(toastOnce).toHaveBeenCalledWith(
        expect.objectContaining({
          dedupeKey: 'credit-insufficient:teacher-collaborator:7101',
          title: 'module.billing.creditInsufficient.teacherCollaborator',
          duration: 0,
          action: undefined,
        }),
      );
    });
  });
});

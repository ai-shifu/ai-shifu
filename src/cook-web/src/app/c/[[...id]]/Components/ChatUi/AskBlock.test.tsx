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
import { SSE_OUTPUT_TYPE } from '@/c-api/studyV2';
import { useAskStateStore } from './useAskStateStore';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/c-utils/markdownUtils', () => ({
  fixMarkdownStream: (_previous: string, delta: string) => delta,
}));

jest.mock('markdown-flow-ui/renderer', () => ({
  ContentRender: ({ content }: { content: string }) => <div>{content}</div>,
  MarkdownFlowInput: ({
    value,
    onChange,
    onSend,
  }: {
    value: string;
    onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
    onSend: () => void;
  }) => (
    <div>
      <textarea
        aria-label='ask-input'
        value={value}
        onChange={onChange}
      />
      <button onClick={onSend}>send</button>
    </div>
  ),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
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

jest.mock('@/c-assets/newchat/light/icon_shifu.svg', () => ({
  __esModule: true,
  default: '/icon_shifu.svg',
}));

jest.mock('@/c-store/useCourseStore', () => ({
  useCourseStore: (selector?: (state: { courseAvatar: string }) => unknown) => {
    const state = { courseAvatar: '' };
    return selector ? selector(state) : state;
  },
}));

const mockSystemState: {
  showLearningModeToggle: boolean;
  learningMode: 'read' | 'listen';
} = {
  showLearningModeToggle: true,
  learningMode: 'read',
};

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: (selector?: (state: typeof mockSystemState) => unknown) => {
    return selector ? selector(mockSystemState) : mockSystemState;
  },
}));

const mockCheckIsRunning = jest.fn();
const mockGetRunMessage = jest.fn();

jest.mock('@/c-api/studyV2', () => ({
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
  let activeRun:
    | {
        source: MockRunSource;
        onMessage: (response: {
          type: string;
          content?: string | Record<string, unknown>;
        }) => Promise<void> | void;
      }
    | undefined;

  beforeEach(() => {
    jest.clearAllMocks();
    activeRun = undefined;
    mockSystemState.showLearningModeToggle = true;
    mockSystemState.learningMode = 'read';
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
        onMessage: (response: {
          type: string;
          content?: string | Record<string, unknown>;
        }) => Promise<void> | void,
      ) => {
        const source = new MockRunSource();
        activeRun = { source, onMessage };
        return source;
      },
    );
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
    },
  );

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
});

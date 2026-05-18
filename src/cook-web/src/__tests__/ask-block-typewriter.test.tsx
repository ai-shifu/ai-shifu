import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import AskBlock from '@/app/c/[[...id]]/Components/ChatUi/AskBlock';
import { AppContext } from '@/c-components/AppContext';
import { useAskStateStore } from '@/app/c/[[...id]]/Components/ChatUi/useAskStateStore';

const mockContentRender = jest.fn<null, [Record<string, unknown>]>(() => null);

let activeOnMessage: ((response: any) => Promise<void> | void) | undefined;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    t: (key: string) => key,
  },
}));

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
}));

jest.mock('@/c-store/useCourseStore', () => ({
  useCourseStore: jest.fn(() => ''),
}));

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: jest.fn(() => false),
}));

jest.mock('@/components/ui/Avatar', () => ({
  Avatar: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
  AvatarImage: () => null,
}));

jest.mock('markdown-flow-ui/renderer', () => ({
  ContentRender: (props: Record<string, unknown>) => {
    mockContentRender(props);
    return null;
  },
  MarkdownFlowInput: ({
    value,
    onChange,
    onSend,
  }: {
    value?: string;
    onChange?: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
    onSend?: () => void;
  }) => (
    <div>
      <textarea
        data-testid='ask-input'
        value={value as string}
        onChange={onChange}
      />
      <button
        type='button'
        onClick={onSend}
      >
        send
      </button>
    </div>
  ),
}));

jest.mock('@/c-api/studyV2', () => ({
  BLOCK_TYPE: {
    ASK: 'ask',
    ANSWER: 'answer',
  },
  SSE_INPUT_TYPE: {
    ASK: 'ask',
  },
  SSE_OUTPUT_TYPE: {
    HEARTBEAT: 'heartbeat',
    ERROR: 'error',
    CONTENT: 'content',
    ELEMENT: 'element',
    BREAK: 'break',
    TEXT_END: 'done',
  },
  getRunMessage: jest.fn(
    (
      _shifuBid: string,
      _outlineBid: string,
      _previewMode: boolean,
      _body: Record<string, unknown>,
      onMessage: (response: any) => Promise<void> | void,
    ) => {
      activeOnMessage = onMessage;
      return {
        readyState: 0,
        addEventListener: jest.fn(),
        close: jest.fn(),
      };
    },
  ),
}));

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <AppContext.Provider
    value={{
      isLoggedIn: false,
      mobileStyle: false,
      userInfo: null,
      theme: 'light',
      frameLayout: 0,
    }}
  >
    {children}
  </AppContext.Provider>
);

const getLastContentRenderProps = () => {
  const calls = mockContentRender.mock.calls;
  return calls[calls.length - 1]?.[0] ?? null;
};

describe('AskBlock typewriter lifecycle', () => {
  beforeEach(() => {
    mockContentRender.mockClear();
    activeOnMessage = undefined;
    useAskStateStore.getState().clearLessonScope();
  });

  it('disables typewriter after ask block expand state changes', async () => {
    const { rerender } = render(
      <AskBlock
        askList={[
          {
            type: 'answer' as any,
            content: 'streamed answer',
            shouldUseTypewriter: true,
          },
        ]}
        isExpanded={true}
        shifu_bid='shifu-1'
        outline_bid='lesson-1'
        element_bid='anchor-1'
      />,
      { wrapper },
    );

    expect(getLastContentRenderProps()).toEqual(
      expect.objectContaining({
        enableTypewriter: true,
      }),
    );

    rerender(
      <AskBlock
        askList={[
          {
            type: 'answer' as any,
            content: 'streamed answer',
            shouldUseTypewriter: true,
          },
        ]}
        isExpanded={false}
        shifu_bid='shifu-1'
        outline_bid='lesson-1'
        element_bid='anchor-1'
      />,
    );

    await waitFor(() =>
      expect(getLastContentRenderProps()).toEqual(
        expect.objectContaining({
          enableTypewriter: false,
        }),
      ),
    );
  });

  it('keeps typewriter enabled after terminal follow-up streaming ends', async () => {
    render(
      <AskBlock
        askList={[]}
        isExpanded={true}
        shifu_bid='shifu-1'
        outline_bid='lesson-1'
        element_bid='anchor-1'
      />,
      { wrapper },
    );

    fireEvent.change(screen.getByTestId('ask-input'), {
      target: { value: 'who are you' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() =>
      expect(getLastContentRenderProps()).toEqual(
        expect.objectContaining({
          enableTypewriter: true,
        }),
      ),
    );

    await act(async () => {
      await activeOnMessage?.({
        type: 'content',
        content: 'hello there',
      });
    });

    await waitFor(() =>
      expect(getLastContentRenderProps()).toEqual(
        expect.objectContaining({
          content: 'hello there',
          enableTypewriter: true,
        }),
      ),
    );

    await act(async () => {
      await activeOnMessage?.({
        type: 'done',
        content: '',
        is_terminal: true,
      });
    });

    await waitFor(() =>
      expect(getLastContentRenderProps()).toEqual(
        expect.objectContaining({
          content: 'hello there',
          enableTypewriter: true,
        }),
      ),
    );
  });

  it('keeps locally appended follow-up history after collapsing and rehydrating with a shorter ask list', async () => {
    const initialAskList = [
      {
        type: 'ask' as any,
        content: '你是谁啊',
      },
      {
        type: 'answer' as any,
        content: '我是何少甫',
      },
    ];
    const latestAnswer = '再追问后的答案';
    const { rerender } = render(
      <AskBlock
        askList={initialAskList}
        isExpanded={true}
        shifu_bid='shifu-1'
        outline_bid='lesson-1'
        element_bid='anchor-1'
      />,
      { wrapper },
    );

    await act(async () => {
      useAskStateStore.getState().setAskList('anchor-1', [
        ...initialAskList,
        {
          type: 'ask' as any,
          content: '1111',
        },
        {
          type: 'answer' as any,
          content: latestAnswer,
          shouldUseTypewriter: false,
        },
      ]);
    });

    rerender(
      <AskBlock
        askList={[...initialAskList]}
        isExpanded={false}
        shifu_bid='shifu-1'
        outline_bid='lesson-1'
        element_bid='anchor-1'
      />,
    );

    rerender(
      <AskBlock
        askList={[...initialAskList]}
        isExpanded={true}
        shifu_bid='shifu-1'
        outline_bid='lesson-1'
        element_bid='anchor-1'
      />,
    );

    await waitFor(() =>
      expect(
        useAskStateStore.getState().askListByAnchorElementBid['anchor-1'],
      ).toHaveLength(4),
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({
        content: latestAnswer,
      }),
    );
  });
});

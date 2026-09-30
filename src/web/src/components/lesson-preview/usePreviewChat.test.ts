import { act, renderHook, waitFor } from '@testing-library/react';
import { SSE } from 'sse.js';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from '@/types/chatUi';
import { toast, toastOnce } from '@/hooks/useToast';
import { attachSseBusinessResponseFallback } from '@/lib/request';
import { getCreditInsufficientMessage } from '@/lib/creditInsufficientToast';
import {
  buildInteractionContinuationPreviewParams,
  buildPreviewBusinessErrorItem,
  replacePreviewLoadingWithBusinessError,
  usePreviewChat,
} from './usePreviewChat';

const mockParseToRemarkFormat = jest.fn();
const mockTrackEvent = jest.fn();
const mockGetCurrentMdflow = jest.fn();

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('sse.js', () => ({
  SSE: jest.fn(),
}));

jest.mock('remark-flow', () => ({
  createInteractionParser: () => ({
    parseToRemarkFormat: mockParseToRemarkFormat,
  }),
}));

jest.mock('@/api/studyV2', () => ({
  ELEMENT_TYPE: {
    TEXT: 'text',
    HTML: 'html',
    INTERACTION: 'interaction',
  },
  LIKE_STATUS: {
    NONE: 'none',
  },
}));

jest.mock('@/store', () => {
  const useUserStore = jest.fn();
  (
    useUserStore as typeof useUserStore & {
      getState: () => { getToken: () => string };
    }
  ).getState = () => ({
    getToken: () => '',
  });

  return {
    useShifu: () => ({ actions: { getCurrentMdflow: mockGetCurrentMdflow } }),
    useUserStore,
  };
});

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
  toastOnce: jest.fn(),
}));

jest.mock('@/lib/request', () => ({
  attachSseBusinessResponseFallback: jest.fn(),
}));

jest.mock('@/lib/request-trace', () => ({
  buildTraceHeaders: jest.fn(() => ({
    headers: {},
    requestId: 'request-id',
    harnessRunId: 'harness-run-id',
  })),
}));

jest.mock('@/config/environment', () => ({
  getDynamicApiBaseUrl: jest.fn(async () => ''),
}));

jest.mock('@/lib/envUtils', () => ({
  getStringEnv: jest.fn(() => ''),
}));

type MockSseSource = {
  addEventListener: jest.Mock;
  stream: jest.Mock;
  close: jest.Mock;
  listeners: Record<string, (event: { data?: string }) => void>;
};

const buildMockSseSource = (): MockSseSource => {
  const listeners: Record<string, (event: { data?: string }) => void> = {};
  return {
    listeners,
    addEventListener: jest.fn(
      (type: string, listener: (event: { data?: string }) => void) => {
        listeners[type] = listener;
      },
    ),
    stream: jest.fn(),
    close: jest.fn(),
  };
};

jest.mock('@/lib/markdownUtils', () => ({
  mergeStreamingMarkdownText: jest.fn((_prev: string, next: string) => next),
  maskIncompleteMermaidBlock: jest.fn((content: string) => content),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('usePreviewChat helpers and business error rendering', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockReset();
    mockGetCurrentMdflow.mockReturnValue(undefined);
  });

  afterEach(() => {
    jest.useRealTimers();
  });
  test('builds interaction continuation preview params with latest mdflow', () => {
    expect(
      buildInteractionContinuationPreviewParams({
        currentParams: {
          shifuBid: 'shifu-1',
          outlineBid: 'lesson-1',
          mdflow: 'old prompt',
          block_index: 1,
          variables: { oldVar: 'old' },
          user_input: { oldVar: ['old'] },
        },
        latestMdflow: 'new prompt',
        blockIndex: 3,
        variables: { answer: '42' },
        userInput: { answer: ['42'] },
      }),
    ).toEqual({
      shifuBid: 'shifu-1',
      outlineBid: 'lesson-1',
      mdflow: 'new prompt',
      block_index: 3,
      variables: { answer: '42' },
      user_input: { answer: ['42'] },
    });
  });

  test('does not open preview streams while ownership is unresolved', async () => {
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: null }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'content',
      });
    });
    await expect(
      result.current.requestAudioForBlock({
        shifuBid: 'shifu-1',
        blockId: 'block-1',
        text: 'content',
      }),
    ).resolves.toBeNull();

    expect(SSE).not.toHaveBeenCalled();
  });

  test('does not advance 1.0 block indices after a 2.0 debug turn', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'Draft script',
        max_block_count: 3,
      });
    });
    const request = (SSE as jest.Mock).mock.calls[0][1];
    expect(JSON.parse(request.payload)).toEqual(
      expect.objectContaining({
        content: 'Draft script',
        debug_session_id: expect.any(String),
      }),
    );

    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      source.listeners.message?.({
        data: JSON.stringify({
          type: 'content',
          generated_block_bid: 'turn-1',
          content: 'The lesson.',
        }),
      });
      source.listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
    });

    expect(SSE).toHaveBeenCalledTimes(1);
    expect(source.close).toHaveBeenCalled();
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_lesson_preview_engine_started',
      {
        engine: 'v2',
        shifu_bid: 'shifu-1',
        outline_bid: 'lesson-1',
      },
    );
  });

  test('tracks the preview engine once per debug session and ignores tracking failures', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'Private draft',
      });
    });

    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '1.0' }),
      });
      source.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '1.0' }),
      });
      source.listeners.message?.({
        data: JSON.stringify({
          type: 'content',
          generated_block_bid: 'block',
          content: 'Visible content',
        }),
      });
    });

    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_lesson_preview_engine_started',
      {
        engine: 'v1',
        shifu_bid: 'shifu-1',
        outline_bid: 'lesson-1',
      },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'Private draft',
    );
    expect(result.current.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ content: 'Visible content' }),
      ]),
    );
  });

  test('keeps a debug session across answers and replaces it on reset', async () => {
    const sources = [
      buildMockSseSource(),
      buildMockSseSource(),
      buildMockSseSource(),
    ];
    sources.forEach(source => (SSE as jest.Mock).mockReturnValueOnce(source));
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    const params = {
      shifuBid: 'shifu-1',
      outlineBid: 'lesson-1',
      mdflow: 'Draft script',
      max_block_count: 3,
    };

    await act(async () => {
      await result.current.startPreview(params);
      await result.current.startPreview({
        ...params,
        user_input: { answer: ['yes'] },
      });
    });
    const first = JSON.parse((SSE as jest.Mock).mock.calls[0][1].payload);
    const second = JSON.parse((SSE as jest.Mock).mock.calls[1][1].payload);
    expect(second.debug_session_id).toBe(first.debug_session_id);
    expect(second.user_input).toEqual({ answer: ['yes'] });

    act(() => result.current.resetPreview());
    await act(async () => result.current.startPreview(params));
    const third = JSON.parse((SSE as jest.Mock).mock.calls[2][1].payload);
    expect(third.debug_session_id).not.toBe(first.debug_session_id);
  });

  test('lets a restarted 2.0 debug session answer a question with a saved variable', async () => {
    jest.useFakeTimers();
    mockParseToRemarkFormat.mockReturnValue({
      variableName: 'answer',
      buttonTexts: ['old choice', 'new choice'],
      buttonValues: ['old choice', 'new choice'],
    });
    const firstSource = buildMockSseSource();
    const answerSource = buildMockSseSource();
    (SSE as jest.Mock)
      .mockReturnValueOnce(firstSource)
      .mockReturnValueOnce(answerSource);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () =>
      result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'Ask for an answer',
        variables: { answer: 'old choice' },
      }),
    );
    act(() => {
      firstSource.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      firstSource.listeners.message?.({
        data: JSON.stringify({
          type: 'element',
          content: {
            element_bid: 'question-1',
            element_type: 'interaction',
            content: '?[answer]',
          },
        }),
      });
      firstSource.listeners.message?.({
        data: JSON.stringify({
          type: 'interaction',
          generated_block_bid: 'question-1',
          content: '?[answer]',
        }),
      });
      firstSource.listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
      jest.advanceTimersByTime(1000);
    });

    expect(SSE).toHaveBeenCalledTimes(1);
    expect(
      result.current.items.find(item => item.element_bid === 'question-1'),
    ).toMatchObject({ user_input: '' });

    await act(async () =>
      result.current.onSend(
        { variableName: 'answer', selectedValues: ['new choice'] },
        'question-1',
      ),
    );
    expect(SSE).toHaveBeenCalledTimes(2);
    const firstRequest = JSON.parse(
      (SSE as jest.Mock).mock.calls[0][1].payload,
    );
    const answerRequest = JSON.parse(
      (SSE as jest.Mock).mock.calls[1][1].payload,
    );
    expect(answerRequest.debug_session_id).toBe(firstRequest.debug_session_id);
    expect(answerRequest.user_input).toEqual({ answer: ['new choice'] });
  });

  test('omits the debug session ID when browser cryptography is unavailable', async () => {
    const cryptoProperty = Object.getOwnPropertyDescriptor(
      globalThis,
      'crypto',
    );
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: undefined,
    });
    try {
      (SSE as jest.Mock).mockReturnValueOnce(buildMockSseSource());
      const { result } = renderHook(() =>
        usePreviewChat({ creditInsufficientAudience: 'teacher' }),
      );
      await act(async () =>
        result.current.startPreview({
          shifuBid: 'shifu-1',
          outlineBid: 'lesson-1',
          mdflow: 'Draft',
        }),
      );
      const payload = JSON.parse((SSE as jest.Mock).mock.calls[0][1].payload);
      expect(payload).not.toHaveProperty('debug_session_id');
    } finally {
      if (cryptoProperty) {
        Object.defineProperty(globalThis, 'crypto', cryptoProperty);
      }
    }
  });

  test('starts an edited 2.0 draft without submitting an answer from the old script', async () => {
    const firstSource = buildMockSseSource();
    const secondSource = buildMockSseSource();
    (SSE as jest.Mock)
      .mockReturnValueOnce(firstSource)
      .mockReturnValueOnce(secondSource);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    const params = {
      shifuBid: 'shifu-1',
      outlineBid: 'lesson-1',
      mdflow: 'Original draft',
      variables: { learnerName: 'Ada' },
      max_block_count: 3,
    };

    await act(async () => result.current.startPreview(params));
    act(() => {
      firstSource.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      firstSource.listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
    });
    act(() => result.current.onVariableChange('answer', 'old choice'));
    await act(async () =>
      result.current.startPreview({
        ...params,
        mdflow: 'Edited draft',
        block_index: 1,
        variables: { learnerName: 'Ada', answer: 'old choice' },
        user_input: { answer: ['old choice'] },
      }),
    );

    const first = JSON.parse((SSE as jest.Mock).mock.calls[0][1].payload);
    const second = JSON.parse((SSE as jest.Mock).mock.calls[1][1].payload);
    expect(second.content).toBe('Edited draft');
    expect(second.block_index).toBe(0);
    expect(second.user_input).toBeUndefined();
    expect(second.variables).toEqual({ learnerName: 'Ada' });
    expect(second.debug_session_id).not.toBe(first.debug_session_id);
  });

  test('discards the pending answer before restarting an edited 2.0 draft and on refresh', async () => {
    jest.useFakeTimers();
    mockParseToRemarkFormat.mockReturnValue({ variableName: 'answer' });
    const sources = [
      buildMockSseSource(),
      buildMockSseSource(),
      buildMockSseSource(),
    ];
    sources.forEach(source => (SSE as jest.Mock).mockReturnValueOnce(source));
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () =>
      result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'Original draft',
        variables: { learnerName: 'Ada' },
      }),
    );
    act(() => {
      sources[0].listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      sources[0].listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
      result.current.onVariableChange('answer', 'old choice');
    });
    mockGetCurrentMdflow.mockReturnValue('Edited draft');
    await act(async () => {
      result.current.onSend({} as OnSendContentParams, 'old-question');
    });
    const restarted = JSON.parse((SSE as jest.Mock).mock.calls[1][1].payload);
    expect(restarted.content).toBe('Edited draft');
    expect(restarted.variables).toEqual({ learnerName: 'Ada' });
    expect(restarted.user_input).toBeUndefined();

    act(() => {
      sources[1].listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      sources[1].listeners.message?.({
        data: JSON.stringify({
          type: 'interaction',
          generated_block_bid: 'new-question',
          content: '?[answer]',
        }),
      });
      sources[1].listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
      jest.advanceTimersByTime(1000);
      result.current.onVariableChange('answer', 'new choice');
    });
    expect(SSE).toHaveBeenCalledTimes(2);
    await act(async () => result.current.onRefresh('question'));
    const refreshed = JSON.parse((SSE as jest.Mock).mock.calls[2][1].payload);
    expect(refreshed.variables).toEqual({ learnerName: 'Ada' });
    expect(refreshed.user_input).toBeUndefined();
  });

  test('drops stale interaction user input when continuation has no submission', () => {
    expect(
      buildInteractionContinuationPreviewParams({
        currentParams: {
          shifuBid: 'shifu-1',
          outlineBid: 'lesson-1',
          mdflow: 'old prompt',
          block_index: 1,
          user_input: { oldVar: ['old'] },
        },
        latestMdflow: 'new prompt',
        blockIndex: 2,
        variables: {},
      }),
    ).toEqual({
      shifuBid: 'shifu-1',
      outlineBid: 'lesson-1',
      mdflow: 'new prompt',
      block_index: 2,
      variables: {},
    });
  });

  test('replaces loading placeholder with backend business error message', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'loading',
        generated_block_bid: 'loading',
        content: '',
        type: ChatContentItemType.CONTENT,
      },
    ];

    expect(
      replacePreviewLoadingWithBusinessError(
        items,
        '积分余额不足，暂时无法继续调用，请先开通订阅或购买积分',
      ),
    ).toEqual([
      buildPreviewBusinessErrorItem(
        '积分余额不足，暂时无法继续调用，请先开通订阅或购买积分',
      ),
    ]);
  });

  test('preserves existing preview items and appends one business error row', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'content-1',
        generated_block_bid: 'content-1',
        content: 'Existing content',
        type: ChatContentItemType.CONTENT,
      },
      {
        element_bid: 'loading',
        generated_block_bid: 'loading',
        content: '',
        type: ChatContentItemType.CONTENT,
      },
    ];

    expect(replacePreviewLoadingWithBusinessError(items, '余额不足')).toEqual([
      items[0],
      buildPreviewBusinessErrorItem('余额不足'),
    ]);
  });

  test('keeps the preview business code on the rendered error row', () => {
    expect(
      buildPreviewBusinessErrorItem('积分不足，请稍后重试', 7101),
    ).toMatchObject({
      element_bid: 'preview-business-error',
      generated_block_bid: 'preview-business-error',
      content: '积分不足，请稍后重试',
      type: ChatContentItemType.ERROR,
      business_code: 7101,
    });
  });

  test('shows one friendly toast when preview business fallback reports an AI service error', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);
    let handledError:
      | ((error: { message: string; code: number }) => void)
      | undefined;
    (attachSseBusinessResponseFallback as jest.Mock).mockImplementationOnce(
      (_source, options) => {
        handledError = options.onHandled;
      },
    );

    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'prompt',
      });
    });

    expect(attachSseBusinessResponseFallback).toHaveBeenCalledWith(
      source,
      expect.objectContaining({
        meta: expect.objectContaining({
          skipErrorToast: true,
          creditInsufficientAudience: 'teacher',
        }),
      }),
    );

    act(() => {
      handledError?.({
        code: 500,
        message: '模型 deepseek 调用失败：provider unavailable',
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('module.preview.aiDebugUnavailable');
    });
    expect(toast).not.toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringContaining('deepseek'),
      }),
    );
    expect(toastOnce).toHaveBeenCalledWith(
      expect.objectContaining({
        dedupeKey: 'ai-service-unavailable',
        title: 'module.preview.aiDebugUnavailable',
        variant: 'destructive',
        duration: 8000,
      }),
    );
    expect(result.current.items.at(-1)).toMatchObject({
      content: 'module.preview.aiDebugUnavailable',
      type: ChatContentItemType.ERROR,
      business_code: 500,
    });

    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({
          type: 'content',
          generated_block_bid: 'late-block',
          content: 'late content should be ignored',
        }),
      });
    });

    expect(result.current.items).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          generated_block_bid: 'late-block',
        }),
      ]),
    );
  });

  test('uses the collaborator message without a purchase action for owner credit errors', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);
    let handledError:
      | ((error: { message: string; code: number }) => void)
      | undefined;
    (attachSseBusinessResponseFallback as jest.Mock).mockImplementationOnce(
      (_source, options) => {
        handledError = options.onHandled;
      },
    );

    const { result } = renderHook(() =>
      usePreviewChat({
        creditInsufficientAudience: 'teacher-collaborator',
      }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'prompt',
      });
    });

    expect(attachSseBusinessResponseFallback).toHaveBeenCalledWith(
      source,
      expect.objectContaining({
        meta: expect.objectContaining({
          creditInsufficientAudience: 'teacher-collaborator',
        }),
      }),
    );

    act(() => {
      handledError?.({
        code: 7101,
        message: 'backend credit message',
      });
    });

    const collaboratorMessage = getCreditInsufficientMessage(
      'teacher-collaborator',
      7101,
    );
    await waitFor(() => {
      expect(result.current.error).toBe(collaboratorMessage);
    });
    expect(result.current.items.at(-1)).toMatchObject({
      content: collaboratorMessage,
      type: ChatContentItemType.ERROR,
      business_code: 7101,
    });
    expect(toastOnce).toHaveBeenCalledWith(
      expect.objectContaining({
        dedupeKey: 'credit-insufficient:teacher-collaborator:7101',
        action: undefined,
      }),
    );
  });

  test.each(['content', 'data'] as const)(
    'reads credit codes from serialized SSE %s payloads',
    async payloadField => {
      const source = buildMockSseSource();
      (SSE as jest.Mock).mockReturnValueOnce(source);
      const ownerMessage = getCreditInsufficientMessage('teacher', 7101);

      const { result } = renderHook(() =>
        usePreviewChat({ creditInsufficientAudience: 'teacher' }),
      );

      await act(async () => {
        await result.current.startPreview({
          shifuBid: 'shifu-1',
          outlineBid: 'lesson-1',
          mdflow: 'prompt',
        });
      });

      act(() => {
        source.listeners.message?.({
          data: JSON.stringify({
            type: 'error',
            [payloadField]: JSON.stringify({
              code: 7101,
              message: 'serialized backend credit error',
            }),
          }),
        });
      });

      await waitFor(() => expect(result.current.error).toBe(ownerMessage));
      expect(result.current.items.at(-1)).toMatchObject({
        content: ownerMessage,
        type: ChatContentItemType.ERROR,
        business_code: 7101,
      });
      expect(toastOnce).toHaveBeenCalledWith(
        expect.objectContaining({
          dedupeKey: 'credit-insufficient:teacher:7101',
          action: expect.anything(),
        }),
      );
    },
  );

  test('shows friendly content when preview SSE error exposes Langfuse details', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);

    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'prompt',
      });
    });

    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({
          type: 'error',
          content: "'Langfuse' object has no attribute 'start_span'",
        }),
      });
    });

    await waitFor(() => {
      expect(result.current.error).toBe('module.preview.aiDebugUnavailable');
    });
    expect(toast).not.toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringContaining('Langfuse'),
      }),
    );
    expect(toastOnce).toHaveBeenCalledWith(
      expect.objectContaining({
        dedupeKey: 'ai-service-unavailable',
        title: 'module.preview.aiDebugUnavailable',
        variant: 'destructive',
        duration: 8000,
      }),
    );
    expect(result.current.items).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          generated_block_bid: 'loading',
        }),
      ]),
    );
    expect(result.current.items.at(-1)).toMatchObject({
      content: 'module.preview.aiDebugUnavailable',
      type: ChatContentItemType.ERROR,
    });

    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({
          type: 'content',
          generated_block_bid: 'late-langfuse-block',
          content: 'late content should be ignored',
        }),
      });
    });

    expect(result.current.items).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          generated_block_bid: 'late-langfuse-block',
        }),
      ]),
    );
  });

  test('replaces the loading placeholder when preview closes before content', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);

    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'prompt',
      });
    });

    expect(result.current.items.at(-1)).toMatchObject({
      generated_block_bid: 'loading',
    });

    act(() => {
      source.listeners.error?.({});
    });

    await waitFor(() => {
      expect(result.current.error).toBe('module.preview.streamError');
    });
    expect(result.current.items).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          generated_block_bid: 'loading',
        }),
      ]),
    );
    expect(result.current.items.at(-1)).toMatchObject({
      content: 'module.preview.streamError',
      type: ChatContentItemType.ERROR,
    });
  });

  test('keeps successful final content when preview closes before done', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);

    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'prompt',
        max_block_count: 1,
      });
    });

    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({
          type: 'content',
          generated_block_bid: 'final-block',
          content: 'Final preview content.',
        }),
      });
    });

    await waitFor(() => {
      expect(result.current.items).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            generated_block_bid: 'final-block',
            content: 'Final preview content.',
            type: ChatContentItemType.CONTENT,
          }),
        ]),
      );
    });

    act(() => {
      source.listeners.error?.({});
    });

    await waitFor(() => {
      expect(result.current.items).not.toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: ChatContentItemType.ERROR,
          }),
        ]),
      );
    });
    expect(result.current.error).toBeNull();
    expect(toast).not.toHaveBeenCalled();
    expect(toastOnce).not.toHaveBeenCalled();
    expect(result.current.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          generated_block_bid: 'final-block',
          content: 'Final preview content.',
          is_final: true,
        }),
      ]),
    );
  });

  test('ignores stale interaction auto-submit after preview reset', async () => {
    jest.useFakeTimers();
    mockParseToRemarkFormat.mockReturnValue({
      variableName: 'answer',
      placeholder: 'Type your answer',
    });
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);

    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'prompt',
        variables: { answer: 'saved answer' },
      });
    });

    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({
          type: 'interaction',
          generated_block_bid: 'old-interaction',
          content: '?[answer]',
        }),
      });
    });

    act(() => {
      result.current.resetPreview();
      jest.advanceTimersByTime(1000);
    });

    expect(SSE).toHaveBeenCalledTimes(1);
    expect(result.current.items).toEqual([]);
  });

  test('ignores stale interaction auto-submit after a new preview starts', async () => {
    jest.useFakeTimers();
    mockParseToRemarkFormat.mockReturnValue({
      variableName: 'answer',
      placeholder: 'Type your answer',
    });
    const oldSource = buildMockSseSource();
    const newSource = buildMockSseSource();
    (SSE as jest.Mock)
      .mockReturnValueOnce(oldSource)
      .mockReturnValueOnce(newSource);

    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'old prompt',
        variables: { answer: 'saved answer' },
      });
    });

    act(() => {
      oldSource.listeners.message?.({
        data: JSON.stringify({
          type: 'interaction',
          generated_block_bid: 'old-interaction',
          content: '?[answer]',
        }),
      });
    });

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'new prompt',
        variables: {},
      });
    });
    act(() => {
      jest.advanceTimersByTime(1000);
    });

    expect(SSE).toHaveBeenCalledTimes(2);
    expect(newSource.stream).toHaveBeenCalledTimes(1);
  });

  test('ignores stale preview audio callbacks after preview reset', async () => {
    const previewSource = buildMockSseSource();
    const ttsSource = buildMockSseSource();
    (SSE as jest.Mock)
      .mockReturnValueOnce(previewSource)
      .mockReturnValueOnce(ttsSource);

    const { result } = renderHook(() =>
      usePreviewChat({
        creditInsufficientAudience: 'teacher-collaborator',
      }),
    );

    await act(async () => {
      await result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'prompt',
      });
    });

    act(() => {
      previewSource.listeners.message?.({
        data: JSON.stringify({
          type: 'content',
          generated_block_bid: 'audio-block',
          content: 'Audio text.',
        }),
      });
    });

    act(() => {
      void result.current.requestAudioForBlock({
        shifuBid: 'shifu-1',
        blockId: 'audio-block',
        text: 'Audio text.',
      });
    });

    await waitFor(() => {
      expect(ttsSource.stream).toHaveBeenCalled();
    });
    expect(attachSseBusinessResponseFallback).toHaveBeenLastCalledWith(
      ttsSource,
      expect.objectContaining({
        meta: expect.objectContaining({
          creditInsufficientAudience: 'teacher-collaborator',
        }),
      }),
    );
    expect(result.current.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          generated_block_bid: 'audio-block',
          isAudioStreaming: true,
        }),
      ]),
    );

    act(() => {
      result.current.resetPreview();
      ttsSource.listeners.message?.({
        data: JSON.stringify({
          type: 'audio_complete',
          content: {
            audio_url: 'https://example.com/stale.mp3',
            duration_ms: 1000,
          },
        }),
      });
      ttsSource.listeners.error?.({});
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('drops the loading placeholder without appending an empty error row', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'content-1',
        generated_block_bid: 'content-1',
        content: 'Existing content',
        type: ChatContentItemType.CONTENT,
      },
      {
        element_bid: 'loading',
        generated_block_bid: 'loading',
        content: '',
        type: ChatContentItemType.CONTENT,
      },
    ];

    expect(replacePreviewLoadingWithBusinessError(items, '   ')).toEqual([
      items[0],
    ]);
  });
});

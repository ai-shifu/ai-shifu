import { act, renderHook, waitFor } from '@testing-library/react';
import { SSE } from 'sse.js';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { toast, toastOnce } from '@/hooks/useToast';
import { attachSseBusinessResponseFallback } from '@/lib/request';
import {
  buildInteractionContinuationPreviewParams,
  buildPreviewBusinessErrorItem,
  replacePreviewLoadingWithBusinessError,
  usePreviewChat,
} from './usePreviewChat';

const mockParseToRemarkFormat = jest.fn();

jest.mock('sse.js', () => ({
  SSE: jest.fn(),
}));

jest.mock('remark-flow', () => ({
  createInteractionParser: () => ({
    parseToRemarkFormat: mockParseToRemarkFormat,
  }),
}));

jest.mock('@/c-api/studyV2', () => ({
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
    useShifu: () => ({
      actions: {},
    }),
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

jest.mock('@/c-utils/envUtils', () => ({
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

jest.mock('@/c-utils/markdownUtils', () => ({
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

    const { result } = renderHook(() => usePreviewChat());

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

  test('shows friendly content when preview SSE error exposes Langfuse details', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValueOnce(source);

    const { result } = renderHook(() => usePreviewChat());

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

    const { result } = renderHook(() => usePreviewChat());

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

    const { result } = renderHook(() => usePreviewChat());

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

    const { result } = renderHook(() => usePreviewChat());

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

    const { result } = renderHook(() => usePreviewChat());

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

    const { result } = renderHook(() => usePreviewChat());

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

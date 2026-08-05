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

jest.mock('sse.js', () => ({
  SSE: jest.fn(),
}));

jest.mock('remark-flow', () => ({
  createInteractionParser: () => ({
    parseToRemarkFormat: jest.fn(),
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
    (SSE as jest.Mock).mockImplementationOnce(() => source);
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
        meta: expect.objectContaining({ skipErrorToast: true }),
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
  });

  test('shows friendly content when preview SSE error exposes Langfuse details', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockImplementationOnce(() => source);

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

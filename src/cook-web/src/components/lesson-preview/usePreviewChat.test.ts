import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import {
  buildInteractionContinuationPreviewParams,
  buildPreviewBusinessErrorItem,
  replacePreviewLoadingWithBusinessError,
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
});

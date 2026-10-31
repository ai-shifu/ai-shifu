import { createElement, StrictMode } from 'react';
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from '@testing-library/react';
import AudioPlayer from '@/components/audio/AudioPlayer';
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
let mockRequestLanguage = 'en-US';

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('sse.js', () => ({
  SSE: jest.fn(),
}));

jest.mock('remark-flow', () => ({
  ...jest.requireActual('remark-flow/dist/variable-name'),
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
  getCurrentLanguageHeaders: () => ({ 'Accept-Language': mockRequestLanguage }),
}));

jest.mock('@/lib/request-trace', () => ({
  buildTraceHeaders: jest.fn((headers = {}) => ({
    headers,
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
    mockRequestLanguage = 'en-US';
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

  test('stops after a terminal 2.0 debug turn without requesting another block', async () => {
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
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      source.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
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
        engine: 'v2',
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

  test('sends the current interface language on each preview request', async () => {
    (SSE as jest.Mock).mockImplementation(buildMockSseSource);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    const params = {
      shifuBid: 'course',
      outlineBid: 'lesson',
      mdflow: 'Draft',
    };
    for (const language of ['zh-CN', 'en-US', 'fr-FR']) {
      mockRequestLanguage = language;
      await act(async () => result.current.startPreview(params));
      const options = (SSE as jest.Mock).mock.lastCall[1];
      expect(options.headers['Accept-Language']).toBe(language);
      expect(JSON.parse(options.payload).variables).toEqual({});
    }
  });

  test('keeps canonical language edits on restart without changing a course language variable', async () => {
    const sources: MockSseSource[] = [];
    (SSE as jest.Mock).mockImplementation(() => {
      const source = buildMockSseSource();
      sources.push(source);
      return source;
    });
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    const finish = () => {
      const source = sources[sources.length - 1];
      source.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      source.listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
    };
    await act(async () =>
      result.current.startPreview({
        shifuBid: 'course',
        outlineBid: 'lesson',
        mdflow: 'Draft',
        variables: {
          sys_user_language: 'zh-CN',
          language: 'Python',
          nickname: 'Ada',
        },
      }),
    );
    act(finish);
    for (const language of ['en-US', 'fr-FR', '']) {
      act(() => {
        result.current.onVariableChange('sys_user_language', language);
        result.current.onVariableChange('answer', 'old answer');
      });
      expect(result.current.variables).toMatchObject({
        sys_user_language: language,
        language: 'Python',
      });
      await act(async () => result.current.onRefresh());
      const request = JSON.parse((SSE as jest.Mock).mock.lastCall[1].payload);
      expect(request.variables).toEqual({
        sys_user_language: language,
        language: 'Python',
        nickname: 'Ada',
      });
      expect(request.user_input).toBeUndefined();
      expect(request.debug_session_id).not.toBe(
        JSON.parse((SSE as jest.Mock).mock.calls[sources.length - 2][1].payload)
          .debug_session_id,
      );
      act(finish);
    }
  });

  test('treats edits to a course language variable as ordinary answers', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockImplementation(() => source);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    await act(async () =>
      result.current.startPreview({
        shifuBid: 'course',
        outlineBid: 'lesson',
        mdflow: 'Draft',
        variables: { sys_user_language: 'fr-FR', language: 'Python' },
      }),
    );
    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
      result.current.onVariableChange('language', 'TypeScript');
    });
    expect(result.current.variables).toEqual({
      sys_user_language: 'fr-FR',
      language: 'TypeScript',
    });
    await act(async () => result.current.onRefresh());
    const request = JSON.parse((SSE as jest.Mock).mock.lastCall[1].payload);
    expect(request.variables).toEqual({
      sys_user_language: 'fr-FR',
      language: 'Python',
    });
  });

  test('does not introduce a legacy language field when editing the visible language', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockImplementation(() => source);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    await act(async () =>
      result.current.startPreview({
        shifuBid: 'course',
        outlineBid: 'lesson',
        mdflow: 'Draft',
        variables: { sys_user_language: '' },
      }),
    );
    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      source.listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
      result.current.onVariableChange('sys_user_language', 'fr-FR');
    });
    expect(result.current.variables).toEqual({ sys_user_language: 'fr-FR' });
    await act(async () => result.current.onRefresh());
    const request = JSON.parse((SSE as jest.Mock).mock.lastCall[1].payload);
    expect(request.variables).toEqual({ sys_user_language: 'fr-FR' });
  });

  test('lets a restarted 2.0 debug session answer a question with a saved variable', async () => {
    jest.useFakeTimers();
    mockParseToRemarkFormat.mockImplementation((content: string) => ({
      variableName: content.includes('multiAnswer') ? 'multiAnswer' : 'answer',
      buttonTexts: ['old choice', 'new choice'],
      buttonValues: ['old choice', 'new choice'],
      isMultiSelect: content.includes('multiAnswer'),
    }));
    const firstSource = buildMockSseSource();
    const answerSource = buildMockSseSource();
    const multiAnswerSource = buildMockSseSource();
    (SSE as jest.Mock)
      .mockReturnValueOnce(firstSource)
      .mockReturnValueOnce(answerSource)
      .mockReturnValueOnce(multiAnswerSource);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );

    await act(async () =>
      result.current.startPreview({
        shifuBid: 'shifu-1',
        outlineBid: 'lesson-1',
        mdflow: 'Ask for an answer',
        variables: { answer: 'old choice', multiAnswer: 'old choice' },
        max_block_count: 3,
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
            generated_block_bid: '68bbca55db4b4134a5502a641aa0ca04',
            element_type: 'interaction',
            content: '?[answer]',
          },
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
    expect(result.current.variables.answer).toBeUndefined();
    expect(result.current.variables.multiAnswer).toBe('old choice');

    await act(async () =>
      result.current.onSend(
        { variableName: '  answer  ', selectedValues: ['new choice'] },
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
    expect(result.current.variables['  answer  ']).toBeUndefined();
    expect(result.current.variables.answer).toBe('new choice');
    expect(answerRequest.block_index).toBe(0);

    act(() => {
      answerSource.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      answerSource.listeners.message?.({
        data: JSON.stringify({
          type: 'element',
          content: {
            element_bid: 'question-2',
            generated_block_bid: '4fcd3bed69243efa27a031be6c435c0',
            element_type: 'interaction',
            content: '?[multiAnswer]',
          },
        }),
      });
      answerSource.listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
    });
    expect(result.current.variables.multiAnswer).toBeUndefined();
    expect(
      result.current.items.find(item => item.element_bid === 'question-2'),
    ).toMatchObject({ user_input: '' });

    await act(async () =>
      result.current.onSend(
        { variableName: 'multiAnswer', selectedValues: ['new choice'] },
        'question-2',
      ),
    );
    expect(SSE).toHaveBeenCalledTimes(3);
    const multiAnswerRequest = JSON.parse(
      (SSE as jest.Mock).mock.calls[2][1].payload,
    );
    expect(multiAnswerRequest.user_input).toEqual({
      multiAnswer: ['new choice'],
    });
    expect(multiAnswerRequest.block_index).toBe(0);
  });

  test('still sends a debug session ID when browser cryptography is unavailable', async () => {
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
      // The preview API refuses requests without one.
      expect(payload.debug_session_id).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
    } finally {
      if (cryptoProperty) {
        Object.defineProperty(globalThis, 'crypto', cryptoProperty);
      }
    }
  });

  test('keeps the debug session and answer until a run of it has started streaming', async () => {
    (SSE as jest.Mock).mockImplementation(buildMockSseSource);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    const params = {
      shifuBid: 'shifu-1',
      outlineBid: 'lesson-1',
      mdflow: 'Original draft',
      block_index: 1,
      variables: { learnerName: 'Ada', answer: 'saved choice' },
      user_input: { answer: ['saved choice'] },
    };

    await act(async () => result.current.startPreview(params));
    await act(async () =>
      result.current.startPreview({ ...params, mdflow: 'Edited draft' }),
    );

    const first = JSON.parse((SSE as jest.Mock).mock.calls[0][1].payload);
    const second = JSON.parse((SSE as jest.Mock).mock.calls[1][1].payload);
    for (const request of [first, second]) {
      expect(request.block_index).toBe(1);
      expect(request.variables).toEqual(params.variables);
      expect(request.user_input).toEqual(params.user_input);
    }
    expect(first.content).toBe('Original draft');
    expect(second.content).toBe('Edited draft');
    expect(second.debug_session_id).toBe(first.debug_session_id);
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
    await act(async () => result.current.onRefresh());
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

  test.each([
    'error-message',
    'partial-error',
    'done-message',
    'transport-error',
    'early-close',
  ])('ends audio loading and allows retry after %s', async outcome => {
    const previewSource = buildMockSseSource();
    const failedSource = buildMockSseSource();
    const retrySource = buildMockSseSource();
    (SSE as jest.Mock)
      .mockReturnValueOnce(previewSource)
      .mockReturnValueOnce(failedSource)
      .mockReturnValueOnce(retrySource);
    const { result } = renderHook(() =>
      usePreviewChat({ creditInsufficientAudience: 'teacher' }),
    );
    await act(async () =>
      result.current.startPreview({
        shifuBid: 'course',
        outlineBid: 'lesson',
        mdflow: 'Draft',
      }),
    );
    act(() =>
      previewSource.listeners.message?.({
        data: JSON.stringify({
          type: 'content',
          generated_block_bid: 'audio',
          content: 'Speak this.',
        }),
      }),
    );
    let failed: Promise<unknown>;
    act(() => {
      failed = result.current
        .requestAudioForBlock({
          shifuBid: 'course',
          blockId: 'audio',
          text: 'Speak this.',
        })
        .catch(error => error);
    });
    await waitFor(() => expect(failedSource.stream).toHaveBeenCalled());
    await act(async () => {
      if (outcome === 'partial-error') {
        failedSource.listeners.message?.({
          data: JSON.stringify({
            type: 'audio_segment',
            content: { segment_index: 0, audio_data: 'YQ==', duration_ms: 10 },
          }),
        });
      }
      if (outcome === 'transport-error') failedSource.listeners.error?.({});
      else if (outcome === 'early-close')
        failedSource.listeners.readystatechange?.({ readyState: 2 } as never);
      else
        failedSource.listeners.message?.({
          data: JSON.stringify({
            type: outcome === 'done-message' ? 'done' : 'error',
            content: 'Provider unavailable',
          }),
        });
    });
    expect(
      result.current.items.find(item => item.generated_block_bid === 'audio')
        ?.isAudioStreaming,
    ).toBe(false);
    if (outcome === 'partial-error') {
      expect(
        result.current.items.find(item => item.generated_block_bid === 'audio')
          ?.audioTracks,
      ).toEqual([]);
    }
    expect(failedSource.close).toHaveBeenCalledTimes(1);
    expect(await failed!).toBeInstanceOf(Error);
    let retry: Promise<unknown>;
    act(() => {
      retry = result.current.requestAudioForBlock({
        shifuBid: 'course',
        blockId: 'audio',
        text: 'Speak this.',
      });
    });
    await waitFor(() => expect(retrySource.stream).toHaveBeenCalled());
    await act(async () => {
      retrySource.listeners.message?.({
        data: JSON.stringify({
          type: 'audio_complete',
          content: {
            audio_url: 'https://example.com/audio.mp3',
            duration_ms: 1000,
          },
        }),
      });
      retrySource.listeners.readystatechange?.({ readyState: 2 } as never);
      await retry!;
    });
    expect(
      result.current.items.find(item => item.generated_block_bid === 'audio')
        ?.isAudioStreaming,
    ).toBe(false);
  });

  test('a real player requests fresh synthesis after a partial stream fails', async () => {
    const sources: MockSseSource[] = [];
    (SSE as jest.Mock).mockImplementation(() => {
      const source = buildMockSseSource();
      sources.push(source);
      return source;
    });
    let preview!: ReturnType<typeof usePreviewChat>;
    function Harness() {
      preview = usePreviewChat({ creditInsufficientAudience: 'teacher' });
      const track = preview.items.find(
        item => item.generated_block_bid === 'audio',
      )?.audioTracks?.[0];
      return createElement(AudioPlayer, {
        alwaysVisible: true,
        audioUrl: track?.audioUrl,
        streamingSegments: track?.audioSegments,
        isStreaming: track?.isAudioStreaming,
        onRequestAudio: () =>
          preview.requestAudioForBlock({
            shifuBid: 'course',
            blockId: 'audio',
            text: 'Speak this.',
          }),
      });
    }
    const consoleError = jest
      .spyOn(console, 'error')
      .mockImplementation(() => {});
    try {
      render(createElement(Harness));
      await act(async () =>
        preview.startPreview({
          shifuBid: 'course',
          outlineBid: 'lesson',
          mdflow: 'Draft',
        }),
      );
      act(() =>
        sources[0].listeners.message?.({
          data: JSON.stringify({
            type: 'content',
            generated_block_bid: 'audio',
            content: 'Speak this.',
          }),
        }),
      );
      fireEvent.click(
        screen.getByRole('button', { name: 'module.chat.playAudio' }),
      );
      await waitFor(() => expect(sources).toHaveLength(2));
      await act(async () =>
        sources[1].listeners.message?.({
          data: JSON.stringify({
            type: 'audio_segment',
            content: { segment_index: 0, audio_data: 'YQ==', duration_ms: 10 },
          }),
        }),
      );
      expect(
        preview.items.find(item => item.generated_block_bid === 'audio')
          ?.audioTracks?.[0].audioSegments,
      ).toHaveLength(1);
      await act(async () =>
        sources[1].listeners.message?.({
          data: JSON.stringify({
            type: 'error',
            content: 'Provider unavailable',
          }),
        }),
      );
      fireEvent.click(
        screen.getByRole('button', { name: 'module.chat.playAudio' }),
      );
      await waitFor(() => expect(sources).toHaveLength(3));
      expect(JSON.parse((SSE as jest.Mock).mock.lastCall[1].payload)).toEqual({
        text: 'Speak this.',
      });
      await act(async () => sources[2].listeners.error?.({}));
    } finally {
      consoleError.mockRestore();
    }
  });

  test.each(['stop', 'reset', 'unmount'])(
    'settles pending audio when the preview is stopped by %s',
    async action => {
      const sources: MockSseSource[] = [];
      (SSE as jest.Mock).mockImplementation(() => {
        const source = buildMockSseSource();
        sources.push(source);
        return source;
      });
      const { result, unmount } = renderHook(() =>
        usePreviewChat({ creditInsufficientAudience: 'teacher' }),
      );
      await act(async () =>
        result.current.startPreview({
          shifuBid: 'course',
          outlineBid: 'lesson',
          mdflow: 'Draft',
        }),
      );
      act(() =>
        sources[0].listeners.message?.({
          data: JSON.stringify({
            type: 'content',
            generated_block_bid: 'audio',
            content: 'Speak this.',
          }),
        }),
      );
      let failure: Error | undefined;
      act(() => {
        void result.current
          .requestAudioForBlock({
            shifuBid: 'course',
            blockId: 'audio',
            text: 'Speak this.',
          })
          .catch(error => {
            failure = error;
          });
      });
      await waitFor(() => expect(sources).toHaveLength(2));
      await act(async () => {
        if (action === 'unmount') unmount();
        else if (action === 'reset') result.current.resetPreview();
        else result.current.stopPreview();
      });
      expect(failure?.name).toBe('AbortError');
      expect(sources[1].close).toHaveBeenCalledTimes(1);
      if (action === 'reset') expect(result.current.items).toEqual([]);
      if (action !== 'stop') return;
      expect(
        result.current.items.find(item => item.generated_block_bid === 'audio')
          ?.isAudioStreaming,
      ).toBe(false);
      act(() => {
        void result.current
          .requestAudioForBlock({
            shifuBid: 'course',
            blockId: 'audio',
            text: 'Speak this.',
          })
          .catch(() => undefined);
      });
      await waitFor(() => expect(sources).toHaveLength(3));
      act(() => {
        sources[1].listeners.message?.({
          data: JSON.stringify({
            type: 'audio_complete',
            content: {
              audio_url: 'https://example.com/stale.mp3',
              duration_ms: 1000,
            },
          }),
        });
        sources[1].listeners.error?.({});
      });
      expect(
        result.current.items.find(item => item.generated_block_bid === 'audio')
          ?.isAudioStreaming,
      ).toBe(true);
      expect(sources[2].close).not.toHaveBeenCalled();
      await act(async () => sources[2].listeners.error?.({}));
    },
  );

  test('keeps batched variable edits consistent with the next request in StrictMode', async () => {
    const source = buildMockSseSource();
    (SSE as jest.Mock).mockReturnValue(source);
    const { result } = renderHook(
      () => usePreviewChat({ creditInsufficientAudience: 'teacher' }),
      { wrapper: StrictMode },
    );
    await act(async () =>
      result.current.startPreview({
        shifuBid: 'course',
        outlineBid: 'lesson',
        mdflow: 'Draft',
        variables: { sys_user_language: 'en-US', nickname: 'Ada' },
      }),
    );
    act(() => {
      source.listeners.message?.({
        data: JSON.stringify({ type: 'preview_engine', content: '2.0' }),
      });
      source.listeners.message?.({
        data: JSON.stringify({
          type: 'content',
          generated_block_bid: 'question',
          content: 'Continue?',
        }),
      });
      source.listeners.message?.({
        data: JSON.stringify({ type: 'done', is_terminal: true }),
      });
      result.current.onVariableChange('sys_user_language', 'fr-FR');
      result.current.onVariableChange('nickname', 'Alex');
    });
    expect(result.current.variables).toEqual({
      sys_user_language: 'fr-FR',
      nickname: 'Alex',
    });
    await act(async () =>
      result.current.onSend({ inputText: 'Continue' }, 'question'),
    );
    expect(SSE).toHaveBeenCalledTimes(2);
    expect(
      JSON.parse((SSE as jest.Mock).mock.lastCall[1].payload).variables,
    ).toEqual({ sys_user_language: 'fr-FR', nickname: 'Alex' });
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
      void result.current
        .requestAudioForBlock({
          shifuBid: 'shifu-1',
          blockId: 'audio-block',
          text: 'Audio text.',
        })
        .catch(() => undefined);
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

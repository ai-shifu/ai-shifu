import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { toast } from '@/hooks/useToast';
import useChatLogicHook, { ChatContentItemType } from './useChatLogicHook';
import { AppContext } from '../AppContext';
import { SSE_INPUT_TYPE, SSE_OUTPUT_TYPE } from '@/c-api/studyV2';
import { stopAllActiveLessonStreams } from '@/app/c/[[...id]]/events';
import { useLessonRunContentStore } from '@/c-store/useLessonRunContentStore';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en-US', changeLanguage: jest.fn() },
    ready: true,
  }),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    t: (key: string) => key,
    language: 'en-US',
    changeLanguage: jest.fn(),
  },
}));

jest.mock('remark-flow', () => ({
  createInteractionParser: jest.fn(() => ({
    parse: jest.fn(),
    parseToRemarkFormat: jest.fn(),
  })),
}));

jest.mock('@/hooks/useToast', () => ({
  show: jest.fn(),
  toast: jest.fn(),
  fail: jest.fn(),
}));

jest.mock('@/c-assets/newchat/light/icon_ask.svg', () => ({
  __esModule: true,
  default: {
    src: '/ask.svg',
  },
}));

declare global {
  var __chatHookMockUpdateUserInfo__: jest.Mock | undefined;

  var __chatHookMockUpdateResetedChapterId__: jest.Mock | undefined;

  var __chatHookMockUpdateResetedLessonId__: jest.Mock | undefined;
}

jest.mock('@/c-store/useCourseStore', () => ({
  useCourseStore: (() => {
    globalThis.__chatHookMockUpdateResetedChapterId__ = jest.fn();
    globalThis.__chatHookMockUpdateResetedLessonId__ = jest.fn();
    const state = {
      resetedLessonId: null as string | null,
      updateResetedChapterId: globalThis.__chatHookMockUpdateResetedChapterId__,
      updateResetedLessonId: globalThis.__chatHookMockUpdateResetedLessonId__,
    };
    return Object.assign(
      (selector?: (store: typeof state) => unknown) =>
        selector ? selector(state) : state,
      {
        subscribe: jest.fn(() => jest.fn()),
      },
    );
  })(),
}));

jest.mock('@/store', () => ({
  useUserStore: (() => {
    globalThis.__chatHookMockUpdateUserInfo__ = jest.fn();
    const state = {
      isLoggedIn: false,
      updateUserInfo: globalThis.__chatHookMockUpdateUserInfo__,
    };
    return Object.assign(
      (selector?: (store: typeof state) => unknown) =>
        selector ? selector(state) : state,
      {
        subscribe: jest.fn(() => jest.fn()),
        getState: jest.fn(() => ({
          getToken: () => '',
          updateUserInfo: globalThis.__chatHookMockUpdateUserInfo__,
        })),
      },
    );
  })(),
}));

const mockGetLessonStudyRecord = jest.fn();
const mockGetRunMessage = jest.fn();
const mockCheckIsRunning = jest.fn();
const mockStreamGeneratedBlockAudio = jest.fn();
const mockSubmitLessonFeedback = jest.fn();

jest.mock('@/c-api/studyV2', () => {
  return {
    BLOCK_TYPE: {
      CONTENT: 'content',
      INTERACTION: 'interaction',
      ASK: 'ask',
      ANSWER: 'answer',
      ERROR: 'error_message',
    },
    ELEMENT_TYPE: {
      CONTENT: 'content',
      INTERACTION: 'interaction',
      ASK: 'ask',
      ANSWER: 'answer',
      ERROR: 'error_message',
    },
    LIKE_STATUS: {
      LIKE: 'like',
      DISLIKE: 'dislike',
      NONE: 'none',
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
      INTERACTION: 'interaction',
      OUTLINE_ITEM_UPDATE: 'outline_item_update',
      HEARTBEAT: 'heartbeat',
      VARIABLE_UPDATE: 'variable_update',
      PROFILE_UPDATE: 'update_user_info',
      AUDIO_SEGMENT: 'audio_segment',
      AUDIO_COMPLETE: 'audio_complete',
      AUDIO_BACKFILL_READY: 'audio_backfill_ready',
      NEW_SLIDE: 'new_slide',
    },
    SYS_INTERACTION_TYPE: {
      PAY: '_sys_pay',
      LOGIN: '_sys_login',
      NEXT_CHAPTER: '_sys_next_chapter',
    },
    LESSON_FEEDBACK_VARIABLE_NAME: 'sys_lesson_feedback_score',
    LESSON_FEEDBACK_INTERACTION_MARKER: '%{{sys_lesson_feedback_score}}',
    getLessonStudyRecord: (...args: unknown[]) =>
      mockGetLessonStudyRecord(...args),
    getRunMessage: (...args: unknown[]) => mockGetRunMessage(...args),
    checkIsRunning: (...args: unknown[]) => mockCheckIsRunning(...args),
    streamGeneratedBlockAudio: (...args: unknown[]) =>
      mockStreamGeneratedBlockAudio(...args),
    submitLessonFeedback: (...args: unknown[]) =>
      mockSubmitLessonFeedback(...args),
  };
});

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

describe('useChatLogicHook stream cleanup', () => {
  let activeRun:
    | {
        source: MockRunSource;
        onMessage: (response: any) => Promise<void> | void;
      }
    | undefined;

  beforeEach(() => {
    jest.clearAllMocks();
    mockStreamGeneratedBlockAudio.mockReset();
    useLessonRunContentStore.getState().clearAll();
    activeRun = undefined;

    mockGetLessonStudyRecord.mockResolvedValue({
      mdflow: '',
      elements: [],
      records: [],
      slides: [],
    });
    mockCheckIsRunning.mockResolvedValue({
      is_running: false,
      running_time: 0,
    });
    mockSubmitLessonFeedback.mockResolvedValue({});

    mockGetRunMessage.mockImplementation(
      (
        _shifuBid: string,
        _outlineBid: string,
        _previewMode: boolean,
        _body: {
          input: string | Record<string, any>;
          input_type: SSE_INPUT_TYPE;
        },
        onMessage: (response: any) => Promise<void> | void,
      ) => {
        const source = new MockRunSource();
        activeRun = {
          source,
          onMessage,
        };
        return source;
      },
    );
  });

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

  const mobileWrapper = ({ children }: { children: React.ReactNode }) => (
    <AppContext.Provider
      value={{
        isLoggedIn: false,
        mobileStyle: true,
        userInfo: null,
        theme: 'light',
        frameLayout: 0,
      }}
    >
      {children}
    </AppContext.Provider>
  );

  const buildBaseParams = () => ({
    shifuBid: 'shifu-1',
    outlineBid: 'lesson-1',
    lessonId: 'lesson-1',
    trackEvent: jest.fn(),
    trackTrailProgress: jest.fn(),
    lessonUpdate: jest.fn(),
    chapterUpdate: jest.fn(),
    updateSelectedLesson: jest.fn(),
    getNextLessonId: jest.fn(() => null),
    scrollToLesson: jest.fn(),
    showOutputInProgressToast: jest.fn(),
    onPayModalOpen: jest.fn(),
    chatBoxBottomRef: { current: document.createElement('div') },
    onGoChapter: jest.fn(),
  });

  it('sends listen=false in the run body when listen requests are disabled', async () => {
    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: false,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockGetRunMessage.mock.calls[0]?.[3]).toEqual(
      expect.objectContaining({
        listen: false,
      }),
    );
  });

  it('sends listen=true in the run body when listen requests are enabled', async () => {
    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: true,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockGetRunMessage.mock.calls[0]?.[3]).toEqual(
      expect.objectContaining({
        listen: true,
      }),
    );
  });

  it('can force listen=true for generated-block audio backfill while the run body uses listen=false', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'content',
          content: 'History content without audio',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
      ],
      slides: [],
      records: [],
    });
    mockStreamGeneratedBlockAudio.mockReturnValue({
      close: jest.fn(),
    });

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: false,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      void result.current.requestAudioForBlock('content-1', { listen: true });
    });

    expect(mockGetRunMessage.mock.calls[0]?.[3]).toEqual(
      expect.objectContaining({
        listen: false,
      }),
    );
    expect(mockStreamGeneratedBlockAudio).toHaveBeenCalledWith(
      expect.objectContaining({
        generated_block_bid: 'content-1',
        listen: true,
      }),
    );
  });

  it('uses generated_block_bid for audio backfill and writes audio to speakable elements by history order', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'text',
          content: 'First history content without audio',
          generated_block_bid: 'generated-block-1',
          element_bid: 'element-1',
          element_index: 0,
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
        {
          element_type: 'html',
          content: '<section>First visual marker</section>',
          generated_block_bid: 'generated-block-1',
          element_bid: 'visual-1',
          element_index: 1,
          like_status: 'none',
          user_input: '',
          is_speakable: false,
          is_renderable: true,
          is_marker: true,
          is_new: false,
        },
        {
          element_type: 'text',
          content: 'Second history content without audio',
          generated_block_bid: 'generated-block-1',
          element_bid: 'element-2',
          element_index: 2,
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
        {
          element_type: 'html',
          content: '<section>Second visual marker</section>',
          generated_block_bid: 'generated-block-1',
          element_bid: 'visual-2',
          element_index: 3,
          like_status: 'none',
          user_input: '',
          is_speakable: false,
          is_renderable: true,
          is_marker: true,
          is_new: false,
        },
        {
          element_type: 'text',
          content: 'Third history content without audio',
          generated_block_bid: 'generated-block-1',
          element_bid: 'element-3',
          element_index: 4,
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
      ],
      slides: [],
      records: [],
    });

    let ttsRequest:
      | {
          onMessage: (response: unknown) => void;
        }
      | undefined;
    const close = jest.fn();
    mockStreamGeneratedBlockAudio.mockImplementation(params => {
      ttsRequest = params;
      return {
        close,
      };
    });

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: false,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const onStreamSettled = jest.fn();
    let audioPromise: Promise<unknown> | undefined;
    let audioPromiseSettled = false;
    act(() => {
      audioPromise = result.current.requestAudioForBlock('element-1', {
        listen: true,
        onStreamSettled,
      });
      audioPromise?.then(
        () => {
          audioPromiseSettled = true;
        },
        () => {
          audioPromiseSettled = true;
        },
      );
    });

    expect(mockStreamGeneratedBlockAudio).toHaveBeenCalledWith(
      expect.objectContaining({
        generated_block_bid: 'generated-block-1',
        listen: true,
      }),
    );

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_SEGMENT,
        content: {
          segment_index: 0,
          audio_data: 'first-streamed-audio',
          duration_ms: 321,
          is_final: false,
          position: 0,
          stream_element_number: 0,
          subtitle_cues: [
            {
              text: '第一段字幕。',
              start_ms: 0,
              end_ms: 321,
              segment_index: 0,
              position: 0,
            },
          ],
        },
      });
    });

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_COMPLETE,
        content: {
          audio_url: 'https://example.com/generated-block-1.mp3',
          audio_bid: 'audio-1',
          duration_ms: 321,
          position: 0,
          stream_element_number: 0,
          subtitle_cues: [
            {
              text: '第一段字幕。',
              start_ms: 0,
              end_ms: 321,
              segment_index: 0,
              position: 0,
            },
          ],
        },
      });
      await Promise.resolve();
    });

    expect(
      result.current.items.find(item => item.element_bid === 'element-1')
        ?.audioUrl,
    ).toBe('https://example.com/generated-block-1.mp3');
    expect(audioPromiseSettled).toBe(false);
    expect(close).not.toHaveBeenCalled();
    expect(onStreamSettled).not.toHaveBeenCalled();

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_COMPLETE,
        content: {
          audio_url: 'https://example.com/generated-block-1-position-1.mp3',
          audio_bid: 'audio-2',
          duration_ms: 654,
          position: 1,
          subtitle_cues: [
            {
              text: '第二段字幕。',
              start_ms: 0,
              end_ms: 654,
              segment_index: 0,
              position: 1,
            },
          ],
        },
      });
    });

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_COMPLETE,
        content: {
          audio_url: 'https://example.com/generated-block-1-position-2.mp3',
          audio_bid: 'audio-3',
          duration_ms: 987,
          position: 2,
          stream_element_number: 99,
          subtitle_cues: [
            {
              text: '第三段字幕。',
              start_ms: 0,
              end_ms: 987,
              segment_index: 0,
              position: 2,
            },
          ],
        },
      });
    });

    const firstElementAudioTracks =
      result.current.items.find(item => item.element_bid === 'element-1')
        ?.audioTracks ?? [];
    expect(firstElementAudioTracks.map(track => track.audioUrl)).toEqual([
      'https://example.com/generated-block-1.mp3',
    ]);
    expect(firstElementAudioTracks[0]?.audioSegments).toEqual([
      expect.objectContaining({
        segmentIndex: 0,
        audioData: 'first-streamed-audio',
        durationMs: 321,
        isFinal: true,
        position: 0,
      }),
    ]);
    expect(firstElementAudioTracks.map(track => track.subtitleCues)).toEqual([
      [
        {
          text: '第一段字幕。',
          start_ms: 0,
          end_ms: 321,
          segment_index: 0,
          position: 0,
        },
      ],
    ]);

    expect(
      result.current.items.find(item => item.element_bid === 'visual-1')
        ?.audioTracks ?? [],
    ).toEqual([]);
    expect(
      result.current.items.find(item => item.element_bid === 'visual-2')
        ?.audioTracks ?? [],
    ).toEqual([]);

    const secondElementAudioTracks =
      result.current.items.find(item => item.element_bid === 'element-2')
        ?.audioTracks ?? [];
    expect(secondElementAudioTracks.map(track => track.audioUrl)).toEqual([
      'https://example.com/generated-block-1-position-1.mp3',
    ]);
    expect(secondElementAudioTracks.map(track => track.subtitleCues)).toEqual([
      [
        {
          text: '第二段字幕。',
          start_ms: 0,
          end_ms: 654,
          segment_index: 0,
          position: 1,
        },
      ],
    ]);

    const thirdElementAudioTracks =
      result.current.items.find(item => item.element_bid === 'element-3')
        ?.audioTracks ?? [];
    expect(thirdElementAudioTracks.map(track => track.audioUrl)).toEqual([
      'https://example.com/generated-block-1-position-2.mp3',
    ]);
    expect(thirdElementAudioTracks.map(track => track.subtitleCues)).toEqual([
      [
        {
          text: '第三段字幕。',
          start_ms: 0,
          end_ms: 987,
          segment_index: 0,
          position: 2,
        },
      ],
    ]);
    expect(close).not.toHaveBeenCalled();

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: true,
      });
      await audioPromise;
    });
    expect(audioPromiseSettled).toBe(true);
    expect(close).toHaveBeenCalled();
    expect(onStreamSettled).toHaveBeenCalledTimes(1);
  });

  it('closes non-listen generated-block audio after the first complete event', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'text',
          content: 'History content without audio',
          generated_block_bid: 'generated-block-manual-1',
          element_bid: 'element-manual-1',
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
      ],
      slides: [],
      records: [],
    });

    let ttsRequest:
      | {
          onMessage: (response: unknown) => void;
        }
      | undefined;
    const close = jest.fn();
    mockStreamGeneratedBlockAudio.mockImplementation(params => {
      ttsRequest = params;
      return {
        close,
      };
    });

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: false,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let audioPromise: Promise<unknown> | undefined;
    act(() => {
      audioPromise = result.current.requestAudioForBlock('element-manual-1');
    });

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_COMPLETE,
        content: {
          audio_url: 'https://example.com/manual.mp3',
          audio_bid: 'manual-audio-1',
          duration_ms: 123,
          position: 0,
        },
      });
      await audioPromise;
    });

    expect(close).toHaveBeenCalled();
  });

  it('starts the listen-mode backfill idle timeout before the first SSE message', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'text',
          content: 'History content without audio',
          generated_block_bid: 'generated-block-idle-1',
          element_bid: 'element-idle-1',
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
      ],
      slides: [],
      records: [],
    });

    const close = jest.fn();
    mockStreamGeneratedBlockAudio.mockReturnValue({
      close,
    });

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: false,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    jest.useFakeTimers();
    try {
      let audioPromise: Promise<unknown> | undefined;
      act(() => {
        audioPromise = result.current.requestAudioForBlock('element-idle-1', {
          listen: true,
        });
      });

      await act(async () => {
        jest.advanceTimersByTime(120000);
        await audioPromise;
      });

      expect(close).toHaveBeenCalled();
    } finally {
      jest.useRealTimers();
    }
  });

  it('closes listen-mode backfill when the result should no longer apply during a segment', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'text',
          content: 'History content without audio',
          generated_block_bid: 'generated-block-stale-1',
          element_bid: 'element-stale-1',
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
      ],
      slides: [],
      records: [],
    });

    let ttsRequest:
      | {
          onMessage: (response: unknown) => void;
        }
      | undefined;
    const close = jest.fn();
    mockStreamGeneratedBlockAudio.mockImplementation(params => {
      ttsRequest = params;
      return {
        close,
      };
    });

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: false,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let shouldApply = true;
    let audioPromise: Promise<unknown> | undefined;
    act(() => {
      audioPromise = result.current.requestAudioForBlock('element-stale-1', {
        listen: true,
        shouldApplyResult: () => shouldApply,
      });
    });

    shouldApply = false;

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_SEGMENT,
        content: {
          segment_index: 0,
          audio_data: 'base64-audio',
          duration_ms: 100,
          is_final: false,
          position: 0,
        },
      });
      await audioPromise;
    });

    expect(close).toHaveBeenCalled();
  });

  it('clears track streaming state when generated-block audio backfill errors', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'text',
          content: 'History content without audio',
          generated_block_bid: 'generated-block-error-1',
          element_bid: 'element-error-1',
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
      ],
      slides: [],
      records: [],
    });

    let ttsRequest:
      | {
          onMessage: (response: unknown) => void;
          onError: () => void;
        }
      | undefined;
    const close = jest.fn();
    mockStreamGeneratedBlockAudio.mockImplementation(params => {
      ttsRequest = params;
      return {
        close,
      };
    });

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: false,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let audioPromise: Promise<unknown> | undefined;
    act(() => {
      audioPromise = result.current
        .requestAudioForBlock('element-error-1', { listen: true })
        .catch(error => error);
    });

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_SEGMENT,
        content: {
          segment_index: 0,
          audio_data: 'base64-audio',
          duration_ms: 100,
          is_final: false,
          position: 0,
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'element-error-1')
        ?.audioTracks?.[0]?.isAudioStreaming,
    ).toBe(true);

    await act(async () => {
      ttsRequest?.onError();
      await audioPromise;
    });

    const erroredItem = result.current.items.find(
      item => item.element_bid === 'element-error-1',
    );
    expect(erroredItem?.isAudioStreaming).toBe(false);
    expect(erroredItem?.audioTracks?.[0]?.isAudioStreaming).toBe(false);
    expect(close).toHaveBeenCalled();
  });

  it('clears generated-block sibling audio streaming state when backfill errors', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'text',
          content: 'First history content without audio',
          generated_block_bid: 'generated-block-error-all-1',
          element_bid: 'element-error-all-1',
          element_index: 0,
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
        {
          element_type: 'text',
          content: 'Second history content without audio',
          generated_block_bid: 'generated-block-error-all-1',
          element_bid: 'element-error-all-2',
          element_index: 1,
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
      ],
      slides: [],
      records: [],
    });

    let ttsRequest:
      | {
          onMessage: (response: unknown) => void;
          onError: () => void;
        }
      | undefined;
    const close = jest.fn();
    mockStreamGeneratedBlockAudio.mockImplementation(params => {
      ttsRequest = params;
      return {
        close,
      };
    });

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          listenRequestEnabled: false,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let audioPromise: Promise<unknown> | undefined;
    act(() => {
      audioPromise = result.current
        .requestAudioForBlock('element-error-all-1', { listen: true })
        .catch(error => error);
    });

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_SEGMENT,
        content: {
          segment_index: 0,
          audio_data: 'second-base64-audio',
          duration_ms: 100,
          is_final: false,
          position: 1,
        },
      });
    });

    expect(
      result.current.items.find(
        item => item.element_bid === 'element-error-all-2',
      )?.audioTracks?.[0]?.isAudioStreaming,
    ).toBe(true);

    await act(async () => {
      ttsRequest?.onError();
      await audioPromise;
    });

    const firstItem = result.current.items.find(
      item => item.element_bid === 'element-error-all-1',
    );
    const secondItem = result.current.items.find(
      item => item.element_bid === 'element-error-all-2',
    );
    expect(firstItem?.isAudioStreaming).toBe(false);
    expect(secondItem?.isAudioStreaming).toBe(false);
    expect(secondItem?.audioTracks?.[0]?.isAudioStreaming).toBe(false);
    expect(close).toHaveBeenCalled();
  });

  it('closes run and generated-block TTS streams on a global stop event', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'text',
          content: 'History content without audio',
          generated_block_bid: 'generated-block-stop-1',
          element_bid: 'element-stop-1',
          element_index: 0,
          like_status: 'none',
          user_input: '',
          is_speakable: true,
          is_renderable: true,
          is_marker: false,
          is_new: false,
        },
      ],
      slides: [],
      records: [],
    });

    let ttsRequest:
      | {
          onMessage: (response: unknown) => void;
        }
      | undefined;
    const closeTtsSource = jest.fn();
    mockStreamGeneratedBlockAudio.mockImplementation(params => {
      ttsRequest = params;
      return {
        close: closeTtsSource,
      };
    });

    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let audioPromise: Promise<unknown> | undefined;
    act(() => {
      audioPromise = result.current.requestAudioForBlock('element-stop-1', {
        listen: true,
      });
    });

    await waitFor(() => expect(ttsRequest).toBeDefined());

    await act(async () => {
      ttsRequest?.onMessage({
        type: SSE_OUTPUT_TYPE.AUDIO_SEGMENT,
        content: {
          segment_index: 0,
          audio_data: 'base64-audio',
          duration_ms: 100,
          is_final: false,
          position: 0,
        },
      });
    });

    await waitFor(() =>
      expect(
        result.current.items.find(item => item.element_bid === 'element-stop-1')
          ?.audioTracks?.[0]?.isAudioStreaming,
      ).toBe(true),
    );

    await act(async () => {
      stopAllActiveLessonStreams();
      await audioPromise;
    });

    expect(activeRun?.source.close).toHaveBeenCalled();
    expect(closeTtsSource).toHaveBeenCalled();
    expect(result.current.isOutputInProgress).toBe(false);

    const stoppedItem = result.current.items.find(
      item => item.element_bid === 'element-stop-1',
    );
    expect(stoppedItem?.isAudioStreaming).toBe(false);
    expect(stoppedItem?.audioTracks?.[0]?.isAudioStreaming).toBe(false);
  });

  it('keeps an active read run open when presentation mode changes', async () => {
    const { result, rerender } = renderHook(
      ({ isListenMode }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          isListenMode,
        }),
      {
        wrapper,
        initialProps: {
          isListenMode: false,
        },
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());
    await waitFor(() => expect(result.current.isOutputInProgress).toBe(true));
    const initialRunCount = mockGetRunMessage.mock.calls.length;
    const activeRunSource = activeRun?.source;

    await act(async () => {
      await activeRun?.onMessage({
        element_bid: 'streaming-content-1',
        generated_block_bid: 'streaming-content-1',
        type: SSE_OUTPUT_TYPE.CONTENT,
        content: 'Read mode text',
      });
    });

    expect(
      result.current.items.find(
        item => item.element_bid === 'streaming-content-1',
      )?.content,
    ).toContain('Read mode text');

    rerender({ isListenMode: true });

    expect(activeRunSource?.close).not.toHaveBeenCalled();
    expect(result.current.isOutputInProgress).toBe(true);
    expect(mockGetRunMessage).toHaveBeenCalledTimes(initialRunCount);

    await act(async () => {
      await activeRun?.onMessage({
        element_bid: 'streaming-content-1',
        generated_block_bid: 'streaming-content-1',
        type: SSE_OUTPUT_TYPE.CONTENT,
        content: ' while listening',
      });
    });

    rerender({ isListenMode: false });
    expect(activeRunSource?.close).not.toHaveBeenCalled();
    expect(mockGetRunMessage).toHaveBeenCalledTimes(initialRunCount);
    expect(
      result.current.items.find(
        item => item.element_bid === 'streaming-content-1',
      )?.content,
    ).toContain('while listening');
  });

  it('clears loading after a control-only stream closes', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());
    await waitFor(() => expect(result.current.isOutputInProgress).toBe(true));
    await waitFor(() =>
      expect(
        result.current.items.some(
          item => item.generated_block_bid === 'loading',
        ),
      ).toBe(true),
    );

    act(() => {
      if (!activeRun) {
        throw new Error('Expected active run source');
      }
      activeRun.source.readyState = 1;
      activeRun?.source.emit('readystatechange');
    });

    await waitFor(() => expect(result.current.isOutputInProgress).toBe(true));

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: '',
        type: SSE_OUTPUT_TYPE.VARIABLE_UPDATE,
        content: {
          variable_name: 'sys_user_nickname',
          variable_value: 'Tester',
        },
      });
    });

    expect(globalThis.__chatHookMockUpdateUserInfo__).toHaveBeenCalledWith({
      name: 'Tester',
    });

    act(() => {
      if (!activeRun) {
        throw new Error('Expected active run source');
      }
      activeRun.source.readyState = 2;
      activeRun.source.emit('readystatechange');
    });

    await waitFor(() =>
      expect(
        result.current.items.some(
          item => item.generated_block_bid === 'loading',
        ),
      ).toBe(false),
    );
    expect(result.current.isOutputInProgress).toBe(false);
  });

  it('keeps lesson feedback popup pending until prompting is allowed', async () => {
    const { result, rerender } = renderHook(
      ({ shouldPromptLessonFeedback }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          shouldPromptLessonFeedback,
        }),
      {
        wrapper,
        initialProps: {
          shouldPromptLessonFeedback: false,
        },
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'feedback-1',
        type: SSE_OUTPUT_TYPE.INTERACTION,
        content: '%{{sys_lesson_feedback_score}}1|2|3|4|5|...comment',
      });
    });

    expect(result.current.lessonFeedbackPopup.open).toBe(false);

    rerender({ shouldPromptLessonFeedback: true });

    await waitFor(() =>
      expect(result.current.lessonFeedbackPopup.open).toBe(true),
    );
    expect(result.current.lessonFeedbackPopup.elementBid).toBe('feedback-1');
  });

  it('hides lesson feedback popup when prompting becomes disallowed', async () => {
    const { result, rerender } = renderHook(
      ({ shouldPromptLessonFeedback }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          shouldPromptLessonFeedback,
        }),
      {
        wrapper,
        initialProps: {
          shouldPromptLessonFeedback: true,
        },
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'feedback-1',
        type: SSE_OUTPUT_TYPE.INTERACTION,
        content: '%{{sys_lesson_feedback_score}}1|2|3|4|5|...comment',
      });
    });

    await waitFor(() =>
      expect(result.current.lessonFeedbackPopup.open).toBe(true),
    );

    rerender({ shouldPromptLessonFeedback: false });

    expect(result.current.lessonFeedbackPopup.open).toBe(false);
    expect(result.current.lessonFeedbackPopup.elementBid).toBe('feedback-1');
  });

  it('closes lesson feedback popup when switching lessons', async () => {
    const { result, rerender } = renderHook(
      ({ outlineBid }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          outlineBid,
          lessonId: outlineBid,
          shouldPromptLessonFeedback: true,
        }),
      {
        wrapper,
        initialProps: {
          outlineBid: 'lesson-1',
        },
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'feedback-1',
        type: SSE_OUTPUT_TYPE.INTERACTION,
        content: '%{{sys_lesson_feedback_score}}1|2|3|4|5|...comment',
      });
    });

    await waitFor(() =>
      expect(result.current.lessonFeedbackPopup.open).toBe(true),
    );

    rerender({ outlineBid: 'lesson-2' });

    expect(result.current.lessonFeedbackPopup.open).toBe(false);
    expect(result.current.lessonFeedbackPopup.elementBid).toBe('');
  });

  it('closes lesson feedback popup when switching learning modes before prompting is allowed again', async () => {
    const { result, rerender } = renderHook(
      ({ isListenMode, shouldPromptLessonFeedback }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          isListenMode,
          shouldPromptLessonFeedback,
        }),
      {
        wrapper,
        initialProps: {
          isListenMode: false,
          shouldPromptLessonFeedback: true,
        },
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'feedback-1',
        type: SSE_OUTPUT_TYPE.INTERACTION,
        content: '%{{sys_lesson_feedback_score}}1|2|3|4|5|...comment',
      });
    });

    await waitFor(() =>
      expect(result.current.lessonFeedbackPopup.open).toBe(true),
    );

    rerender({ isListenMode: true, shouldPromptLessonFeedback: false });

    expect(result.current.lessonFeedbackPopup.open).toBe(false);
    expect(result.current.lessonFeedbackPopup.elementBid).toBe('feedback-1');
  });

  it('reopens pending lesson feedback after switching modes once prompting is allowed again', async () => {
    const { result, rerender } = renderHook(
      ({ isListenMode, shouldPromptLessonFeedback }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          isListenMode,
          shouldPromptLessonFeedback,
        }),
      {
        wrapper,
        initialProps: {
          isListenMode: true,
          shouldPromptLessonFeedback: true,
        },
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'feedback-1',
        type: SSE_OUTPUT_TYPE.INTERACTION,
        content: '%{{sys_lesson_feedback_score}}1|2|3|4|5|...comment',
      });
    });

    await waitFor(() =>
      expect(result.current.lessonFeedbackPopup.open).toBe(true),
    );

    rerender({
      isListenMode: false,
      shouldPromptLessonFeedback: false,
    });

    expect(result.current.lessonFeedbackPopup.open).toBe(false);
    expect(result.current.lessonFeedbackPopup.elementBid).toBe('feedback-1');

    rerender({
      isListenMode: false,
      shouldPromptLessonFeedback: true,
    });

    await waitFor(() =>
      expect(result.current.lessonFeedbackPopup.open).toBe(true),
    );
  });

  it('pushes an error item and shows a destructive toast after the run stream idle timeout', async () => {
    jest.useFakeTimers();

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          isListenMode: true,
        }),
      {
        wrapper,
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    act(() => {
      jest.advanceTimersByTime(15000);
    });

    await waitFor(() =>
      expect(
        result.current.items.some(
          item => item.type === ChatContentItemType.ERROR,
        ),
      ).toBe(true),
    );

    const timeoutErrorItem = result.current.items.find(
      item => item.type === ChatContentItemType.ERROR,
    );

    expect(timeoutErrorItem?.content).toBe('module.chat.streamTimeoutRetry');
    expect(toast).toHaveBeenCalledWith({
      title: 'module.chat.streamTimeoutRetry',
      variant: 'destructive',
    });
    expect(activeRun?.source.close).toHaveBeenCalled();

    jest.useRealTimers();
  });

  it('uses the longer run stream idle timeout on mobile', async () => {
    jest.useFakeTimers();

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          isListenMode: true,
        }),
      {
        wrapper: mobileWrapper,
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    act(() => {
      jest.advanceTimersByTime(15000);
    });

    expect(
      result.current.items.some(
        item => item.type === ChatContentItemType.ERROR,
      ),
    ).toBe(false);
    expect(activeRun?.source.close).not.toHaveBeenCalled();

    act(() => {
      jest.advanceTimersByTime(45000);
    });

    await waitFor(() =>
      expect(
        result.current.items.some(
          item => item.type === ChatContentItemType.ERROR,
        ),
      ).toBe(true),
    );

    expect(activeRun?.source.close).toHaveBeenCalled();

    jest.useRealTimers();
  });

  it('does not auto-open lesson feedback popup for an already rated lesson', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          block_type: 'content',
          content: 'Lesson done',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
        {
          block_type: 'interaction',
          content: '%{{sys_lesson_feedback_score}}1|2|3|4|5|...comment',
          generated_block_bid: 'feedback-1',
          element_bid: 'feedback-1',
          user_input: JSON.stringify({
            score: 4,
            comment: 'Helpful',
          }),
        },
      ],
      slides: [],
      records: [],
    });

    const { result } = renderHook(
      () =>
        useChatLogicHook({
          ...buildBaseParams(),
          shouldPromptLessonFeedback: true,
        }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.lessonFeedbackPopup.open).toBe(false);
    expect(
      result.current.items.some(
        item => item.generated_block_bid === 'feedback-1',
      ),
    ).toBe(true);
  });

  it('maps history ask/answer elements into ask block messages', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'content',
          content: 'course content',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
        {
          element_type: 'ask',
          content: '111',
          generated_block_bid: 'ask-block-1',
          element_bid: 'ask-element-1',
          payload: {
            anchor_element_bid: 'content-1',
          },
        },
        {
          element_type: 'ask',
          content: '1111',
          generated_block_bid: 'ask-block-1',
          element_bid: 'ask-element-1',
          payload: {
            anchor_element_bid: 'content-1',
          },
        },
        {
          element_type: 'answer',
          content: 'hello',
          generated_block_bid: 'answer-block-1',
          element_bid: 'answer-element-1',
          payload: {
            anchor_element_bid: 'content-1',
            ask_element_bid: 'ask-element-1',
          },
        },
        {
          element_type: 'answer',
          content: 'hello world',
          generated_block_bid: 'answer-block-1',
          element_bid: 'answer-element-1',
          payload: {
            anchor_element_bid: 'content-1',
            ask_element_bid: 'ask-element-1',
          },
        },
      ],
      slides: [],
      records: [],
    });

    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const askBlock = result.current.items.find(
      item =>
        item.type === ChatContentItemType.ASK &&
        item.parent_element_bid === 'content-1',
    );
    expect(askBlock).toBeDefined();
    expect(askBlock?.ask_list).toHaveLength(2);
    expect(askBlock?.ask_list?.[0]?.type).toBe('ask');
    expect(askBlock?.ask_list?.[0]?.content).toBe('1111');
    expect(askBlock?.ask_list?.[1]?.type).toBe('answer');
    expect(askBlock?.ask_list?.[1]?.content).toBe('hello world');

    expect(
      result.current.items.some(item => item.element_bid === 'ask-element-1'),
    ).toBe(false);
    expect(
      result.current.items.some(
        item => item.element_bid === 'answer-element-1',
      ),
    ).toBe(false);
  });

  it('keeps ask block collapsed by default on mobile when history ask/answer exists', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'content',
          content: 'course content',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
        {
          element_type: 'ask',
          content: 'follow-up ask',
          generated_block_bid: 'ask-block-1',
          element_bid: 'ask-element-1',
          payload: {
            anchor_element_bid: 'content-1',
          },
        },
        {
          element_type: 'answer',
          content: 'follow-up answer',
          generated_block_bid: 'answer-block-1',
          element_bid: 'answer-element-1',
          payload: {
            anchor_element_bid: 'content-1',
            ask_element_bid: 'ask-element-1',
          },
        },
      ],
      slides: [],
      records: [],
    });

    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper: mobileWrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const askBlock = result.current.items.find(
      item =>
        item.type === ChatContentItemType.ASK &&
        item.parent_element_bid === 'content-1',
    );
    expect(askBlock).toBeDefined();
    expect(askBlock?.isAskExpanded).toBe(false);
  });

  it('keeps canonical history content free of mobile follow-up markup after mode switches', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'content',
          content: 'History lesson summary',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
      ],
      slides: [],
      records: [],
    });

    const { result, rerender } = renderHook(
      ({ isListenMode }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          isListenMode,
        }),
      {
        wrapper: mobileWrapper,
        initialProps: {
          isListenMode: true,
        },
      },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(
      result.current.items.find(item => item.element_bid === 'content-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');

    rerender({ isListenMode: false });

    expect(
      result.current.items.find(item => item.element_bid === 'content-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');
  });

  it('does not inherit history state when run stream updates an existing history element', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'text',
          content: 'History lesson summary',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
      ],
      slides: [],
      records: [],
    });

    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(
      result.current.items.find(item => item.element_bid === 'content-1')
        ?.isHistory,
    ).toBe(true);
    expect(
      result.current.items.find(item => item.element_bid === 'content-1')
        ?.shouldUseTypewriter,
    ).toBe(false);

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_type: 'text',
          content: 'Updated lesson summary',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-1')
        ?.isHistory,
    ).toBeUndefined();
    expect(
      result.current.items.find(item => item.element_bid === 'content-1')
        ?.shouldUseTypewriter,
    ).toBe(false);
  });

  it('finalizes previous mobile content when a new element arrives', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper: mobileWrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-html-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-html-1',
          generated_block_bid: 'content-html-1',
          element_type: 'html',
          content: '<p>HTML block</p>',
          like_status: 'none',
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-html-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-2',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-2',
          generated_block_bid: 'content-text-2',
          element_type: 'text',
          content: 'Text block',
          like_status: 'none',
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-html-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');
    expect(
      result.current.items.find(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS &&
          item.parent_element_bid === 'content-html-1',
      ),
    ).toBeDefined();
    expect(
      result.current.items.find(item => item.element_bid === 'content-text-2')
        ?.content,
    ).not.toContain('<custom-button-after-content>');
  });

  it('marks streamed elements audio-backfill-ready only after the persisted ready event', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'generated-block-ready-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'element-ready-1',
          generated_block_bid: 'generated-block-ready-1',
          element_type: 'text',
          content: 'Persisted later',
          is_speakable: true,
          like_status: 'none',
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'element-ready-1')
        ?.isAudioBackfillReady,
    ).toBeFalsy();

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'generated-block-ready-1',
        type: SSE_OUTPUT_TYPE.AUDIO_BACKFILL_READY,
        content: {
          generated_block_bid: 'generated-block-ready-1',
          element_bids: ['element-ready-1'],
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'element-ready-1')
        ?.isAudioBackfillReady,
    ).toBe(true);
  });

  it('carries streamed visual slides from a generated block to its final element', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        element_bid: 'streaming-block-visual-1',
        generated_block_bid: 'generated-visual-1',
        type: SSE_OUTPUT_TYPE.CONTENT,
        content: 'Generating visual...',
      });
    });

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'generated-visual-1',
        type: SSE_OUTPUT_TYPE.NEW_SLIDE,
        content: {
          slide_id: 'slide-visual-1',
          target_element_bid: 'element-visual-1',
          generated_block_bid: 'generated-visual-1',
          slide_index: 0,
          audio_position: 0,
          visual_kind: 'image',
          segment_type: 'markdown',
          segment_content: '![diagram](https://example.com/diagram.png)',
          source_span: [0, 18],
          is_placeholder: false,
        },
      });
    });

    expect(
      result.current.items.find(
        item => item.generated_block_bid === 'generated-visual-1',
      )?.listenSlides,
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          slide_id: 'slide-visual-1',
          segment_content: '![diagram](https://example.com/diagram.png)',
        }),
      ]),
    );

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'generated-visual-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'streaming-block-visual-1',
          generated_block_bid: 'generated-visual-1',
          element_type: 'text',
          content: '',
          is_renderable: false,
          is_speakable: false,
          is_new: true,
          like_status: 'none',
        },
      });
    });

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'generated-visual-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'element-visual-1',
          generated_block_bid: 'generated-visual-1',
          element_type: 'text',
          content: 'Final visual explanation',
          is_speakable: true,
          like_status: 'none',
        },
      });
    });

    expect(
      result.current.items.find(
        item => item.element_bid === 'streaming-block-visual-1',
      )?.is_renderable,
    ).toBe(false);
    expect(
      result.current.items.find(item => item.element_bid === 'element-visual-1')
        ?.listenSlides,
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          slide_id: 'slide-visual-1',
          generated_block_bid: 'generated-visual-1',
        }),
      ]),
    );
  });

  it('keeps multiple final elements from the same generated block distinct', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        element_bid: 'streaming-multi-1',
        generated_block_bid: 'generated-multi-1',
        type: SSE_OUTPUT_TYPE.CONTENT,
        content: 'Generating visual and text...',
      });
    });

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'generated-multi-1',
        type: SSE_OUTPUT_TYPE.NEW_SLIDE,
        content: {
          slide_id: 'slide-multi-visual-1',
          target_element_bid: 'visual-final-1',
          generated_block_bid: 'generated-multi-1',
          slide_index: 0,
          audio_position: 0,
          visual_kind: 'image',
          segment_type: 'markdown',
          segment_content: '![figure](https://example.com/figure.png)',
          source_span: [0, 34],
          is_placeholder: false,
        },
      });
    });

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'generated-multi-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'streaming-multi-1',
          generated_block_bid: 'generated-multi-1',
          element_type: 'text',
          content: '',
          is_renderable: false,
          is_speakable: false,
          is_new: true,
          like_status: 'none',
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'generated-multi-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'visual-final-1',
          generated_block_bid: 'generated-multi-1',
          element_type: 'image',
          content: '',
          payload: {
            previous_visuals: [
              {
                visual_type: 'image',
                content: '![figure](https://example.com/figure.png)',
              },
            ],
          },
          is_renderable: true,
          is_speakable: false,
          is_new: true,
          like_status: 'none',
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'generated-multi-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'text-final-1',
          generated_block_bid: 'generated-multi-1',
          element_type: 'text',
          content: 'Final explanation after the image',
          is_renderable: false,
          is_speakable: true,
          is_new: true,
          like_status: 'none',
        },
      });
    });

    const visualItem = result.current.items.find(
      item => item.element_bid === 'visual-final-1',
    );
    const textItem = result.current.items.find(
      item => item.element_bid === 'text-final-1',
    );

    expect(visualItem?.content).toBe(
      '![figure](https://example.com/figure.png)',
    );
    expect(textItem?.content).toBe('Final explanation after the image');
    expect(visualItem?.listenSlides).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ slide_id: 'slide-multi-visual-1' }),
      ]),
    );
    expect(textItem?.listenSlides ?? []).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ slide_id: 'slide-multi-visual-1' }),
      ]),
    );
  });

  it('hydrates history visual elements from payload previous visuals', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'image',
          content: '',
          generated_block_bid: 'history-generated-visual-1',
          element_bid: 'history-visual-1',
          is_renderable: true,
          is_speakable: false,
          is_new: true,
          like_status: 'none',
          user_input: '',
          payload: {
            previous_visuals: [
              {
                visual_type: 'image',
                content: '![history](https://example.com/history.png)',
              },
            ],
          },
        },
      ],
      slides: [],
      records: [],
    });

    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(
      result.current.items.find(item => item.element_bid === 'history-visual-1')
        ?.content,
    ).toBe('![history](https://example.com/history.png)');
  });

  it('keeps canonical stream content raw after text end for the current element', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper: mobileWrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-1',
          generated_block_bid: 'content-text-1',
          element_type: 'text',
          content: 'First line',
          like_status: 'none',
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-text-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: false,
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-text-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');
    expect(
      result.current.items.find(item => item.element_bid === 'content-text-1')
        ?.isHistory,
    ).toBeUndefined();
    expect(
      result.current.items.find(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS &&
          item.parent_element_bid === 'content-text-1',
      ),
    ).toBeDefined();
  });

  it('marks finalized listen mode elements for history-like read mode rendering during streaming', async () => {
    const { result } = renderHook(
      ({ isListenMode }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          isListenMode,
        }),
      {
        wrapper,
        initialProps: {
          isListenMode: true,
        },
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-1',
          generated_block_bid: 'content-text-1',
          element_type: 'text',
          content: 'First line',
          like_status: 'none',
        },
      });
    });

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: false,
      });
    });

    const finalizedItem = result.current.items.find(
      item => item.element_bid === 'content-text-1',
    );

    expect(finalizedItem?.isHistory).toBeUndefined();
    expect(finalizedItem?.shouldRenderAsHistoryInReadMode).toBe(true);
  });

  it('does not keep using stale listen mode when a streamed element is finalized after switching back to read mode', async () => {
    const { result, rerender } = renderHook(
      ({ isListenMode }) =>
        useChatLogicHook({
          ...buildBaseParams(),
          isListenMode,
        }),
      {
        wrapper,
        initialProps: {
          isListenMode: true,
        },
      },
    );

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-1',
          generated_block_bid: 'content-text-1',
          element_type: 'text',
          content: 'First line',
          like_status: 'none',
        },
      });
    });

    rerender({ isListenMode: false });

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-2',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-2',
          generated_block_bid: 'content-text-2',
          element_type: 'text',
          content: 'Second line',
          like_status: 'none',
        },
      });
    });

    const firstItem = result.current.items.find(
      item => item.element_bid === 'content-text-1',
    );

    expect(firstItem?.is_final).toBe(true);
    expect(firstItem?.shouldRenderAsHistoryInReadMode).toBe(false);
  });

  it('keeps canonical finalized content raw after receiving more stream text', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper: mobileWrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-1',
          generated_block_bid: 'content-text-1',
          element_type: 'text',
          content: 'First line',
          like_status: 'none',
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: false,
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-text-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.CONTENT,
        content: ' and second line',
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-text-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');
  });

  it('keeps previously streamed text when a resumed run sends a cumulative content snapshot', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper: mobileWrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-1',
          generated_block_bid: 'content-text-1',
          element_type: 'text',
          content: 'First line',
          like_status: 'none',
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: false,
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-text-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.CONTENT,
        content: 'First line and second line',
      });
    });

    const content = result.current.items.find(
      item => item.element_bid === 'content-text-1',
    )?.content;

    expect(content).toContain('First line and second line');
    expect(content).not.toContain('<custom-button-after-content>');
  });

  it('keeps canonical finalized content raw after receiving another element update', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper: mobileWrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-html-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-html-1',
          generated_block_bid: 'content-html-1',
          element_type: 'html',
          content: '<p>HTML block</p>',
          like_status: 'none',
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'content-html-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: false,
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-html-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-html-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-html-1',
          generated_block_bid: 'content-html-1',
          element_type: 'html',
          content: '<p>Updated HTML block</p>',
          like_status: 'none',
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-html-1')
        ?.content,
    ).not.toContain('<custom-button-after-content>');
    expect(
      result.current.items.find(item => item.element_bid === 'content-html-1')
        ?.is_final,
    ).toBe(true);
  });

  it('keeps a finalized element final when a later element snapshot still reports false', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-1',
          generated_block_bid: 'content-text-1',
          element_type: 'text',
          content: 'First text',
          like_status: 'none',
          is_final: false,
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-2',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-2',
          generated_block_bid: 'content-text-2',
          element_type: 'text',
          content: 'Second text',
          like_status: 'none',
          is_final: false,
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-text-1')
        ?.is_final,
    ).toBe(true);

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-text-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-text-1',
          generated_block_bid: 'content-text-1',
          element_type: 'text',
          content: 'First text updated',
          like_status: 'none',
          is_final: false,
        },
      });
    });

    expect(
      result.current.items.find(item => item.element_bid === 'content-text-1')
        ?.is_final,
    ).toBe(true);
  });

  it('places history ask block right after its anchor element across multiple content elements', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'content',
          content: 'content-1',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
        {
          element_type: 'content',
          content: 'content-2',
          generated_block_bid: 'content-2',
          element_bid: 'content-2',
          like_status: 'none',
          user_input: '',
        },
        {
          element_type: 'ask',
          content: 'follow-up ask',
          generated_block_bid: 'ask-block-1',
          element_bid: 'ask-element-1',
          payload: {
            anchor_element_bid: 'content-1',
          },
        },
        {
          element_type: 'answer',
          content: 'follow-up answer',
          generated_block_bid: 'answer-block-1',
          element_bid: 'answer-element-1',
          payload: {
            anchor_element_bid: 'content-1',
            ask_element_bid: 'ask-element-1',
          },
        },
      ],
      slides: [],
      records: [],
    });

    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const askBlockIndex = result.current.items.findIndex(
      item =>
        item.type === ChatContentItemType.ASK &&
        item.parent_element_bid === 'content-1',
    );
    const contentOneIndex = result.current.items.findIndex(
      item => item.element_bid === 'content-1',
    );
    const contentTwoIndex = result.current.items.findIndex(
      item => item.element_bid === 'content-2',
    );

    expect(askBlockIndex).toBeGreaterThan(contentOneIndex);
    expect(askBlockIndex).toBeLessThan(contentTwoIndex);
  });

  it('inserts only one ask block and keeps it under like status', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-1',
          generated_block_bid: 'content-1',
          element_type: 'content',
          content: 'Hello',
          like_status: 'none',
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'content-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: false,
      });
    });

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
      });
    });

    act(() => {
      result.current.toggleAskExpanded('content-1');
    });

    const askItems = result.current.items.filter(
      item =>
        item.type === ChatContentItemType.ASK &&
        item.parent_element_bid === 'content-1',
    );
    const likeStatusIndex = result.current.items.findIndex(
      item =>
        item.type === ChatContentItemType.LIKE_STATUS &&
        item.parent_element_bid === 'content-1',
    );
    const askIndex = result.current.items.findIndex(
      item =>
        item.type === ChatContentItemType.ASK &&
        item.parent_element_bid === 'content-1',
    );

    expect(askItems).toHaveLength(1);
    expect(likeStatusIndex).toBeGreaterThan(-1);
    expect(askIndex).toBe(likeStatusIndex + 1);
  });

  it('continues the lesson stream after a non-terminal done event', async () => {
    renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());
    const initialRunCount = mockGetRunMessage.mock.calls.length;

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-1',
          generated_block_bid: 'content-1',
          element_type: 'content',
          content: 'Hello',
          like_status: 'none',
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'content-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: false,
      });
    });

    await waitFor(() =>
      expect(mockGetRunMessage).toHaveBeenCalledTimes(initialRunCount + 1),
    );
  });

  it('stops auto-continuation after the current lesson reports completed', async () => {
    const params = buildBaseParams();
    const { result } = renderHook(() => useChatLogicHook(params), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());
    await waitFor(() => expect(result.current.isOutputInProgress).toBe(true));
    const initialRunCount = mockGetRunMessage.mock.calls.length;

    await act(async () => {
      await activeRun?.onMessage({
        generated_block_bid: 'content-1',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'content-1',
          generated_block_bid: 'content-1',
          element_type: 'content',
          content: 'Hello',
          like_status: 'none',
        },
      });
      await activeRun?.onMessage({
        type: SSE_OUTPUT_TYPE.OUTLINE_ITEM_UPDATE,
        content: {
          outline_bid: 'lesson-1',
          title: 'Lesson 1',
          status: 'completed',
          has_children: false,
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'content-1',
        type: SSE_OUTPUT_TYPE.TEXT_END,
        content: '',
        is_terminal: true,
      });
    });

    expect(params.lessonUpdate).toHaveBeenCalledWith({
      id: 'lesson-1',
      name: 'Lesson 1',
      status: 'completed',
      status_value: 'completed',
    });
    expect(mockGetRunMessage).toHaveBeenCalledTimes(initialRunCount);
    await waitFor(() => expect(result.current.isOutputInProgress).toBe(false));
    expect(activeRun?.source.close).toHaveBeenCalled();
  });

  it('keeps interaction elements that arrive after lesson completion updates', async () => {
    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(activeRun).toBeDefined());

    await act(async () => {
      await activeRun?.onMessage({
        type: SSE_OUTPUT_TYPE.OUTLINE_ITEM_UPDATE,
        content: {
          outline_bid: 'lesson-1',
          title: 'Lesson 1',
          status: 'completed',
          has_children: false,
        },
      });
      await activeRun?.onMessage({
        generated_block_bid: 'interaction-after-complete',
        type: SSE_OUTPUT_TYPE.ELEMENT,
        content: {
          element_bid: 'interaction-after-complete',
          generated_block_bid: 'interaction-after-complete',
          element_type: 'interaction',
          content: '?[下一节//_sys_next_chapter]',
          is_marker: true,
          is_new: true,
          is_renderable: false,
          is_speakable: false,
          user_input: '',
          like_status: 'none',
        },
      });
    });

    await waitFor(() =>
      expect(
        result.current.items.find(
          item => item.element_bid === 'interaction-after-complete',
        ),
      ).toEqual(
        expect.objectContaining({
          element_bid: 'interaction-after-complete',
          type: ChatContentItemType.INTERACTION,
          content: '?[下一节//_sys_next_chapter]',
        }),
      ),
    );
  });

  it('does not treat the latest interaction as regenerate when helper rows are trailing', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          block_type: 'content',
          element_type: 'content',
          content: 'intro',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
        {
          block_type: 'interaction',
          element_type: 'interaction',
          content: '?[%{{knowledge_level}} 完全不了解 | 略知一二 | 比较熟悉]',
          generated_block_bid: 'interaction-1',
          element_bid: 'interaction-1',
          like_status: 'none',
          user_input: '',
        },
      ],
      slides: [],
      records: [],
    });

    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items[result.current.items.length - 1]?.type).toBe(
      ChatContentItemType.LIKE_STATUS,
    );

    const runCallCountBeforeSend = mockGetRunMessage.mock.calls.length;

    act(() => {
      result.current.onSend(
        {
          variableName: 'knowledge_level',
          selectedValues: ['比较熟悉'],
        },
        'interaction-1',
      );
    });

    await waitFor(() =>
      expect(mockGetRunMessage).toHaveBeenCalledTimes(
        runCallCountBeforeSend + 1,
      ),
    );
    expect(result.current.reGenerateConfirm.open).toBe(false);
  });

  it('drops orphan history follow-ups whose anchor element is absent from records', async () => {
    mockGetLessonStudyRecord.mockResolvedValueOnce({
      mdflow: '',
      elements: [
        {
          element_type: 'ask',
          content: '接下来学什么',
          generated_block_bid: 'ask-block-1',
          element_bid: 'ask-element-1',
          payload: { anchor_element_bid: 'missing-anchor' },
        },
        {
          element_type: 'answer',
          content: '咱们已经学完了...',
          generated_block_bid: 'ask-block-1',
          element_bid: 'answer-element-1',
          payload: {
            anchor_element_bid: 'missing-anchor',
            ask_element_bid: 'ask-element-1',
          },
        },
      ],
      slides: [],
      records: [],
    });

    const { result } = renderHook(() => useChatLogicHook(buildBaseParams()), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(
      result.current.items.some(item => item.type === ChatContentItemType.ASK),
    ).toBe(false);
  });

  describe('regenerate during a running stream', () => {
    const HISTORY_WITH_TWO_INTERACTIONS = {
      mdflow: '',
      elements: [
        {
          element_type: 'content',
          content: 'intro',
          generated_block_bid: 'content-1',
          element_bid: 'content-1',
          like_status: 'none',
          user_input: '',
        },
        {
          element_type: 'interaction',
          content: '?[%{{var_old}} A | B]',
          generated_block_bid: 'interaction-old',
          element_bid: 'interaction-old',
          like_status: 'none',
          user_input: 'A',
        },
        {
          element_type: 'interaction',
          content: '?[%{{var_new}} X | Y]',
          generated_block_bid: 'interaction-new',
          element_bid: 'interaction-new',
          like_status: 'none',
          user_input: '',
        },
      ],
      slides: [],
      records: [],
    };

    const renderWithStreamingRun = async () => {
      mockGetLessonStudyRecord.mockResolvedValueOnce(
        HISTORY_WITH_TWO_INTERACTIONS,
      );
      const renderResult = renderHook(
        () => useChatLogicHook(buildBaseParams()),
        { wrapper },
      );
      await waitFor(() =>
        expect(renderResult.result.current.isLoading).toBe(false),
      );

      act(() => {
        renderResult.result.current.onSend(
          { variableName: 'var_new', selectedValues: ['X'] },
          'interaction-new',
        );
      });
      await waitFor(() => expect(activeRun).toBeDefined());

      await act(async () => {
        await activeRun?.onMessage({
          generated_block_bid: 'content-new',
          type: SSE_OUTPUT_TYPE.ELEMENT,
          content: {
            element_bid: 'content-new',
            generated_block_bid: 'content-new',
            element_type: 'content',
            content: 'streaming...',
            like_status: 'none',
          },
        });
      });
      await waitFor(() =>
        expect(renderResult.result.current.isOutputInProgress).toBe(true),
      );
      return renderResult;
    };

    it('pops the regenerate confirm dialog instead of toasting while the stream is running', async () => {
      const { result } = await renderWithStreamingRun();
      const initialSource = activeRun?.source;
      const runCallCountBeforeRegen = mockGetRunMessage.mock.calls.length;
      (toast as jest.Mock).mockClear();

      act(() => {
        result.current.onSend(
          { variableName: 'var_old', selectedValues: ['B'] },
          'interaction-old',
        );
      });

      expect(result.current.reGenerateConfirm.open).toBe(true);
      expect(toast).not.toHaveBeenCalled();
      expect(initialSource?.close).not.toHaveBeenCalled();
      expect(mockGetRunMessage).toHaveBeenCalledTimes(runCallCountBeforeRegen);
    });

    it('aborts the running stream and submits the new variables when the user confirms regenerate', async () => {
      const { result } = await renderWithStreamingRun();
      act(() => {
        result.current.onSend(
          { variableName: 'var_old', selectedValues: ['B'] },
          'interaction-old',
        );
      });
      expect(result.current.reGenerateConfirm.open).toBe(true);

      const initialSource = activeRun?.source;
      const runCallCountBeforeConfirm = mockGetRunMessage.mock.calls.length;

      await act(async () => {
        result.current.reGenerateConfirm.onConfirm();
      });

      await waitFor(() =>
        expect(mockGetRunMessage).toHaveBeenCalledTimes(
          runCallCountBeforeConfirm + 1,
        ),
      );
      expect(initialSource?.close).toHaveBeenCalled();
      expect(result.current.reGenerateConfirm.open).toBe(false);

      const lastCall =
        mockGetRunMessage.mock.calls[mockGetRunMessage.mock.calls.length - 1];
      expect(lastCall[3]).toMatchObject({
        input: { var_old: expect.anything() },
        input_type: SSE_INPUT_TYPE.NORMAL,
      });
    });

    it('keeps the running stream and discards the pending submit when the user cancels regenerate', async () => {
      const { result } = await renderWithStreamingRun();
      act(() => {
        result.current.onSend(
          { variableName: 'var_old', selectedValues: ['B'] },
          'interaction-old',
        );
      });
      expect(result.current.reGenerateConfirm.open).toBe(true);

      const initialSource = activeRun?.source;
      const runCallCountBeforeCancel = mockGetRunMessage.mock.calls.length;

      act(() => {
        result.current.reGenerateConfirm.onCancel();
      });

      expect(initialSource?.close).not.toHaveBeenCalled();
      expect(mockGetRunMessage).toHaveBeenCalledTimes(runCallCountBeforeCancel);
      expect(result.current.reGenerateConfirm.open).toBe(false);
    });
  });
});

import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { toast } from '@/hooks/useToast';
import useChatLogicHook, { ChatContentItemType } from './useChatLogicHook';
import { AppContext } from '../AppContext';
import { SSE_INPUT_TYPE, SSE_OUTPUT_TYPE } from '@/c-api/studyV2';

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

  it('pushes an error item and shows a destructive toast after 3s of run stream inactivity', async () => {
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
      jest.advanceTimersByTime(3000);
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

  it('re-adds the mobile follow-up button for history content after switching from listen mode to read mode', async () => {
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

    await waitFor(() =>
      expect(
        result.current.items.find(item => item.element_bid === 'content-1')
          ?.content,
      ).toContain('<custom-button-after-content>'),
    );
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

    await waitFor(() =>
      expect(
        result.current.items.find(item => item.element_bid === 'content-html-1')
          ?.content,
      ).toContain('<custom-button-after-content>'),
    );
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

  it('adds the mobile follow-up button only after text end for the current element', async () => {
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

    await waitFor(() =>
      expect(
        result.current.items.find(item => item.element_bid === 'content-text-1')
          ?.content,
      ).toContain('<custom-button-after-content>'),
    );
    expect(
      result.current.items.find(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS &&
          item.parent_element_bid === 'content-text-1',
      ),
    ).toBeDefined();
  });

  it('keeps the mobile follow-up button after finalized content receives more stream text', async () => {
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

    await waitFor(() =>
      expect(
        result.current.items.find(item => item.element_bid === 'content-text-1')
          ?.content,
      ).toContain('<custom-button-after-content>'),
    );

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
    ).toContain('<custom-button-after-content>');
  });

  it('keeps the mobile follow-up button after finalized content receives another element update', async () => {
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

    await waitFor(() =>
      expect(
        result.current.items.find(item => item.element_bid === 'content-html-1')
          ?.content,
      ).toContain('<custom-button-after-content>'),
    );

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
    ).toContain('<custom-button-after-content>');
  });

  it('keeps ask block position by history sequence order instead of anchor position', async () => {
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
    const contentTwoIndex = result.current.items.findIndex(
      item => item.element_bid === 'content-2',
    );
    const contentTwoLikeStatusIndex = result.current.items.findIndex(
      item =>
        item.type === ChatContentItemType.LIKE_STATUS &&
        item.parent_element_bid === 'content-2',
    );

    expect(askBlockIndex).toBeGreaterThan(contentTwoIndex);
    expect(askBlockIndex).toBeGreaterThan(contentTwoLikeStatusIndex);
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
    renderHook(() => useChatLogicHook(params), {
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
});

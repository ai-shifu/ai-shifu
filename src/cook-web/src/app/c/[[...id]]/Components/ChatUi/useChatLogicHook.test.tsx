import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import useChatLogicHook from './useChatLogicHook';
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
      CONTENT: 'content',
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

  it('clears loading after a control-only stream closes', async () => {
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

    const { result } = renderHook(
      () =>
        useChatLogicHook({
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
        }),
      { wrapper },
    );

    await waitFor(() => expect(activeRun).toBeDefined());
    await waitFor(() =>
      expect(
        result.current.items.some(
          item => item.generated_block_bid === 'loading',
        ),
      ).toBe(true),
    );

    act(() => {
      activeRun?.source.emit('readystatechange');
    });

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
  });
});

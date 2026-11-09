import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useContext,
  useMemo,
} from 'react';
import React from 'react';
import { useLatest } from 'react-use';
import {
  applyElementToList,
  isLoadingItem,
  LOADING_ITEM_BID,
  matchesElementBid,
  withoutLoadingItem,
} from '@/lib/lesson-stream/content-list';
import {
  readDoneIsTerminal,
  readRunEventError,
} from '@/lib/lesson-stream/run-events';
import { useCourseStore } from '@/store/use-course-store';
import { useUserStore } from '@/store';
import { useShallow } from 'zustand/react/shallow';
import {
  StudyRecordItem,
  AudioCompleteData,
  AudioSegmentData,
  type ListenSlideData,
  getRunMessage,
  SSE_INPUT_TYPE,
  getLessonStudyRecord,
  SSE_OUTPUT_TYPE,
  SYS_INTERACTION_TYPE,
  LESSON_FEEDBACK_VARIABLE_NAME,
  BLOCK_TYPE,
  checkIsRunning,
  streamGeneratedBlockAudio,
  submitLessonFeedback,
  ELEMENT_TYPE,
} from '@/api/learning';
import {
  getAudioTrackByPosition,
  normalizeAudioCompletePayload,
  normalizeAudioSegmentPayload,
  toAudioSegmentData,
  upsertAudioComplete,
  upsertAudioSegment,
} from '@/lib/audio-utils';
import { LESSON_STATUS_VALUE } from '@/constants/course-constants';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
  type StopActiveLessonStreamDetail,
} from '@/app/c/[[...id]]/events';
import { EVENT_NAMES } from '@/hooks/use-tracking';
import {
  buildLessonFeedbackUserInput,
  parseLessonFeedbackUserInput,
  resolveInteractionSubmission,
} from '@/lib/interaction-user-input';
import {
  classifyLearnerInteraction,
  updateInteractionItems,
} from '@/lib/chat-interaction-rewind';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import {
  finalizeLikeStatusByParent,
  isLessonFeedbackContent,
  removeLikeStatusByParent,
  shouldAttachLikeStatusByElement,
  upsertLikeStatusByParent,
} from './lesson-like-status';
import {
  itemMatchesElementCacheIdentity,
  mergeListenSlides,
  resolveAskRecordParentBid,
  resolveElementCacheIdentityBids,
  upsertAskMessageByParent,
} from './lesson-list-helpers';
import LoadingBar from './LoadingBar';
import { startPreviewRewindTracking } from './preview-rewind-tracking';
import { useTranslation } from 'react-i18next';
import { show as showToast, toast, toastOnce } from '@/hooks/use-toast';
import { AppContext } from '../app-context';
import {
  buildLessonRunContentCacheKey,
  EMPTY_LESSON_RUN_CONTENT_ENTRY,
  EMPTY_LESSON_RUN_ITEMS,
  useLessonRunContentStore,
} from '@/store/use-lesson-run-content-store';
import { resolveLearnerErrorToast } from '@/lib/learner-error';
import {
  AI_SERVICE_ERROR_TOAST_DEDUPE_MS,
  AI_SERVICE_ERROR_TOAST_DURATION_MS,
  AI_SERVICE_ERROR_TOAST_KEY,
  resolveAiServiceErrorToast,
} from '@/lib/ai-service-error';
import { debugWarn } from '@/lib/debug-console';
import {
  getCreditInsufficientMessage,
  isCreditInsufficientBusinessCode,
  resolveCourseCreditInsufficientAudience,
  showCreditInsufficientToast,
} from '@/lib/credit-insufficient-toast';
import {
  buildElementContentItem as buildChatElementContentItem,
  isAskOrAnswerElementType,
  normalizeCanonicalChatContentList,
  normalizeOptionalNumber,
  resolveRecordElementType,
} from './use-lesson-conversation.helpers';
import type {
  LessonFeedbackPopupState,
  RequestAudioForBlockOptions,
  SSEParams,
  TtsStreamCancel,
  UseChatSessionParams,
  UseChatSessionResult,
} from './use-lesson-conversation.types';

const LESSON_FEEDBACK_DISMISS_CACHE_LIMIT = 200;
const RUN_STREAM_IDLE_TIMEOUT_MS = 15000;
const MOBILE_RUN_STREAM_IDLE_TIMEOUT_MS = 60000;
const TTS_BACKFILL_IDLE_TIMEOUT_MS = 120000;
const STREAM_TIMEOUT_ITEM_BID_PREFIX = 'stream-timeout-error';
export { ChatContentItemType };
export type { ChatContentItem };

const findAudioTargetItem = (items: ChatContentItem[], bid: string) => {
  if (!bid) {
    return undefined;
  }

  for (const item of items) {
    if (item.element_bid === bid || item.generated_block_bid === bid) {
      return item;
    }

    const askMessage = item.ask_list?.find(
      message =>
        message.element_bid === bid || message.generated_block_bid === bid,
    );
    if (askMessage) {
      return askMessage;
    }
  }

  return undefined;
};

const mapNestedAskMessages = (
  items: ChatContentItem[],
  shouldUpdate: (message: ChatContentItem) => boolean,
  updateMessage: (message: ChatContentItem) => ChatContentItem,
) =>
  items.map(item => {
    if (!Array.isArray(item.ask_list)) {
      return item;
    }

    let hasChanges = false;
    const nextAskList = item.ask_list.map(message => {
      if (!shouldUpdate(message)) {
        return message;
      }
      hasChanges = true;
      return updateMessage(message);
    });

    if (!hasChanges) {
      return item;
    }

    return {
      ...item,
      ask_list: nextAskList,
    };
  });

const updateNestedAskMessageAudioStreaming = (
  items: ChatContentItem[],
  targetElementBid: string,
  sourceBlockBid: string,
  isAudioStreaming: boolean,
) =>
  mapNestedAskMessages(
    items,
    message =>
      Boolean(targetElementBid && message.element_bid === targetElementBid) ||
      Boolean(sourceBlockBid && message.generated_block_bid === sourceBlockBid),
    message => ({
      ...message,
      ...(isAudioStreaming
        ? {
            audioTracks: [],
            audioUrl: undefined,
            audioDurationMs: undefined,
          }
        : {
            audioTracks: (message.audioTracks ?? []).map(track => ({
              ...track,
              isAudioStreaming: false,
            })),
          }),
      isAudioStreaming,
    }),
  );

const upsertNestedAskAudioSegment = (
  items: ChatContentItem[],
  elementBid: string,
  segment: AudioSegmentData,
) =>
  mapNestedAskMessages(
    items,
    message =>
      message.element_bid === elementBid ||
      message.generated_block_bid === elementBid,
    message =>
      upsertAudioSegment(
        [message],
        message.element_bid || elementBid,
        segment,
      )[0] ?? message,
  );

const upsertNestedAskAudioComplete = (
  items: ChatContentItem[],
  elementBid: string,
  complete: Partial<AudioCompleteData>,
) =>
  mapNestedAskMessages(
    items,
    message =>
      message.element_bid === elementBid ||
      message.generated_block_bid === elementBid,
    message =>
      upsertAudioComplete(
        [message],
        message.element_bid || elementBid,
        complete,
      )[0] ?? message,
  );

/**
 * useLessonConversation orchestrates the streaming chat lifecycle for lesson content.
 */
function useLessonConversation({
  shifuBid,
  onGoChapter,
  outlineBid,
  lessonId,
  chapterId,
  previewMode,
  isListenMode = false,
  learningMode = isListenMode ? 'listen' : 'read',
  listenRequestEnabled = false,
  shouldPromptLessonFeedback = true,
  trackEvent,
  lessonUpdate,
  chapterUpdate,
  updateSelectedLesson,
  getNextLessonId,
  scrollToLesson,
  // scrollToBottom,
  showOutputInProgressToast,
  onPayModalOpen,
}: UseChatSessionParams): UseChatSessionResult {
  const { t } = useTranslation();
  const { mobileStyle } = useContext(AppContext);
  const isListenModeLatest = useLatest(isListenMode);

  const { updateUserInfo } = useUserStore(
    useShallow(state => ({
      updateUserInfo: state.updateUserInfo,
    })),
  );
  const isStreamingRef = useRef(false);
  const [isOutputInProgress, setIsOutputInProgress] = useState(false);
  const [hasRunFailed, setHasRunFailed] = useState(false);
  const {
    updateResetedLessonId,
    resetedLessonId,
    resettingLessonId,
    isCurrentUserCourseOwner,
  } = useCourseStore(
    useShallow(state => ({
      resetedLessonId: state.resetedLessonId,
      resettingLessonId: state.resettingLessonId,
      updateResetedLessonId: state.updateResetedLessonId,
      isCurrentUserCourseOwner: state.isCurrentUserCourseOwner,
    })),
  );

  const effectivePreviewMode = previewMode ?? false;
  const creditInsufficientAudience = resolveCourseCreditInsufficientAudience({
    previewMode: effectivePreviewMode,
    isCurrentUserCourseOwner,
  });
  const lessonRunContentCacheKey = useMemo(
    () =>
      buildLessonRunContentCacheKey({
        shifuBid,
        outlineBid,
        previewMode: effectivePreviewMode,
      }),
    [effectivePreviewMode, outlineBid, shifuBid],
  );
  const contentList = useLessonRunContentStore(
    useCallback(
      state =>
        state.entries[lessonRunContentCacheKey]?.items ??
        EMPTY_LESSON_RUN_ITEMS,
      [lessonRunContentCacheKey],
    ),
  );
  const replaceLessonRunContentItems = useLessonRunContentStore(
    state => state.replaceItems,
  );
  const resetLessonRunContent = useLessonRunContentStore(
    state => state.resetLesson,
  );
  const markLessonRunAudioBackfillReady = useLessonRunContentStore(
    state => state.markAudioBackfillReady,
  );
  const [currentStreamingElementBid, setCurrentStreamingElementBid] =
    useState('');
  const [currentTypewriterElementBid, setCurrentTypewriterElementBid] =
    useState('');
  // const [isTypeFinished, setIsTypeFinished] = useState(false);
  const isTypeFinishedRef = useRef(false);
  const [isLoading, setIsLoading] = useState(true);
  const isInitHistoryRef = useRef(true);
  const [showLessonUpdateNotice, setShowLessonUpdateNotice] = useState(false);
  // const [lastInteractionBlock, setLastInteractionBlock] =
  //   useState<ChatContentItem | null>(null);
  const [loadedChapterId, setLoadedChapterId] = useState('');

  const contentListRef = useRef<ChatContentItem[]>([]);
  const currentContentRef = useRef<string>('');
  const currentBlockIdRef = useRef<string | null>(null);
  const pendingInteractionAnchorBidRef = useRef('');
  const unconfirmedAnswerRef = useRef<{
    elementBid: string;
    previousAnswer: string;
  } | null>(null);
  const runRef = useRef<
    | ((
        params: SSEParams,
        continuingRewind?: ReturnType<typeof startPreviewRewindTracking>,
      ) => void)
    | null
  >(null);
  const sseRef = useRef<any>(null);
  const previewRewindResultRef =
    useRef<ReturnType<typeof startPreviewRewindTracking>>(undefined);
  const sseRunSerialRef = useRef(0);
  const refreshDataSerialRef = useRef(0);
  // The lesson an empty-input run has already been started for. Loading a lesson calls
  // `refreshData` from three places -- the lesson-id effect, the reset subscription, and the
  // effect watching `resetedLessonId` return to null -- and on a reset all three fire. They run
  // one after another, so `refreshDataSerialRef` cannot tell them apart: each is the newest at
  // the moment it finishes, and each started its own run. Measured on a reset: three identical
  // runs within 332ms. The first two are closed client-side, which does not stop the server, so
  // each one still teaches a turn, bills for it, and leaves an unfinalized row behind.
  const autoRunStartedForRef = useRef<string | null>(null);
  // The lesson the reset subscription has reloaded and not yet handed back. Clearing
  // `resetedLessonId` afterwards re-runs the lesson-id effect, which would otherwise close the run
  // the reset just started and start it again -- measured after the mark above: two identical runs
  // per reset, the first closed after 7ms and still taught and billed by the server.
  const reloadedForResetRef = useRef<string | null>(null);
  const runStreamTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const ttsSseRef = useRef<Record<string, any>>({});
  const ttsStreamCancelRef = useRef<Record<string, TtsStreamCancel>>({});
  const lastInteractionBlockRef = useRef<ChatContentItem | null>(null);
  const hasScrolledToBottomRef = useRef<boolean>(false);
  const [pendingRegenerate, setPendingRegenerate] = useState<{
    content: OnSendContentParams;
    blockBid: string;
  } | null>(null);
  const [showRegenerateConfirm, setShowRegenerateConfirm] = useState(false);
  const [lessonFeedbackPopupState, setLessonFeedbackPopupState] =
    useState<LessonFeedbackPopupState>({
      open: false,
      outlineBid: '',
      modeKey: '',
      elementBid: '',
      defaultScoreText: '',
      defaultCommentText: '',
      readonly: false,
    });
  const dismissedLessonFeedbackOutlineBidsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    contentListRef.current = contentList;
  }, [contentList]);

  const getLessonRunContentCacheEntry = useCallback(
    () =>
      useLessonRunContentStore.getState().entries[lessonRunContentCacheKey] ??
      EMPTY_LESSON_RUN_CONTENT_ENTRY,
    [lessonRunContentCacheKey],
  );

  // Learner preview uses the same generated-block TTS contract as live courses.
  // Keep preview-specific request params, but do not disable audio streaming.
  const allowTtsStreaming = true;

  useEffect(() => {
    setHasRunFailed(false);
  }, [lessonRunContentCacheKey]);

  const resolveElementItemBid = useCallback(
    (
      record?: Pick<
        StudyRecordItem,
        'element_bid' | 'generated_block_bid' | 'target_element_bid'
      > | null,
    ) =>
      // Normalize streamed updates to the logical source element to avoid duplicate visual blocks.
      record?.target_element_bid ||
      record?.element_bid ||
      record?.generated_block_bid ||
      '',
    [],
  );

  const resolveAudioBlockTarget = useCallback((bid: string) => {
    const item = findAudioTargetItem(contentListRef.current, bid);

    return {
      elementBid: item?.element_bid || bid,
      generatedBlockBid: item?.generated_block_bid || bid,
    };
  }, []);

  const resolveSourceGeneratedBlockBid = useCallback(
    (bid: string) => resolveAudioBlockTarget(bid).generatedBlockBid,
    [resolveAudioBlockTarget],
  );

  const isAudioBackfillReadyForBlock = useCallback(
    (generatedBlockBid?: string | null, elementBid?: string | null) => {
      const readyBids = new Set(
        getLessonRunContentCacheEntry().audioBackfillReadyBids,
      );

      return Boolean(
        (generatedBlockBid && readyBids.has(generatedBlockBid)) ||
        (elementBid && readyBids.has(elementBid)),
      );
    },
    [getLessonRunContentCacheEntry],
  );

  const finalizeElementOutputInList = useCallback(
    (items: ChatContentItem[], completedElementBid: string) => {
      if (!completedElementBid) {
        return items;
      }

      const targetIndex = items.findIndex(
        item => item.element_bid === completedElementBid,
      );
      if (targetIndex < 0) {
        return items;
      }

      const nextItems = [...items];
      const targetItem = nextItems[targetIndex];
      const isListenModeCurrent = Boolean(isListenModeLatest.current);

      nextItems[targetIndex] = {
        ...nextItems[targetIndex],
        is_final: true,
        shouldRenderAsHistoryInReadMode:
          isListenModeCurrent && targetItem.isHistory !== true,
      };

      return finalizeLikeStatusByParent(nextItems, completedElementBid);
    },
    [isListenModeLatest],
  );

  const buildContentItem = useCallback(
    (
      record: StudyRecordItem,
      options?: {
        isHistory?: boolean;
        shouldRenderAsHistoryInReadMode?: boolean;
        shouldUseTypewriter?: boolean;
        listenSlides?: ListenSlideData[];
        previousItem?: ChatContentItem;
      },
    ): ChatContentItem =>
      buildChatElementContentItem(record, {
        ...options,
        isAudioBackfillReadyForBlock,
        mergeListenSlides,
        resolveElementItemBid,
      }),
    [isAudioBackfillReadyForBlock, resolveElementItemBid],
  );

  const parseLessonFeedbackScore = useCallback((raw?: string | null) => {
    if (!raw) {
      return null;
    }
    const normalized = Number(raw);
    if (!Number.isInteger(normalized)) {
      return null;
    }
    if (normalized < 1 || normalized > 5) {
      return null;
    }
    return normalized;
  }, []);

  const markLessonFeedbackPopupDismissed = useCallback(
    (lessonOutlineBid: string) => {
      if (!lessonOutlineBid) {
        return;
      }
      const cache = dismissedLessonFeedbackOutlineBidsRef.current;
      if (cache.has(lessonOutlineBid)) {
        cache.delete(lessonOutlineBid);
      }
      cache.add(lessonOutlineBid);

      while (cache.size > LESSON_FEEDBACK_DISMISS_CACHE_LIMIT) {
        const oldestOutlineBid = cache.values().next().value as
          | string
          | undefined;
        if (!oldestOutlineBid) {
          break;
        }
        cache.delete(oldestOutlineBid);
      }
    },
    [],
  );

  const resetLessonFeedbackPopup = useCallback(() => {
    setLessonFeedbackPopupState({
      open: false,
      outlineBid: '',
      modeKey: '',
      elementBid: '',
      defaultScoreText: '',
      defaultCommentText: '',
      readonly: false,
    });
  }, []);

  useEffect(() => {
    resetLessonFeedbackPopup();
  }, [outlineBid, resetLessonFeedbackPopup]);

  useEffect(() => {
    setLessonFeedbackPopupState(prev => {
      if (!prev.open || prev.outlineBid !== outlineBid) {
        return prev;
      }
      return {
        ...prev,
        open: false,
      };
    });
  }, [isListenMode, outlineBid]);

  const dismissLessonFeedbackPopup = useCallback(() => {
    markLessonFeedbackPopupDismissed(outlineBid);
    setLessonFeedbackPopupState({
      open: false,
      outlineBid: '',
      modeKey: '',
      elementBid: '',
      defaultScoreText: '',
      defaultCommentText: '',
      readonly: false,
    });
  }, [markLessonFeedbackPopupDismissed, outlineBid]);

  const openLessonFeedbackPopup = useCallback(
    (interaction: {
      elementBid: string;
      defaultScoreText?: string;
      defaultCommentText?: string;
      readonly?: boolean;
      deferOpen?: boolean;
    }) => {
      if (!interaction.elementBid) {
        return;
      }
      if (dismissedLessonFeedbackOutlineBidsRef.current.has(outlineBid)) {
        return;
      }
      if (parseLessonFeedbackScore(interaction.defaultScoreText)) {
        return;
      }
      setLessonFeedbackPopupState({
        open: !interaction.deferOpen && shouldPromptLessonFeedback,
        outlineBid,
        modeKey: isListenMode ? 'listen' : 'read',
        elementBid: interaction.elementBid,
        defaultScoreText: interaction.defaultScoreText || '',
        defaultCommentText: interaction.defaultCommentText || '',
        readonly: Boolean(interaction.readonly),
      });
    },
    [
      isListenMode,
      outlineBid,
      parseLessonFeedbackScore,
      shouldPromptLessonFeedback,
    ],
  );

  useEffect(() => {
    if (isLoading || !shouldPromptLessonFeedback) {
      return;
    }
    setLessonFeedbackPopupState(prev => {
      if (!prev.elementBid || prev.open) {
        return prev;
      }
      if (dismissedLessonFeedbackOutlineBidsRef.current.has(outlineBid)) {
        return prev;
      }
      return {
        ...prev,
        open: true,
        modeKey: isListenMode ? 'listen' : 'read',
      };
    });
  }, [isLoading, isListenMode, outlineBid, shouldPromptLessonFeedback]);

  const getLessonFeedbackDefaults = useCallback(
    (raw?: string | null) => {
      const parsed = parseLessonFeedbackUserInput(raw);
      const score = parseLessonFeedbackScore(parsed.scoreText);

      return {
        scoreText: score ? String(score) : '',
        commentText: parsed.commentText || '',
      };
    },
    [parseLessonFeedbackScore],
  );

  /**
   * Auto scroll to bottom when history records are loaded and rendered
   * Only scroll once, don't interfere with user scrolling
   */
  // useEffect(() => {
  //   // Only scroll once after initial load
  //   if (hasScrolledToBottomRef.current) {
  //     return;
  //   }

  //   // Wait for: 1) loading complete, 2) has content, 3) chapter loaded
  //   if (!isLoading && contentList.length > 0 && loadedChapterId) {
  //     // Simple one-time scroll after a reasonable delay
  //     const timer = setTimeout(() => {
  //       if (!isMounted()) return;

  //       const bottomEl = chatBoxBottomRefLatest.current?.current;
  //       if (bottomEl) {
  //         // Use instant scroll to avoid blocking user interaction
  //         bottomEl.scrollIntoView({
  //           behavior: 'auto',
  //           block: 'end',
  //         });
  //         hasScrolledToBottomRef.current = true;
  //       }
  //     }, 300);

  //     return () => clearTimeout(timer);
  //   }
  // }, [
  //   isLoading,
  //   contentList.length,
  //   loadedChapterId,
  //   isMounted,
  //   chatBoxBottomRefLatest,
  // ]);

  /**
   * Keeps the React state and mutable ref of the content list in sync.
   */
  const setTrackedContentList = useCallback(
    (
      updater:
        | ChatContentItem[]
        | ((prev: ChatContentItem[]) => ChatContentItem[]),
    ) => {
      const previousItems =
        useLessonRunContentStore.getState().entries[lessonRunContentCacheKey]
          ?.items ?? EMPTY_LESSON_RUN_ITEMS;
      const next =
        typeof updater === 'function'
          ? (updater as (prev: ChatContentItem[]) => ChatContentItem[])(
              previousItems,
            )
          : updater;
      const normalizedNext = normalizeCanonicalChatContentList(next);
      contentListRef.current = normalizedNext;
      replaceLessonRunContentItems(lessonRunContentCacheKey, normalizedNext);
    },
    [lessonRunContentCacheKey, replaceLessonRunContentItems],
  );

  const clearRunStreamTimeout = useCallback(() => {
    if (runStreamTimeoutRef.current) {
      clearTimeout(runStreamTimeoutRef.current);
      runStreamTimeoutRef.current = null;
    }
  }, []);

  const createRunTimeoutErrorItem = useCallback(
    (runSerial: number): ChatContentItem => {
      const itemBid = `${STREAM_TIMEOUT_ITEM_BID_PREFIX}-${outlineBid}-${runSerial}`;

      return {
        element_bid: itemBid,
        generated_block_bid: itemBid,
        content: t('module.chat.streamTimeoutRetry'),
        readonly: true,
        user_input: '',
        customRenderBar: () => null,
        type: ChatContentItemType.ERROR,
        is_marker: true,
        is_renderable: true,
        is_new: true,
        is_speakable: false,
      };
    },
    [outlineBid, t],
  );

  const appendRunTimeoutError = useCallback(
    (runSerial: number) => {
      const timeoutErrorItem = createRunTimeoutErrorItem(runSerial);
      const timeoutErrorContent =
        typeof timeoutErrorItem.content === 'string'
          ? timeoutErrorItem.content
          : t('module.chat.streamTimeoutRetry');

      toast({
        title: timeoutErrorContent,
        variant: 'destructive',
      });

      setTrackedContentList(prevState => {
        const nextList = withoutLoadingItem(prevState);
        if (
          nextList.some(
            item => item.element_bid === timeoutErrorItem.element_bid,
          )
        ) {
          return nextList;
        }

        return [...nextList, timeoutErrorItem];
      });
    },
    [createRunTimeoutErrorItem, setTrackedContentList, t],
  );

  const appendRunBusinessError = useCallback(
    (message: string, businessCode?: number) => {
      const normalizedMessage = message.trim();
      if (!normalizedMessage) {
        return;
      }

      const itemBid = `run-business-error-${outlineBid}-${businessCode || 'unknown'}`;
      setTrackedContentList(prevState => {
        const nextList = withoutLoadingItem(prevState);
        if (nextList.some(item => item.element_bid === itemBid)) {
          return nextList;
        }

        return [
          ...nextList,
          {
            element_bid: itemBid,
            generated_block_bid: itemBid,
            content: normalizedMessage,
            readonly: true,
            user_input: '',
            customRenderBar: () => null,
            type: ChatContentItemType.ERROR,
            business_code: businessCode,
            is_marker: true,
            is_renderable: true,
            is_new: true,
            is_speakable: false,
          },
        ];
      });
    },
    [outlineBid, setTrackedContentList],
  );

  const syncLessonFeedbackInteractionValues = useCallback(
    (blockBid: string, scoreText: string, commentText: string) => {
      setTrackedContentList(prev =>
        prev.map(item => {
          if (item.element_bid !== blockBid) {
            return item;
          }
          return {
            ...item,
            readonly: false,
            user_input: buildLessonFeedbackUserInput(scoreText, commentText),
          };
        }),
      );
      setLessonFeedbackPopupState(prev => {
        if (prev.elementBid !== blockBid) {
          return prev;
        }
        return {
          ...prev,
          defaultScoreText: scoreText,
          defaultCommentText: commentText,
        };
      });
    },
    [setTrackedContentList],
  );

  /**
   * Applies stream-driven lesson status updates and triggers follow-up actions.
   */
  const lessonUpdateResp = useCallback(
    (
      response,
      isEnd: boolean,
      continuingRewind?: ReturnType<typeof startPreviewRewindTracking>,
    ) => {
      const {
        outline_bid: currentOutlineBid,
        status,
        title,
      } = response.content;
      lessonUpdate?.({
        id: currentOutlineBid,
        name: title,
        status,
        status_value: status,
      });
      if (status === LESSON_STATUS_VALUE.PREPARE_LEARNING && !isEnd) {
        runRef.current?.(
          {
            input: '',
            input_type: SSE_INPUT_TYPE.NORMAL,
          },
          continuingRewind,
        );
      }

      if (status === LESSON_STATUS_VALUE.LEARNING && !isEnd) {
        updateSelectedLesson(currentOutlineBid);
      }
    },
    [lessonUpdate, updateSelectedLesson],
  );

  const stopActiveRunStream = useCallback(() => {
    clearRunStreamTimeout();
    previewRewindResultRef.current?.('cancelled');
    if (sseRef.current) {
      try {
        sseRef.current.close();
      } catch {
      } finally {
        sseRef.current = null;
      }
    }

    isStreamingRef.current = false;
    setIsOutputInProgress(false);

    const completedElementBid = currentBlockIdRef.current || '';
    setTrackedContentList(prevState => {
      let nextList = withoutLoadingItem(prevState);
      if (completedElementBid) {
        nextList = finalizeElementOutputInList(nextList, completedElementBid);
      }
      return nextList.map(item => {
        const audioTracks = item.audioTracks ?? [];
        const hasStreamingTrack = audioTracks.some(track =>
          Boolean(track.isAudioStreaming),
        );
        if (!item.isAudioStreaming && !hasStreamingTrack) {
          return item;
        }

        return {
          ...item,
          isAudioStreaming: false,
          audioTracks: hasStreamingTrack
            ? audioTracks.map(track => ({
                ...track,
                isAudioStreaming: false,
              }))
            : item.audioTracks,
        };
      });
    });

    currentBlockIdRef.current = null;
    currentContentRef.current = '';
    setCurrentStreamingElementBid('');
    setCurrentTypewriterElementBid('');

    Object.values(ttsStreamCancelRef.current).forEach(cancel => {
      cancel();
    });
    Object.values(ttsSseRef.current).forEach(source => {
      source?.close?.();
    });
    ttsStreamCancelRef.current = {};
    ttsSseRef.current = {};
  }, [
    clearRunStreamTimeout,
    finalizeElementOutputInList,
    setTrackedContentList,
  ]);

  /**
   * Starts the SSE request and streams content into the chat list.
   */
  const run = useCallback(
    (
      sseParams: SSEParams,
      continuingRewind?: ReturnType<typeof startPreviewRewindTracking>,
    ) => {
      if (creditInsufficientAudience === null) {
        return;
      }
      const runSerial = sseRunSerialRef.current + 1;
      sseRunSerialRef.current = runSerial;
      clearRunStreamTimeout();
      // Internal continuation retains the original attempt; a user replacement cancels it.
      if (!continuingRewind) previewRewindResultRef.current?.('cancelled');
      if (sseRef.current) {
        try {
          sseRef.current?.close();
        } catch {
        } finally {
          sseRef.current = null;
          isStreamingRef.current = false;
          setIsOutputInProgress(false);
        }
      }
      isTypeFinishedRef.current = false;
      isStreamingRef.current = true;
      setIsOutputInProgress(true);
      setHasRunFailed(false);
      isInitHistoryRef.current = false;
      currentBlockIdRef.current = null;
      setCurrentStreamingElementBid('');
      setCurrentTypewriterElementBid('');
      currentContentRef.current = '';
      lastInteractionBlockRef.current = null;
      if (!isListenMode) {
        setTrackedContentList(prev => {
          const hasLoading = prev.some(isLoadingItem);
          if (hasLoading) {
            return prev;
          }
          const placeholderItem: ChatContentItem = {
            element_bid: LOADING_ITEM_BID,
            content: '',
            customRenderBar: () => <LoadingBar />,
            type: ChatContentItemType.CONTENT,
          };
          return [...prev, placeholderItem];
        });
      }

      const finishPreviewRewind =
        continuingRewind ??
        startPreviewRewindTracking({
          preview: effectivePreviewMode,
          anchor:
            sseParams.reload_element_bid ||
            sseParams.reload_generated_block_bid,
          answering: Boolean(sseParams.input),
          shifuBid,
          outlineBid,
          learningMode,
          trackEvent,
        });
      previewRewindResultRef.current = finishPreviewRewind;
      let isEnd = false;
      let didReachTerminal = false;
      // The backend follows an error with a non-terminal block end; that end
      // must not start another run, or a persistent failure retries forever.
      let didStreamFail = false;
      const clearLoadingPlaceholder = () => {
        setTrackedContentList(prev => withoutLoadingItem(prev));
      };

      let source: ReturnType<typeof getRunMessage> | null = null;

      const cleanupRunStreamState = () => {
        clearRunStreamTimeout();
        clearLoadingPlaceholder();
        isStreamingRef.current = false;
        setIsOutputInProgress(false);
        sseRef.current = null;
        const completedElementBid = currentBlockIdRef.current || '';
        if (completedElementBid) {
          setTrackedContentList(prevState =>
            finalizeElementOutputInList(prevState, completedElementBid),
          );
        }
        currentBlockIdRef.current = null;
        currentContentRef.current = '';
        setCurrentStreamingElementBid('');
        setCurrentTypewriterElementBid('');
      };

      const handleRunStreamTimeout = () => {
        if (
          !source ||
          sseRef.current !== source ||
          runSerial !== sseRunSerialRef.current
        ) {
          return;
        }

        finishPreviewRewind?.('failed');
        cleanupRunStreamState();
        setHasRunFailed(true);
        appendRunTimeoutError(runSerial);

        try {
          source.close();
        } catch {}
      };

      const armRunStreamTimeout = () => {
        clearRunStreamTimeout();
        const timeoutMs = mobileStyle
          ? MOBILE_RUN_STREAM_IDLE_TIMEOUT_MS
          : RUN_STREAM_IDLE_TIMEOUT_MS;
        runStreamTimeoutRef.current = setTimeout(() => {
          handleRunStreamTimeout();
        }, timeoutMs);
      };

      if (!effectivePreviewMode) {
        trackEvent('learner_run_start', {
          shifu_bid: shifuBid,
          outline_bid: outlineBid,
          learning_mode: learningMode,
        });
      }
      source = getRunMessage(
        shifuBid,
        outlineBid,
        effectivePreviewMode,
        {
          ...sseParams,
          listen: listenRequestEnabled,
          learning_mode: learningMode,
        },
        creditInsufficientAudience,
        async response => {
          if (
            sseRef.current !== source ||
            runSerial !== sseRunSerialRef.current
          ) {
            return;
          }
          armRunStreamTimeout();
          // if (response.type === SSE_OUTPUT_TYPE.HEARTBEAT) {
          try {
            if (response?.type === SSE_OUTPUT_TYPE.ERROR) {
              finishPreviewRewind?.('failed');
              clearRunStreamTimeout();
              setHasRunFailed(true);
              didStreamFail = true;
              const { message: errorContent, code: businessCode } =
                readRunEventError(response);
              const isCreditError =
                isCreditInsufficientBusinessCode(businessCode);
              if (isCreditError && businessCode !== undefined) {
                showCreditInsufficientToast({
                  audience: creditInsufficientAudience,
                  code: businessCode,
                });
              } else {
                const resolvedErrorToast = resolveLearnerErrorToast({
                  message: errorContent,
                  fallbackMessage: t('module.chat.requestFailed'),
                });
                const displayErrorToast = resolveAiServiceErrorToast({
                  message: resolvedErrorToast.message,
                  fallbackMessage: t('module.chat.requestFailed'),
                  includeUnknown: true,
                });

                if (displayErrorToast.isAiServiceUnavailable) {
                  toastOnce({
                    dedupeKey: AI_SERVICE_ERROR_TOAST_KEY,
                    dedupeWindowMs: AI_SERVICE_ERROR_TOAST_DEDUPE_MS,
                    title: displayErrorToast.message,
                    variant: resolvedErrorToast.variant,
                    duration: AI_SERVICE_ERROR_TOAST_DURATION_MS,
                  });
                } else {
                  toast({
                    title: displayErrorToast.message,
                    variant: resolvedErrorToast.variant,
                  });
                }
              }
              if (
                effectivePreviewMode &&
                isCreditError &&
                businessCode !== undefined &&
                errorContent
              ) {
                appendRunBusinessError(
                  getCreditInsufficientMessage(
                    creditInsufficientAudience,
                    businessCode,
                  ),
                  businessCode,
                );
              }
              return;
            }

            const nid =
              response?.content?.element_bid ||
              response?.element_bid ||
              response?.generated_block_bid ||
              '';
            if (response.type === SSE_OUTPUT_TYPE.ELEMENT) {
              if (contentListRef.current?.some(isLoadingItem)) {
                // currentBlockIdRef.current = nid;
                // close loading
                setTrackedContentList(pre => {
                  const newList = withoutLoadingItem(pre);
                  return newList;
                });
              }
            }
            const blockId = nid;
            // const blockId = currentBlockIdRef.current;

            if (response.type === SSE_OUTPUT_TYPE.ELEMENT) {
              const elementRecord = response.content as StudyRecordItem;
              const itemBid = resolveElementItemBid(elementRecord);
              const elementType = resolveRecordElementType(elementRecord);

              // Lesson completion updates can be emitted before the trailing
              // interaction controls, so keep those final interaction markers.
              if (isEnd && elementType !== ELEMENT_TYPE.INTERACTION) {
                return;
              }

              if (!itemBid) {
                return;
              }

              if (isAskOrAnswerElementType(elementType)) {
                const parentElementBid = resolveAskRecordParentBid(
                  elementRecord,
                  contentListRef.current,
                  pendingInteractionAnchorBidRef.current,
                );
                if (!parentElementBid) {
                  return;
                }
                setTrackedContentList(prevState =>
                  upsertAskMessageByParent(prevState, {
                    autoExpandAskBlock: !mobileStyle,
                    parentElementBid,
                    messageType: elementType as
                      | typeof BLOCK_TYPE.ASK
                      | typeof BLOCK_TYPE.ANSWER,
                    messageElementBid: itemBid,
                    messageGeneratedBlockBid:
                      elementRecord.generated_block_bid || itemBid,
                    messageContent: elementRecord.content || '',
                    messagePayload: elementRecord.payload,
                    insertionMode: 'anchor',
                  }),
                );
                return;
              }

              const previousStreamingElementBid = currentBlockIdRef.current;

              currentBlockIdRef.current = itemBid;
              currentContentRef.current = '';
              setCurrentStreamingElementBid(itemBid);
              if (elementType === 'text') {
                setCurrentTypewriterElementBid(itemBid);
              }

              const elementCacheIdentityBids = resolveElementCacheIdentityBids(
                elementRecord,
                itemBid,
              );
              const elementCacheIdentitySet = new Set(elementCacheIdentityBids);
              const previousItem = contentListRef.current.find(item =>
                itemMatchesElementCacheIdentity(item, elementCacheIdentitySet),
              );
              const nextItem = buildContentItem(elementRecord, {
                previousItem,
                shouldUseTypewriter:
                  previousItem?.shouldUseTypewriter ?? elementType === 'text',
              });
              const isLessonFeedbackInteraction = isLessonFeedbackContent(
                nextItem.content,
              );

              setTrackedContentList(prevState =>
                applyElementToList(prevState, nextItem, {
                  completedElementBid:
                    previousStreamingElementBid &&
                    previousStreamingElementBid !== itemBid
                      ? previousStreamingElementBid
                      : '',
                  finalize: finalizeElementOutputInList,
                  matches: item =>
                    itemMatchesElementCacheIdentity(
                      item,
                      elementCacheIdentitySet,
                    ),
                  merge: (previous, next) => ({
                    ...previous,
                    ...next,
                    listenSlides: next.listenSlides ?? previous.listenSlides,
                  }),
                }),
              );

              if (isLessonFeedbackInteraction && nextItem.element_bid) {
                openLessonFeedbackPopup({
                  elementBid: nextItem.element_bid,
                });
              }
            } else if (response.type === SSE_OUTPUT_TYPE.OUTLINE_ITEM_UPDATE) {
              const { status, outline_bid } = response.content;
              if (response.content.has_children) {
                // only update current chapter
                if (outline_bid && outline_bid === chapterId) {
                  chapterUpdate?.({
                    id: outline_bid,
                    status,
                    status_value: status,
                  });
                  if (status === LESSON_STATUS_VALUE.COMPLETED) {
                    isEnd = true;
                    setHasRunFailed(false);
                  }
                }
              } else {
                // only update current lesson
                if (outline_bid && outline_bid === lessonId) {
                  if (status === LESSON_STATUS_VALUE.COMPLETED) {
                    isEnd = true;
                    setHasRunFailed(false);
                  }
                  lessonUpdateResp(response, isEnd, finishPreviewRewind);
                }
              }
            } else if (
              // response.type === SSE_OUTPUT_TYPE.BREAK ||
              response.type === SSE_OUTPUT_TYPE.TEXT_END
            ) {
              if (readDoneIsTerminal(response) === true) {
                didReachTerminal = true;
                if (!didStreamFail) {
                  finishPreviewRewind?.('success');
                  unconfirmedAnswerRef.current = null;
                  setHasRunFailed(false);
                }
                cleanupRunStreamState();
                try {
                  source?.close?.();
                } catch {}
                return;
              }

              const completedElementBid =
                currentBlockIdRef.current || blockId || '';
              setCurrentStreamingElementBid('');
              setTrackedContentList((prev: ChatContentItem[]) => {
                let updatedList = [...prev].filter(
                  item => !isLoadingItem(item),
                );
                updatedList = finalizeElementOutputInList(
                  updatedList,
                  completedElementBid,
                );

                const lastRenderableItem = [...updatedList]
                  .reverse()
                  .find(item => item.type !== ChatContentItemType.LIKE_STATUS);
                if (
                  !isEnd &&
                  !didStreamFail &&
                  lastRenderableItem &&
                  lastRenderableItem.type === ChatContentItemType.CONTENT
                ) {
                  runRef.current?.(
                    {
                      input: '',
                      input_type: SSE_INPUT_TYPE.NORMAL,
                    },
                    finishPreviewRewind,
                  );
                }
                return updatedList;
              });
              currentBlockIdRef.current = null;
              currentContentRef.current = '';
            } else if (response.type === SSE_OUTPUT_TYPE.VARIABLE_UPDATE) {
              if (response.content.variable_name === 'sys_user_nickname') {
                updateUserInfo({
                  name: response.content.variable_value,
                });
              }
            } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_BACKFILL_READY) {
              const readyContent = response.content as
                | {
                    generated_block_bid?: string;
                    element_bids?: unknown;
                  }
                | undefined;
              const readyBlockBid =
                response.generated_block_bid ||
                readyContent?.generated_block_bid ||
                '';
              if (!readyBlockBid) {
                return;
              }

              const readyElementBids = Array.isArray(readyContent?.element_bids)
                ? readyContent.element_bids.filter(
                    (elementBid): elementBid is string =>
                      typeof elementBid === 'string' && elementBid.length > 0,
                  )
                : [];
              markLessonRunAudioBackfillReady(lessonRunContentCacheKey, [
                readyBlockBid,
                ...readyElementBids,
              ]);

              const readyBids = new Set([readyBlockBid, ...readyElementBids]);
              setTrackedContentList(prevState =>
                prevState.map(item => {
                  if (
                    item.generated_block_bid === readyBlockBid ||
                    readyBids.has(item.element_bid)
                  ) {
                    return {
                      ...item,
                      generated_block_bid:
                        item.generated_block_bid || readyBlockBid,
                      isAudioBackfillReady: true,
                    };
                  }
                  return item;
                }),
              );
            }
          } catch (error) {
            debugWarn('[lesson-run] SSE handling error', error);
          }
        },
        error => {
          if (didReachTerminal) {
            return;
          }
          const isLatestRun = runSerial === sseRunSerialRef.current;
          const isCurrentSource =
            sseRef.current === source || sseRef.current === null;
          if (!isLatestRun || !isCurrentSource) {
            return;
          }
          finishPreviewRewind?.('failed');
          const businessError = (
            error as { detail?: { code?: number; message?: string } }
          )?.detail;
          if (
            effectivePreviewMode &&
            isCreditInsufficientBusinessCode(businessError?.code) &&
            businessError?.message?.trim()
          ) {
            cleanupRunStreamState();
            setHasRunFailed(true);
            appendRunBusinessError(
              getCreditInsufficientMessage(
                creditInsufficientAudience,
                businessError.code,
              ),
              businessError.code,
            );
            return;
          }
          setHasRunFailed(true);
          cleanupRunStreamState();
        },
      );
      sseRef.current = source;
      armRunStreamTimeout();
      source.addEventListener('readystatechange', () => {
        // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
        const isActiveSource =
          sseRef.current === source && runSerial === sseRunSerialRef.current;
        if (source.readyState === 1) {
          if (isActiveSource) {
            isStreamingRef.current = true;
            setIsOutputInProgress(true);
          }
        }
        if (source.readyState === 2) {
          if (isActiveSource) {
            finishPreviewRewind?.('failed');
            // Always clear the loading placeholder when the active stream closes.
            // Some interaction flows may only emit control events before closing,
            // which still leaves the placeholder visible without this cleanup.
            cleanupRunStreamState();
          }
        }
      });
    },
    [
      buildContentItem,
      chapterId,
      chapterUpdate,
      creditInsufficientAudience,
      effectivePreviewMode,
      isListenMode,
      learningMode,
      listenRequestEnabled,
      lessonUpdateResp,
      outlineBid,
      isTypeFinishedRef,
      setTrackedContentList,
      shifuBid,
      lessonId,
      mobileStyle,
      t,
      trackEvent,
      appendRunBusinessError,
      appendRunTimeoutError,
      clearRunStreamTimeout,
      finalizeElementOutputInList,
      lessonRunContentCacheKey,
      markLessonRunAudioBackfillReady,
      openLessonFeedbackPopup,
      resolveElementItemBid,
      updateUserInfo,
    ],
  );

  useEffect(() => {
    return () => {
      clearRunStreamTimeout();
      previewRewindResultRef.current?.('cancelled');
      sseRef.current?.close();
      isStreamingRef.current = false;
    };
  }, [clearRunStreamTimeout]);

  useEffect(() => {
    const handleStopActiveLessonStream = (
      event: Event | CustomEvent<StopActiveLessonStreamDetail>,
    ) => {
      const detail = 'detail' in event ? event.detail : undefined;
      const targetLessonId = detail?.lessonId || '';
      if (targetLessonId && targetLessonId !== outlineBid) {
        return;
      }

      stopActiveRunStream();
    };

    events.addEventListener(
      BZ_EVENT_NAMES.STOP_ACTIVE_LESSON_STREAM,
      handleStopActiveLessonStream as EventListener,
    );

    return () => {
      events.removeEventListener(
        BZ_EVENT_NAMES.STOP_ACTIVE_LESSON_STREAM,
        handleStopActiveLessonStream as EventListener,
      );
    };
  }, [outlineBid, stopActiveRunStream]);

  useEffect(() => {
    runRef.current = run;
  }, [run]);

  /**
   * Transforms persisted study records into chat-friendly content items.
   */
  const mapRecordsToContent = useCallback(
    (records: StudyRecordItem[]) => {
      const result: ChatContentItem[] = [];

      // Index every element bid present in this snapshot so we can detect
      // orphan follow-ups whose anchor element is no longer surfaced
      // (reset, deactivated, or living in a different progress record).
      const presentElementBids = new Set<string>();
      for (const record of records) {
        const bid = resolveElementItemBid(record);
        if (bid) {
          presentElementBids.add(bid);
        }
      }

      records.forEach((item: StudyRecordItem) => {
        const itemBid = resolveElementItemBid(item);
        const elementType = resolveRecordElementType(item);

        if (!itemBid) {
          return;
        }

        if (isAskOrAnswerElementType(elementType)) {
          const parentElementBid = resolveAskRecordParentBid(
            item,
            result,
            pendingInteractionAnchorBidRef.current,
          );
          if (!parentElementBid) {
            return;
          }
          // Without a host element record, upsertAskMessageByParent falls
          // through to `parentContentIndex < 0` and pushes the ask to the
          // top of the chat list. Skip the orphan instead.
          if (!presentElementBids.has(parentElementBid)) {
            return;
          }
          const nextResult = upsertAskMessageByParent(result, {
            autoExpandAskBlock: !mobileStyle,
            parentElementBid,
            messageType: elementType as
              | typeof BLOCK_TYPE.ASK
              | typeof BLOCK_TYPE.ANSWER,
            messageElementBid: itemBid,
            messageGeneratedBlockBid: item.generated_block_bid || itemBid,
            messageContent: item.content || '',
            messagePayload: item.payload,
            isHistory: true,
            insertionMode: 'anchor',
          });
          result.splice(0, result.length, ...nextResult);
          return;
        }

        const nextItem = buildContentItem(item, {
          isHistory: true,
          shouldUseTypewriter: false,
        });
        const hitIndex = result.findIndex(
          contentItem => contentItem.element_bid === itemBid,
        );

        if (hitIndex < 0) {
          result.push(nextItem);
        } else {
          result[hitIndex] = {
            ...result[hitIndex],
            ...nextItem,
          };
        }

        const shouldAttachLikeStatus = shouldAttachLikeStatusByElement({
          elementBid: itemBid,
          elementType: item.element_type,
          content: nextItem.content,
        });

        if (shouldAttachLikeStatus) {
          const nextResult = upsertLikeStatusByParent(result, {
            parentElementBid: itemBid,
            likeStatus: item.like_status,
            insertAfterElementBid: itemBid,
          });
          result.splice(0, result.length, ...nextResult);
        } else {
          const nextResult = removeLikeStatusByParent(result, itemBid);
          result.splice(0, result.length, ...nextResult);
        }
      });

      return result;
    },
    [mobileStyle, buildContentItem, resolveElementItemBid],
  );

  /**
   * Loads the persisted lesson records and primes the chat stream.
   */
  // Resolves true when the lesson's history was loaded and applied by this call.
  const refreshData = useCallback(async (): Promise<boolean> => {
    if (creditInsufficientAudience === null) {
      return false;
    }
    const refreshSerial = ++refreshDataSerialRef.current;
    const isCurrentRefresh = () =>
      refreshSerial === refreshDataSerialRef.current;

    unconfirmedAnswerRef.current = null;
    resetLessonRunContent(lessonRunContentCacheKey);
    setTrackedContentList(() => []);
    resetLessonFeedbackPopup();

    isTypeFinishedRef.current = true;
    lastInteractionBlockRef.current = null;
    setIsLoading(true);
    hasScrolledToBottomRef.current = false;
    isInitHistoryRef.current = true;
    setShowLessonUpdateNotice(false);

    try {
      const recordResp = await getLessonStudyRecord({
        shifu_bid: shifuBid,
        outline_bid: outlineBid,
        preview_mode: effectivePreviewMode,
      });
      if (!isCurrentRefresh()) {
        return false;
      }
      setShowLessonUpdateNotice(
        recordResp?.has_content_update_for_current_user === true,
      );

      if (recordResp?.elements?.length > 0) {
        const contentRecords = mapRecordsToContent(recordResp.elements);
        setTrackedContentList(contentRecords);
        const latestFeedbackInteraction =
          [...contentRecords]
            .reverse()
            .find(
              item =>
                item.type === ChatContentItemType.INTERACTION &&
                isLessonFeedbackContent(item.content),
            ) ?? null;
        if (latestFeedbackInteraction?.element_bid) {
          const feedbackDefaults = getLessonFeedbackDefaults(
            latestFeedbackInteraction.user_input,
          );
          openLessonFeedbackPopup({
            elementBid: latestFeedbackInteraction.element_bid,
            defaultScoreText: feedbackDefaults.scoreText,
            defaultCommentText: feedbackDefaults.commentText,
            readonly: latestFeedbackInteraction.readonly,
            deferOpen: true,
          });
        }
        isTypeFinishedRef.current = true;
        if (chapterId) {
          setLoadedChapterId(chapterId);
        }
        if (
          recordResp.elements[recordResp.elements.length - 1].element_type !==
          ELEMENT_TYPE.INTERACTION
          //   ||
          // recordResp.elements[recordResp.elements.length - 1].element_type ===
          //   BLOCK_TYPE.ERROR
        ) {
          if (autoRunStartedForRef.current !== outlineBid) {
            autoRunStartedForRef.current = outlineBid;
            runRef.current?.({
              input: '',
              input_type: SSE_INPUT_TYPE.NORMAL,
            });
          }
        }
      } else {
        if (autoRunStartedForRef.current !== outlineBid) {
          autoRunStartedForRef.current = outlineBid;
          runRef.current?.({
            input: '',
            input_type: SSE_INPUT_TYPE.NORMAL,
          });
          // Inside the guard: the refreshes this deduplicates would otherwise each report a
          // start, and one reset would read as several in the analytics.
          if (!effectivePreviewMode) {
            trackEvent('learner_lesson_start', {
              shifu_bid: shifuBid,
              outline_bid: outlineBid,
            });
          }
        }
      }
      return true;
    } catch (error) {
      if (isCurrentRefresh()) {
        setShowLessonUpdateNotice(false);
      }
      debugWarn('[lesson-run] refreshData error', error);
      return false;
    } finally {
      if (isCurrentRefresh()) {
        setIsLoading(false);
      }
    }
  }, [
    chapterId,
    creditInsufficientAudience,
    getLessonFeedbackDefaults,
    mapRecordsToContent,
    openLessonFeedbackPopup,
    outlineBid,
    lessonRunContentCacheKey,
    resetLessonFeedbackPopup,
    resetLessonRunContent,
    // scrollToBottom,
    setTrackedContentList,
    shifuBid,
    // lessonId,
    effectivePreviewMode,
    trackEvent,
  ]);

  useEffect(() => {
    if (!chapterId) {
      return;
    }
    if (loadedChapterId === chapterId) {
      return;
    }
    setLoadedChapterId(chapterId);
  }, [chapterId, loadedChapterId]);

  useEffect(() => {
    const unsubscribe = useCourseStore.subscribe(
      state => state.resetedLessonId,
      async curr => {
        if (!curr) {
          return;
        }
        setIsLoading(true);
        if (curr === lessonId) {
          previewRewindResultRef.current?.('cancelled');
          sseRef.current?.close();
          // A reset clears the lesson, so the run that follows it is a new first run, not the
          // one already started for this lesson.
          autoRunStartedForRef.current = null;
          // Marked only once the reload has loaded the lesson. If it failed -- the history
          // request errored -- handing the reset back lets the lesson effect load it again.
          if (await refreshData()) {
            reloadedForResetRef.current = curr;
          }
          // updateResetedChapterId(null);
          // @ts-expect-error resetedLessonId can be null per store design
          updateResetedLessonId(null);
        }
        setIsLoading(false);
      },
    );

    return () => {
      unsubscribe();
    };
  }, [
    loadedChapterId,
    refreshData,
    updateResetedLessonId,
    resetedLessonId,
    lessonId,
  ]);

  useEffect(() => {
    const unsubscribe = useUserStore.subscribe(
      state => state.isLoggedIn,
      isLoggedIn => {
        if (!isLoggedIn || !chapterId) {
          return;
        }
        setLoadedChapterId(chapterId);
        refreshData();
      },
    );

    return () => {
      unsubscribe();
    };
  }, [chapterId, refreshData]);

  // Only the open lesson's own reset concerns the effect below. The store's reset fields name
  // whichever lesson is being reset, and a reset of another lesson from the catalog, with this
  // one staying open, would otherwise re-run it: close this lesson's stream and start its run
  // again.
  const isResettingOpenLesson =
    Boolean(lessonId) && resettingLessonId === lessonId;
  const hasResetLandedForOpenLesson =
    Boolean(lessonId) && resetedLessonId === lessonId;

  useEffect(() => {
    // A mark for another lesson is stale: the learner moved on before the reset was handed back.
    if (reloadedForResetRef.current !== lessonId) {
      reloadedForResetRef.current = null;
    }
    // The reset is being handed back for the lesson the subscription has just reloaded. That
    // load is this lesson's; closing its run and loading again would start the same run twice.
    if (
      lessonId &&
      !hasResetLandedForOpenLesson &&
      reloadedForResetRef.current === lessonId
    ) {
      reloadedForResetRef.current = null;
      return;
    }
    // The reset of this lesson has landed and the subscription is reloading it; closing here
    // could close the run that reload has just started.
    if (hasResetLandedForOpenLesson) {
      return;
    }
    previewRewindResultRef.current?.('cancelled');
    sseRef.current?.close();
    if (!lessonId || creditInsufficientAudience === null) {
      return;
    }
    // This lesson is being reset. Confirming a reset from the catalog also opens the lesson, so
    // it arrives here before the reset has landed: loading it now would start a run on the
    // lesson as it was, which the reset's own reload then closes -- measured: two runs 70ms
    // apart, the first still taught and billed. The subscription loads it once the reset lands;
    // if the reset fails, clearing `resettingLessonId` brings the load back here.
    if (isResettingOpenLesson) {
      return;
    }
    // Opening a lesson is a fresh load, so whatever was started for the lesson left behind does
    // not speak for this one. Without this, coming back to a lesson whose history ends in text
    // -- which the host continues by itself -- would find its own mark still set and stall.
    autoRunStartedForRef.current = null;
    refreshData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    creditInsufficientAudience,
    lessonId,
    hasResetLandedForOpenLesson,
    isResettingOpenLesson,
  ]);

  useEffect(() => {
    const onGoToNavigationNode = (
      event: CustomEvent<{ chapterId: string; lessonId: string }>,
    ) => {
      const { chapterId: targetChapterId, lessonId: targetLessonId } =
        event.detail;
      if (targetChapterId !== loadedChapterId) {
        return;
      }
      isTypeFinishedRef.current = true;
      lastInteractionBlockRef.current = null;
      scrollToLesson(targetLessonId);
      updateSelectedLesson(targetLessonId);
    };

    events.addEventListener(
      BZ_EVENT_NAMES.GO_TO_NAVIGATION_NODE,
      onGoToNavigationNode as EventListener,
    );

    return () => {
      events.removeEventListener(
        BZ_EVENT_NAMES.GO_TO_NAVIGATION_NODE,
        onGoToNavigationNode as EventListener,
      );
    };
  }, [loadedChapterId, scrollToLesson, updateSelectedLesson]);

  /**
   * updateContentListWithUserOperate rewinds the list to the chosen interaction point.
   */
  const updateContentListWithUserOperate = useCallback(
    (
      params: OnSendContentParams,
      blockBid: string,
      options?: { truncateFollowingItems?: boolean },
    ): { newList: ChatContentItem[]; needChangeItemIndex: number } => {
      const { items: newList, index: needChangeItemIndex } =
        updateInteractionItems(contentListRef.current, params, blockBid, {
          truncateFollowingItems:
            Boolean(options?.truncateFollowingItems) || !isListenMode,
          preserveHelpers: !options?.truncateFollowingItems && !isListenMode,
        });
      if (needChangeItemIndex !== -1) setTrackedContentList(newList);
      return { newList, needChangeItemIndex };
    },
    [isListenMode, setTrackedContentList],
  );

  /**
   * If the frontend still thinks a run is streaming but the backend no longer
   * reports an active run, clear the stale local guard so retry / resend can proceed.
   */
  const hasActiveRunInProgress = useCallback(
    async (options?: { swallowRequestError?: boolean }) => {
      const runningRes = await checkIsRunning(shifuBid, outlineBid).catch(
        error => {
          if (options?.swallowRequestError) {
            return undefined;
          }
          throw error;
        },
      );

      if (runningRes === undefined) {
        return true;
      }

      if (runningRes?.is_running) {
        return true;
      }

      if (isStreamingRef.current) {
        stopActiveRunStream();
      }

      return false;
    },
    [outlineBid, shifuBid, stopActiveRunStream],
  );

  /**
   * onRefresh replays a block from the server using the original inputs.
   */
  const onRefresh = useCallback(
    async (elementBid: string) => {
      if (await hasActiveRunInProgress({ swallowRequestError: true })) {
        showOutputInProgressToast();
        return;
      }

      const sourceBlockBid = resolveSourceGeneratedBlockBid(elementBid);

      const newList = [...contentListRef.current];
      const needChangeItemIndex = newList.findIndex(
        item => item.element_bid === elementBid,
      );
      if (needChangeItemIndex === -1) {
        showOutputInProgressToast();
        return;
      }

      const firstBlockIndex = newList.findIndex(
        item =>
          resolveSourceGeneratedBlockBid(item.element_bid) === sourceBlockBid,
      );
      newList.length =
        firstBlockIndex === -1 ? needChangeItemIndex : firstBlockIndex;
      setTrackedContentList(newList);

      isTypeFinishedRef.current = false;
      runRef.current?.({
        input: '',
        input_type: SSE_INPUT_TYPE.NORMAL,
        reload_generated_block_bid: sourceBlockBid,
        reload_element_bid: elementBid,
      });
    },
    [
      hasActiveRunInProgress,
      isTypeFinishedRef,
      resolveSourceGeneratedBlockBid,
      setTrackedContentList,
      showOutputInProgressToast,
    ],
  );

  /**
   * onSend processes user interactions and continues streaming responses.
   */
  const processSend = useCallback(
    async (
      content: OnSendContentParams,
      blockBid: string,
      options?: { skipConfirm?: boolean },
    ) => {
      if (creditInsufficientAudience === null) {
        return;
      }
      const { variableName, buttonText, inputText } = content;
      const sourceBlockBid = resolveSourceGeneratedBlockBid(blockBid);
      const currentInteractionItem = contentListRef.current.find(
        item => item.element_bid === blockBid,
      );
      const isLessonFeedbackInteraction =
        variableName === LESSON_FEEDBACK_VARIABLE_NAME ||
        isLessonFeedbackContent(currentInteractionItem?.content);

      if (buttonText === SYS_INTERACTION_TYPE.PAY) {
        trackEvent(EVENT_NAMES.POP_PAY, { from: 'show-btn' });
        onPayModalOpen();
        return;
      }
      if (buttonText === SYS_INTERACTION_TYPE.LOGIN) {
        if (typeof window !== 'undefined') {
          const redirect = encodeURIComponent(
            window.location.pathname + window.location.search,
          );
          window.location.href = `/login?redirect=${redirect}`;
        }
        return;
      }
      if (buttonText === SYS_INTERACTION_TYPE.NEXT_CHAPTER) {
        const emitLessonFeedbackSkip = (
          feedbackBlockBid: string,
          feedbackItem?: ChatContentItem,
          selectedScoreRaw?: string | null,
          commentFromActionRaw?: string,
        ) => {
          const persistedDefaults = getLessonFeedbackDefaults(
            feedbackItem?.user_input,
          );
          const persistedScore = parseLessonFeedbackScore(
            persistedDefaults.scoreText,
          );
          const selectedScore = parseLessonFeedbackScore(selectedScoreRaw);
          const commentFromAction = (commentFromActionRaw || '').trim();
          const persistedComment = persistedDefaults.commentText.trim();
          const effectiveComment = commentFromAction || persistedComment;
          trackEvent(EVENT_NAMES.LESSON_FEEDBACK_SKIP, {
            shifu_bid: shifuBid,
            outline_bid: outlineBid,
            element_bid: resolveSourceGeneratedBlockBid(feedbackBlockBid),
            mode: isListenMode ? 'listen' : 'read',
            trigger_scene: 'before_next_lesson',
            had_selected_score: Boolean(selectedScore || persistedScore),
            had_input_comment: Boolean(effectiveComment),
            comment_length: effectiveComment.length,
          });
        };

        if (isLessonFeedbackInteraction) {
          emitLessonFeedbackSkip(
            blockBid,
            currentInteractionItem,
            content.selectedValues?.[0],
            inputText,
          );
          dismissLessonFeedbackPopup();
        } else if (lessonFeedbackPopupState.elementBid) {
          const pendingFeedbackBlockBid = lessonFeedbackPopupState.elementBid;
          const pendingFeedbackItem = contentListRef.current.find(
            item => item.element_bid === pendingFeedbackBlockBid,
          );
          if (pendingFeedbackItem?.content) {
            if (isLessonFeedbackContent(pendingFeedbackItem.content)) {
              emitLessonFeedbackSkip(
                pendingFeedbackBlockBid,
                pendingFeedbackItem,
                undefined,
                undefined,
              );
              dismissLessonFeedbackPopup();
            }
          }
        }
        const nextLessonId = getNextLessonId(lessonId);
        if (nextLessonId) {
          updateSelectedLesson(nextLessonId, true);
          onGoChapter(nextLessonId);
          scrollToLesson(nextLessonId);
        } else {
          showToast(t('module.chat.noMoreLessons'));
        }
        return;
      }

      if (isLessonFeedbackInteraction) {
        const score =
          parseLessonFeedbackScore(buttonText) ||
          parseLessonFeedbackScore(
            getLessonFeedbackDefaults(currentInteractionItem?.user_input)
              .scoreText,
          );
        if (!score) {
          toast({ title: t('module.chat.lessonFeedbackScoreRequired') });
          return;
        }
        const comment = (inputText || '').trim();
        const persistedDefaults = getLessonFeedbackDefaults(
          currentInteractionItem?.user_input,
        );
        const persistedScore = parseLessonFeedbackScore(
          persistedDefaults.scoreText,
        );
        const persistedComment = persistedDefaults.commentText.trim();
        submitLessonFeedback({
          shifu_bid: shifuBid,
          outline_bid: outlineBid,
          score,
          comment,
          mode: isListenMode ? 'listen' : 'read',
        })
          .then(() => {
            syncLessonFeedbackInteractionValues(
              blockBid,
              String(score),
              comment,
            );
            dismissLessonFeedbackPopup();
            trackEvent(EVENT_NAMES.LESSON_FEEDBACK_SUBMIT, {
              shifu_bid: shifuBid,
              outline_bid: outlineBid,
              generated_block_bid: sourceBlockBid,
              mode: isListenMode ? 'listen' : 'read',
              trigger_scene: 'before_next_lesson',
              score,
              has_comment: Boolean(comment),
              comment_length: comment.length,
              is_update: Boolean(persistedScore || persistedComment),
            });
            toast({ title: t('module.chat.lessonFeedbackSubmitted') });
          })
          .catch(() => {
            // request.ts already handles global error display
          });
        return;
      }

      // Keep the active-run guard for the current question before first output;
      // its accepting checkpoint may not be durable yet.
      const pendingAnswer = unconfirmedAnswerRef.current;
      const beforeSubmission =
        pendingAnswer?.elementBid === blockBid
          ? pendingAnswer.previousAnswer
          : undefined;
      const submission = classifyLearnerInteraction(
        contentListRef.current,
        blockBid,
        content,
        {
          isStreaming: isStreamingRef.current,
          beforeSubmission: isStreamingRef.current
            ? undefined
            : beforeSubmission,
        },
      );
      if (submission === 'repeat') return;
      const isReGenerate = submission === 'rewind';

      if (isReGenerate && !options?.skipConfirm) {
        setPendingRegenerate({ content, blockBid });
        setShowRegenerateConfirm(true);
        return;
      }

      if (
        !isReGenerate &&
        (await hasActiveRunInProgress({ swallowRequestError: true }))
      ) {
        showOutputInProgressToast();
        return;
      }

      // Confirmed regenerate while a stream is still flowing: close the
      // current SSE locally before issuing the reload request so its late
      // chunks cannot bleed into the new run's list.
      if (isReGenerate && isStreamingRef.current) {
        stopActiveRunStream();
      }

      if (currentInteractionItem?.type === ChatContentItemType.INTERACTION) {
        // The optimistic answer is not evidence of acceptance if the stream fails.
        unconfirmedAnswerRef.current = {
          elementBid: blockBid,
          previousAnswer:
            beforeSubmission ?? currentInteractionItem.user_input ?? '',
        };
      }
      const { newList, needChangeItemIndex } = updateContentListWithUserOperate(
        content,
        blockBid,
        { truncateFollowingItems: isReGenerate },
      );

      if (needChangeItemIndex === -1) {
        setTrackedContentList(newList);
      }

      pendingInteractionAnchorBidRef.current =
        currentInteractionItem?.type === ChatContentItemType.INTERACTION
          ? blockBid
          : '';
      isTypeFinishedRef.current = false;

      const { values } = resolveInteractionSubmission(content);
      const reload_generated_block_bid = isReGenerate
        ? sourceBlockBid
        : undefined;
      runRef.current?.({
        input: {
          // No-variable interactions have an empty variableName; submit
          // under the canonical "input" key (markdown-flow contract),
          // matching the editor Debug flow in debug-request-params.ts.
          [variableName || 'input']: values,
        },
        input_type: SSE_INPUT_TYPE.NORMAL,
        reload_element_bid: isReGenerate ? blockBid : undefined,
        reload_generated_block_bid,
      });
    },
    [
      creditInsufficientAudience,
      dismissLessonFeedbackPopup,
      getLessonFeedbackDefaults,
      getNextLessonId,
      isTypeFinishedRef,
      hasActiveRunInProgress,
      isListenMode,
      lessonId,
      lessonFeedbackPopupState.elementBid,
      syncLessonFeedbackInteractionValues,
      onGoChapter,
      onPayModalOpen,
      outlineBid,
      parseLessonFeedbackScore,
      scrollToLesson,
      setTrackedContentList,
      shifuBid,
      showOutputInProgressToast,
      trackEvent,
      resolveSourceGeneratedBlockBid,
      stopActiveRunStream,
      updateContentListWithUserOperate,
      updateSelectedLesson,
      t,
    ],
  );

  const onSend = useCallback(
    (content: OnSendContentParams, blockBid: string) => {
      void processSend(content, blockBid);
    },
    [processSend],
  );

  const handleConfirmRegenerate = useCallback(() => {
    if (!pendingRegenerate) {
      setShowRegenerateConfirm(false);
      return;
    }
    void processSend(pendingRegenerate.content, pendingRegenerate.blockBid, {
      skipConfirm: true,
    });
    setPendingRegenerate(null);
    setShowRegenerateConfirm(false);
  }, [pendingRegenerate, processSend]);

  const handleCancelRegenerate = useCallback(() => {
    setPendingRegenerate(null);
    setShowRegenerateConfirm(false);
  }, []);

  /**
   * toggleAskExpanded toggles the expanded state of the ask panel for a specific block
   */
  const toggleAskExpanded = useCallback(
    (parentElementBid: string) => {
      setTrackedContentList(prev => {
        const askEntries = prev
          .map((item, index) => ({ item, index }))
          .filter(
            ({ item }) =>
              item.parent_element_bid === parentElementBid &&
              item.type === ChatContentItemType.ASK,
          );

        if (askEntries.length > 0) {
          const primaryAskEntry = askEntries[askEntries.length - 1];
          const primaryAskIndex = primaryAskEntry.index;
          const primaryAskItem = primaryAskEntry.item;
          const toggledExpanded = !prev[primaryAskIndex].isAskExpanded;
          // Keep one ASK block per parent element to avoid duplicated input boxes.
          return prev
            .filter(
              (item, index) =>
                !(
                  index !== primaryAskIndex &&
                  item.parent_element_bid === parentElementBid &&
                  item.type === ChatContentItemType.ASK
                ),
            )
            .map(item =>
              item === primaryAskItem
                ? { ...item, isAskExpanded: toggledExpanded }
                : item,
            );
        }

        // Create a new ASK block next to the target element when needed.
        const nextAskBlock: ChatContentItem = {
          element_bid: '',
          parent_element_bid: parentElementBid,
          type: ChatContentItemType.ASK,
          content: '',
          isAskExpanded: true,
          ask_list: [],
          readonly: false,
          customRenderBar: () => null,
          user_input: '',
        };
        const likeStatusIndex = prev.findIndex(
          item =>
            item.parent_element_bid === parentElementBid &&
            item.type === ChatContentItemType.LIKE_STATUS,
        );
        const parentContentIndex =
          likeStatusIndex >= 0
            ? likeStatusIndex
            : prev.findIndex(item => item.element_bid === parentElementBid);

        if (parentContentIndex < 0) {
          return [...prev, nextAskBlock];
        }

        const nextList = [...prev];
        nextList.splice(parentContentIndex + 1, 0, nextAskBlock);
        return nextList;
      });
    },
    [setTrackedContentList],
  );

  const syncAskListByParentElement = useCallback(
    (
      parentElementBid: string,
      askList: ChatContentItem[],
      options?: {
        expand?: boolean;
      },
    ) => {
      if (!parentElementBid) {
        return;
      }

      setTrackedContentList(prev => {
        const shouldAutoExpandAskBlock = !mobileStyle;
        const normalizedAskList = askList.map((message, index) => {
          const fallbackElementBid = `${message.type}-${parentElementBid}-${index}`;
          const resolvedElementBid =
            message.element_bid ||
            message.generated_block_bid ||
            fallbackElementBid;

          return {
            ...message,
            element_bid: resolvedElementBid,
            generated_block_bid:
              message.generated_block_bid || resolvedElementBid,
            parent_element_bid: parentElementBid,
            content: message.content || '',
            readonly: message.readonly ?? true,
            user_input: message.user_input || '',
          };
        });
        const askEntries = prev
          .map((item, index) => ({ item, index }))
          .filter(
            ({ item }) =>
              item.parent_element_bid === parentElementBid &&
              item.type === ChatContentItemType.ASK,
          );

        if (askEntries.length > 0) {
          const primaryAskEntry = askEntries[askEntries.length - 1];
          const primaryAskIndex = primaryAskEntry.index;
          const primaryAskItem = primaryAskEntry.item;

          return prev
            .filter(
              (item, index) =>
                !(
                  index !== primaryAskIndex &&
                  item.parent_element_bid === parentElementBid &&
                  item.type === ChatContentItemType.ASK
                ),
            )
            .map(item =>
              item === primaryAskItem
                ? {
                    ...item,
                    ask_list: normalizedAskList,
                    isAskExpanded:
                      options?.expand ??
                      item.isAskExpanded ??
                      shouldAutoExpandAskBlock,
                  }
                : item,
            );
        }

        const nextAskBlock: ChatContentItem = {
          element_bid: '',
          parent_element_bid: parentElementBid,
          type: ChatContentItemType.ASK,
          content: '',
          isAskExpanded: options?.expand ?? shouldAutoExpandAskBlock,
          ask_list: normalizedAskList,
          readonly: false,
          customRenderBar: () => null,
          user_input: '',
        };
        const likeStatusIndex = prev.findIndex(
          item =>
            item.parent_element_bid === parentElementBid &&
            item.type === ChatContentItemType.LIKE_STATUS,
        );
        const parentContentIndex =
          likeStatusIndex >= 0
            ? likeStatusIndex
            : prev.findIndex(item => item.element_bid === parentElementBid);

        if (parentContentIndex < 0) {
          return [...prev, nextAskBlock];
        }

        const nextList = [...prev];
        nextList.splice(parentContentIndex + 1, 0, nextAskBlock);
        return nextList;
      });
    },
    [mobileStyle, setTrackedContentList],
  );

  // Create a stable null render bar function
  const nullRenderBar = useCallback(() => null, []);

  const items = useMemo(
    () =>
      contentList.map(item => ({
        ...item,
        customRenderBar: item.customRenderBar || nullRenderBar,
      })),
    [contentList, nullRenderBar],
  );

  const closeTtsStream = useCallback((blockId: string) => {
    const source = ttsSseRef.current[blockId];
    if (!source) {
      delete ttsStreamCancelRef.current[blockId];
      return;
    }
    source.close();
    delete ttsSseRef.current[blockId];
    delete ttsStreamCancelRef.current[blockId];
  }, []);

  const requestAudioForBlock = useCallback(
    async (
      elementBid: string,
      options: RequestAudioForBlockOptions = {},
    ): Promise<AudioCompleteData | null | undefined> => {
      // `undefined` marks "never attempted" so callers can tell a cancelled or
      // de-duplicated request apart from a real synthesis failure.
      if (!elementBid) {
        return undefined;
      }
      if (creditInsufficientAudience === null) {
        return null;
      }

      const {
        elementBid: targetElementBid,
        generatedBlockBid: sourceBlockBid,
      } = resolveAudioBlockTarget(elementBid);
      const effectiveListenRequestEnabled =
        options.listen ?? listenRequestEnabled;
      const shouldApplyResult = () => options.shouldApplyResult?.() ?? true;
      const notifyStreamSettled = (() => {
        let hasSettled = false;
        return () => {
          if (hasSettled) {
            return;
          }
          hasSettled = true;
          options.onStreamSettled?.();
        };
      })();

      if (!allowTtsStreaming) {
        notifyStreamSettled();
        return undefined;
      }

      if (!shouldApplyResult()) {
        notifyStreamSettled();
        return undefined;
      }

      const existingItem = findAudioTargetItem(
        contentListRef.current,
        targetElementBid,
      );
      const cachedTrack = getAudioTrackByPosition(
        existingItem?.audioTracks ?? [],
      );
      if (
        !effectiveListenRequestEnabled &&
        cachedTrack?.audioUrl &&
        !cachedTrack.isAudioStreaming
      ) {
        notifyStreamSettled();
        return {
          audio_url: cachedTrack.audioUrl,
          audio_bid: '',
          duration_ms: cachedTrack.durationMs ?? 0,
        };
      }

      if (ttsSseRef.current[sourceBlockBid]) {
        // Another stream for this block is already in flight; de-duplicating is
        // not a failure, so the caller must be able to retry later.
        notifyStreamSettled();
        return undefined;
      }

      setTrackedContentList(prev =>
        updateNestedAskMessageAudioStreaming(
          prev.map(item => {
            if (!matchesElementBid(item, targetElementBid)) {
              return item;
            }

            return {
              ...item,
              audioTracks: [],
              audioUrl: undefined,
              audioDurationMs: undefined,
              isAudioStreaming: true,
            };
          }),
          targetElementBid,
          sourceBlockBid,
          true,
        ),
      );

      return new Promise((resolve, reject) => {
        let finalizeTimer: ReturnType<typeof setTimeout> | null = null;
        let idleTimer: ReturnType<typeof setTimeout> | null = null;
        let latestComplete: AudioCompleteData | null = null;
        let hasResolved = false;

        const clearTimers = () => {
          if (finalizeTimer) {
            clearTimeout(finalizeTimer);
            finalizeTimer = null;
          }
          if (idleTimer) {
            clearTimeout(idleTimer);
            idleTimer = null;
          }
        };

        const resolveOnce = (value: AudioCompleteData | null | undefined) => {
          if (hasResolved) {
            return;
          }
          hasResolved = true;
          resolve(value);
        };

        const markAudioStreamSettled = () => {
          if (!shouldApplyResult()) {
            return;
          }
          setTrackedContentList(prev =>
            updateNestedAskMessageAudioStreaming(
              prev.map(item => {
                const isSourceBlockItem =
                  Boolean(sourceBlockBid) &&
                  item.type === ChatContentItemType.CONTENT &&
                  item.generated_block_bid === sourceBlockBid;
                if (
                  !matchesElementBid(item, targetElementBid) &&
                  !isSourceBlockItem
                ) {
                  return item;
                }
                return {
                  ...item,
                  isAudioStreaming: false,
                  audioTracks: (item.audioTracks ?? []).map(track => ({
                    ...track,
                    isAudioStreaming: false,
                  })),
                };
              }),
              targetElementBid,
              sourceBlockBid,
              false,
            ),
          );
        };

        const finishStream = (value: AudioCompleteData | null) => {
          clearTimers();
          markAudioStreamSettled();
          closeTtsStream(sourceBlockBid);
          notifyStreamSettled();
          resolveOnce(value);
        };

        const cancelStream: TtsStreamCancel = ({ updateState = true } = {}) => {
          clearTimers();
          if (updateState) {
            markAudioStreamSettled();
          }
          // Cancellation is not a synthesis failure. Submitting an interaction
          // tears down every in-flight TTS stream, so resolving as `null` here
          // would permanently blacklist those blocks and silence all narration
          // generated after the answer.
          resolveOnce(undefined);
          closeTtsStream(sourceBlockBid);
          notifyStreamSettled();
        };

        const resolveAudioEventTargetElementBid = (
          eventTarget?: {
            position?: number;
            stream_element_number?: number;
            streamElementNumber?: number;
          } | null,
        ) => {
          const blockItems = contentListRef.current.filter(
            item =>
              item.type === ChatContentItemType.CONTENT &&
              item.generated_block_bid === sourceBlockBid,
          );
          const speakableBlockItems = blockItems.filter(
            item => item.is_speakable !== false,
          );
          const streamElementNumber =
            normalizeOptionalNumber(eventTarget?.stream_element_number) ??
            normalizeOptionalNumber(eventTarget?.streamElementNumber);
          if (streamElementNumber !== undefined) {
            const matchedItem = speakableBlockItems.find(
              item => Number(item.element_index) === streamElementNumber,
            );
            if (matchedItem?.element_bid) {
              return matchedItem.element_bid;
            }
          }

          const position = normalizeOptionalNumber(eventTarget?.position);
          if (position !== undefined) {
            const matchedItem = speakableBlockItems[position];
            if (matchedItem?.element_bid) {
              return matchedItem.element_bid;
            }
          }

          return targetElementBid;
        };

        const resetIdleTimer = () => {
          if (!effectiveListenRequestEnabled) {
            return;
          }
          if (idleTimer) {
            clearTimeout(idleTimer);
          }
          idleTimer = setTimeout(() => {
            finishStream(latestComplete);
          }, TTS_BACKFILL_IDLE_TIMEOUT_MS);
        };

        const source = streamGeneratedBlockAudio({
          shifu_bid: shifuBid,
          generated_block_bid: sourceBlockBid,
          preview_mode: effectivePreviewMode,
          listen: effectiveListenRequestEnabled,
          creditInsufficientAudience,
          onMessage: response => {
            resetIdleTimer();

            if (response?.type === SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
              if (!shouldApplyResult()) {
                finishStream(null);
                return;
              }

              const audioPayload = response.content ?? response.data;
              const audioSegment = normalizeAudioSegmentPayload(audioPayload);
              if (!audioSegment) {
                return;
              }
              const audioTargetElementBid =
                resolveAudioEventTargetElementBid(audioSegment);
              const audioSegmentData = toAudioSegmentData(audioSegment);
              setTrackedContentList(prevState =>
                upsertNestedAskAudioSegment(
                  upsertAudioSegment(
                    prevState,
                    audioTargetElementBid,
                    audioSegmentData,
                  ),
                  audioTargetElementBid,
                  audioSegmentData,
                ),
              );
              return;
            }

            if (response?.type === SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
              if (!shouldApplyResult()) {
                finishStream(null);
                return;
              }

              const audioPayload = response.content ?? response.data;
              const audioComplete = normalizeAudioCompletePayload(audioPayload);
              if (!audioComplete) {
                return;
              }
              latestComplete = audioComplete ?? latestComplete;
              const audioTargetElementBid =
                resolveAudioEventTargetElementBid(audioComplete);
              setTrackedContentList(prevState =>
                upsertNestedAskAudioComplete(
                  upsertAudioComplete(
                    prevState,
                    audioTargetElementBid,
                    audioComplete,
                  ),
                  audioTargetElementBid,
                  audioComplete,
                ),
              );
              if (effectiveListenRequestEnabled) {
                return;
              }
              clearTimers();
              finalizeTimer = setTimeout(() => {
                finishStream(latestComplete ?? null);
              }, 0);
              return;
            }

            if (response?.type === SSE_OUTPUT_TYPE.TEXT_END) {
              finishStream(latestComplete);
            }
          },
          onError: () => {
            clearTimers();
            markAudioStreamSettled();
            closeTtsStream(sourceBlockBid);
            notifyStreamSettled();
            if (!hasResolved) {
              hasResolved = true;
              reject(new Error('TTS stream failed'));
            }
          },
        });

        ttsSseRef.current[sourceBlockBid] = source;
        ttsStreamCancelRef.current[sourceBlockBid] = cancelStream;
        resetIdleTimer();
      });
    },
    [
      allowTtsStreaming,
      closeTtsStream,
      creditInsufficientAudience,
      effectivePreviewMode,
      listenRequestEnabled,
      resolveAudioBlockTarget,
      setTrackedContentList,
      shifuBid,
    ],
  );

  useEffect(() => {
    return () => {
      Object.values(ttsStreamCancelRef.current).forEach(cancel => {
        cancel({ updateState: false });
      });
      Object.values(ttsSseRef.current).forEach(source => {
        source?.close?.();
      });
      ttsStreamCancelRef.current = {};
      ttsSseRef.current = {};
    };
  }, []);

  const handleLessonFeedbackPopupSubmit = useCallback(
    (score: number, comment: string) => {
      const blockBid = lessonFeedbackPopupState.elementBid;
      if (!blockBid) {
        return;
      }
      void processSend(
        {
          variableName: LESSON_FEEDBACK_VARIABLE_NAME,
          buttonText: String(score),
          inputText: comment,
        },
        blockBid,
      );
    },
    [lessonFeedbackPopupState.elementBid, processSend],
  );

  const handleLessonFeedbackPopupClose = useCallback(() => {
    const blockBid = lessonFeedbackPopupState.elementBid;
    if (!blockBid) {
      return;
    }
    dismissLessonFeedbackPopup();
  }, [lessonFeedbackPopupState.elementBid, dismissLessonFeedbackPopup]);

  return {
    items,
    isLoading,
    isOutputInProgress,
    hasRunFailed,
    currentStreamingElementBid,
    currentTypewriterElementBid,
    onSend,
    onRefresh,
    toggleAskExpanded,
    syncAskListByParentElement,
    requestAudioForBlock,
    reGenerateConfirm: {
      open: showRegenerateConfirm,
      onConfirm: handleConfirmRegenerate,
      onCancel: handleCancelRegenerate,
    },
    lessonFeedbackPopup: {
      open:
        shouldPromptLessonFeedback &&
        lessonFeedbackPopupState.outlineBid === outlineBid &&
        lessonFeedbackPopupState.modeKey ===
          (isListenMode ? 'listen' : 'read') &&
        lessonFeedbackPopupState.open &&
        Boolean(lessonFeedbackPopupState.elementBid),
      elementBid: lessonFeedbackPopupState.elementBid,
      defaultScoreText: lessonFeedbackPopupState.defaultScoreText,
      defaultCommentText: lessonFeedbackPopupState.defaultCommentText,
      readonly: lessonFeedbackPopupState.readonly,
      onClose: handleLessonFeedbackPopupClose,
      onSubmit: handleLessonFeedbackPopupSubmit,
    },
    showLessonUpdateNotice,
  };
}

export default useLessonConversation;

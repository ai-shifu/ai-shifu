import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useContext,
  useMemo,
} from 'react';
import React from 'react';
import { useLatest, useMountedState } from 'react-use';
import {
  mergeStreamingMarkdownText,
  maskIncompleteMermaidBlock,
} from '@/c-utils/markdownUtils';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useUserStore } from '@/store';
import { useShallow } from 'zustand/react/shallow';
import {
  StudyRecordItem,
  LikeStatus,
  AudioCompleteData,
  type AudioSegmentData,
  type ListenSlideData,
  type ElementType,
  getRunMessage,
  SSE_INPUT_TYPE,
  getLessonStudyRecord,
  SSE_OUTPUT_TYPE,
  SYS_INTERACTION_TYPE,
  LESSON_FEEDBACK_VARIABLE_NAME,
  LESSON_FEEDBACK_INTERACTION_MARKER,
  LIKE_STATUS,
  BLOCK_TYPE,
  checkIsRunning,
  streamGeneratedBlockAudio,
  submitLessonFeedback,
  ELEMENT_TYPE,
} from '@/c-api/studyV2';
import {
  getAudioSegmentDataListFromTracks,
  getAudioTrackByPosition,
  mergeAudioSegmentDataList,
  normalizeAudioCompletePayload,
  normalizeAudioSegmentPayload,
  normalizeAudioSubtitleCues,
  sortAudioTracksByPosition,
  toAudioSegmentData,
  upsertAudioComplete,
  upsertAudioSegment,
  type AudioTrack,
} from '@/c-utils/audio-utils';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
  type StopActiveLessonStreamDetail,
} from '@/app/c/[[...id]]/events';
import { EVENT_NAMES } from '@/c-common/hooks/useTracking';
import {
  buildLessonFeedbackUserInput,
  parseLessonFeedbackUserInput,
  resolveInteractionSubmission,
} from '@/c-utils/interaction-user-input';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import LoadingBar from './LoadingBar';
import { useTranslation } from 'react-i18next';
import { show as showToast, toast } from '@/hooks/useToast';
import { AppContext } from '../AppContext';
import {
  normalizeLegacyBlockCompatList,
  stripCustomButtonAfterContent,
} from './chatUiUtils';
import {
  buildLessonRunContentCacheKey,
  EMPTY_LESSON_RUN_CONTENT_ENTRY,
  EMPTY_LESSON_RUN_ITEMS,
  useLessonRunContentStore,
} from '@/c-store/useLessonRunContentStore';

interface LessonFeedbackPopupState {
  open: boolean;
  outlineBid: string;
  modeKey: 'listen' | 'read' | '';
  elementBid: string;
  defaultScoreText: string;
  defaultCommentText: string;
  readonly: boolean;
}

const LESSON_FEEDBACK_DISMISS_CACHE_LIMIT = 200;
const RUN_STREAM_IDLE_TIMEOUT_MS = 15000;
const MOBILE_RUN_STREAM_IDLE_TIMEOUT_MS = 60000;
const TTS_BACKFILL_IDLE_TIMEOUT_MS = 120000;
const STREAM_TIMEOUT_ITEM_BID_PREFIX = 'stream-timeout-error';
const DEFAULT_LISTEN_AUDIO_POSITION = 0;
const CREDIT_INSUFFICIENT_ERROR_CODE = 7101;

export { ChatContentItemType };
export type { ChatContentItem };

interface SSEParams {
  input: string | Record<string, any>;
  input_type: SSE_INPUT_TYPE;
  reload_generated_block_bid?: string;
  reload_element_bid?: string;
}

interface RequestAudioForBlockOptions {
  listen?: boolean;
  shouldApplyResult?: () => boolean;
  onStreamSettled?: () => void;
}

type TtsStreamCancel = (options?: { updateState?: boolean }) => void;

const normalizeOptionalNumber = (value: unknown) => {
  if (value === undefined || value === null) {
    return undefined;
  }

  const normalized = Number(value);
  return Number.isFinite(normalized) ? normalized : undefined;
};

const resolveStudyRecordAudioComplete = (
  record: StudyRecordItem,
): Partial<AudioCompleteData> | null => {
  const audioPayload = record.payload?.audio as
    | Record<string, unknown>
    | undefined;
  const audioUrl =
    (typeof record.audio_url === 'string' && record.audio_url.trim()) ||
    (typeof audioPayload?.audio_url === 'string' &&
      audioPayload.audio_url.trim()) ||
    '';

  if (!audioUrl) {
    return null;
  }

  const audioBid =
    typeof audioPayload?.audio_bid === 'string'
      ? audioPayload.audio_bid
      : undefined;
  const durationMs = normalizeOptionalNumber(audioPayload?.duration_ms);
  const position = normalizeOptionalNumber(audioPayload?.position);
  const slideId =
    typeof audioPayload?.slide_id === 'string'
      ? audioPayload.slide_id
      : undefined;
  const avContract =
    audioPayload?.av_contract &&
    typeof audioPayload.av_contract === 'object' &&
    !Array.isArray(audioPayload.av_contract)
      ? (audioPayload.av_contract as Record<string, unknown>)
      : undefined;
  const subtitleCues = normalizeAudioSubtitleCues(audioPayload?.subtitle_cues);

  return {
    audio_url: audioUrl,
    ...(audioBid ? { audio_bid: audioBid } : {}),
    ...(durationMs === undefined ? {} : { duration_ms: durationMs }),
    ...(position === undefined ? {} : { position }),
    ...(slideId ? { slide_id: slideId } : {}),
    ...(avContract ? { av_contract: avContract } : {}),
    ...(subtitleCues ? { subtitle_cues: subtitleCues } : {}),
  };
};

const hydrateAudioTracksWithCompleteUrl = (
  tracks: AudioTrack[] = [],
  audioComplete?: Partial<AudioCompleteData> | null,
): AudioTrack[] => {
  if (!audioComplete?.audio_url) {
    return tracks;
  }

  const position =
    normalizeOptionalNumber(audioComplete.position) ??
    DEFAULT_LISTEN_AUDIO_POSITION;
  const targetIndex = tracks.findIndex(track => track.position === position);
  const targetTrack =
    targetIndex >= 0
      ? { ...tracks[targetIndex] }
      : {
          position,
          audioSegments: [],
          isAudioStreaming: false,
        };

  const nextTrack: AudioTrack = {
    ...targetTrack,
    audioUrl: audioComplete.audio_url,
    durationMs: audioComplete.duration_ms ?? targetTrack.durationMs,
    isAudioStreaming: false,
    slideId: audioComplete.slide_id ?? targetTrack.slideId,
    avContract: audioComplete.av_contract ?? targetTrack.avContract,
    subtitleCues: audioComplete.subtitle_cues ?? targetTrack.subtitleCues,
  };
  const nextTracks =
    targetIndex >= 0
      ? tracks.map((track, index) =>
          index === targetIndex ? nextTrack : track,
        )
      : [...tracks, nextTrack];

  return sortAudioTracksByPosition(nextTracks);
};

const normalizeCanonicalChatContentItem = (
  item: ChatContentItem,
): ChatContentItem => {
  const nextContent =
    typeof item.content === 'string'
      ? (stripCustomButtonAfterContent(item.content) ?? '')
      : item.content;
  const nextAskList = Array.isArray(item.ask_list)
    ? item.ask_list.map(normalizeCanonicalChatContentItem)
    : item.ask_list;
  const hasContentChanged = nextContent !== item.content;
  const hasAskListChanged = nextAskList !== item.ask_list;

  if (!hasContentChanged && !hasAskListChanged) {
    return item;
  }

  return {
    ...item,
    ...(hasContentChanged ? { content: nextContent } : {}),
    ...(hasAskListChanged ? { ask_list: nextAskList } : {}),
  };
};

const normalizeCanonicalChatContentList = (
  items: ChatContentItem[],
): ChatContentItem[] =>
  normalizeLegacyBlockCompatList(items).map(normalizeCanonicalChatContentItem);

const resolvePayloadVisualContent = (
  payload?: StudyRecordItem['payload'] | null,
) => {
  const previousVisuals = payload?.previous_visuals;
  if (!Array.isArray(previousVisuals)) {
    return '';
  }

  return previousVisuals
    .map(item => {
      if (!item || typeof item !== 'object') {
        return '';
      }
      const content = (item as { content?: unknown }).content;
      return typeof content === 'string' ? content.trim() : '';
    })
    .filter(Boolean)
    .join('\n\n');
};

const resolveRenderableRecordContent = (record: StudyRecordItem) => {
  const content = record.content ?? '';
  if (content.trim()) {
    return content;
  }
  return resolvePayloadVisualContent(record.payload) || content;
};

export interface UseChatSessionParams {
  shifuBid: string;
  outlineBid: string;
  lessonId: string;
  chapterId?: string;
  previewMode?: boolean;
  isListenMode?: boolean;
  listenRequestEnabled?: boolean;
  shouldPromptLessonFeedback?: boolean;
  trackEvent: (name: string, payload?: Record<string, any>) => void;
  trackTrailProgress: (courseId: string, elementBid: string) => void;
  lessonUpdate?: (params: Record<string, any>) => void;
  chapterUpdate?: (params: Record<string, any>) => void;
  updateSelectedLesson: (lessonId: string, forceExpand?: boolean) => void;
  getNextLessonId: (lessonId?: string | null) => string | null;
  scrollToLesson: (lessonId: string) => void;
  // scrollToBottom: (behavior?: ScrollBehavior) => void;
  showOutputInProgressToast: () => void;
  onPayModalOpen: () => void;
  chatBoxBottomRef: React.RefObject<HTMLDivElement | null>;
  onGoChapter: (lessonId: string) => void;
}

export interface UseChatSessionResult {
  items: ChatContentItem[];
  isLoading: boolean;
  isOutputInProgress: boolean;
  currentStreamingElementBid: string;
  currentTypewriterElementBid: string;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onRefresh: (elementBid: string) => void;
  toggleAskExpanded: (parentElementBid: string) => void;
  syncAskListByParentElement: (
    parentElementBid: string,
    askList: ChatContentItem[],
    options?: {
      expand?: boolean;
    },
  ) => void;
  requestAudioForBlock: (
    elementBid: string,
    options?: RequestAudioForBlockOptions,
  ) => Promise<AudioCompleteData | null>;
  reGenerateConfirm: {
    open: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  };
  lessonFeedbackPopup: {
    open: boolean;
    elementBid: string;
    defaultScoreText: string;
    defaultCommentText: string;
    readonly: boolean;
    onClose: () => void;
    onSubmit: (score: number, comment: string) => void;
  };
}

/**
 * useChatLogicHook orchestrates the streaming chat lifecycle for lesson content.
 */
function useChatLogicHook({
  shifuBid,
  onGoChapter,
  outlineBid,
  lessonId,
  chapterId,
  previewMode,
  isListenMode = false,
  listenRequestEnabled = false,
  shouldPromptLessonFeedback = true,
  trackEvent,
  chatBoxBottomRef,
  trackTrailProgress,
  lessonUpdate,
  chapterUpdate,
  updateSelectedLesson,
  getNextLessonId,
  scrollToLesson,
  // scrollToBottom,
  showOutputInProgressToast,
  onPayModalOpen,
}: UseChatSessionParams): UseChatSessionResult {
  const { t, i18n, ready } = useTranslation();
  const { mobileStyle } = useContext(AppContext);
  const isListenModeLatest = useLatest(isListenMode);

  const { updateUserInfo } = useUserStore(
    useShallow(state => ({
      updateUserInfo: state.updateUserInfo,
    })),
  );
  const isStreamingRef = useRef(false);
  const [isOutputInProgress, setIsOutputInProgress] = useState(false);
  const { updateResetedChapterId, updateResetedLessonId, resetedLessonId } =
    useCourseStore(
      useShallow(state => ({
        resetedLessonId: state.resetedLessonId,
        updateResetedChapterId: state.updateResetedChapterId,
        updateResetedLessonId: state.updateResetedLessonId,
      })),
    );

  const effectivePreviewMode = previewMode ?? false;
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
  const updateLessonRunPendingSlides = useLessonRunContentStore(
    state => state.updatePendingSlides,
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
  // const [lastInteractionBlock, setLastInteractionBlock] =
  //   useState<ChatContentItem | null>(null);
  const [loadedChapterId, setLoadedChapterId] = useState('');

  const contentListRef = useRef<ChatContentItem[]>([]);
  const currentContentRef = useRef<string>('');
  const currentBlockIdRef = useRef<string | null>(null);
  const runRef = useRef<((params: SSEParams) => void) | null>(null);
  const sseRef = useRef<any>(null);
  const sseRunSerialRef = useRef(0);
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

  const allowTtsStreaming = !effectivePreviewMode;

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

  const matchItemBid = useCallback((item: ChatContentItem, bid: string) => {
    if (!bid) {
      return false;
    }

    return item.element_bid === bid;
  }, []);

  const resolveAudioBlockTarget = useCallback((bid: string) => {
    const item = contentListRef.current.find(
      contentItem =>
        contentItem.element_bid === bid ||
        contentItem.generated_block_bid === bid,
    );

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

  const isLessonFeedbackContent = useCallback((content?: string | null) => {
    return Boolean(content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER));
  }, []);

  const createLikeStatusItem = useCallback(
    (
      parentElementBid: string,
      likeStatus: LikeStatus = LIKE_STATUS.NONE,
    ): ChatContentItem => ({
      parent_element_bid: parentElementBid,
      element_bid: '',
      content: '',
      like_status: likeStatus,
      type: ChatContentItemType.LIKE_STATUS,
    }),
    [],
  );

  const shouldAttachLikeStatusByElement = useCallback(
    ({
      elementBid,
      elementType,
      content,
    }: {
      elementBid?: string | null;
      elementType?: ElementType | null;
      content?: string | null;
    }) => {
      if (!elementBid) {
        return false;
      }

      if (!elementType) {
        return false;
      }

      return !isLessonFeedbackContent(content);
    },
    [isLessonFeedbackContent],
  );

  const upsertLikeStatusByParent = useCallback(
    (
      items: ChatContentItem[],
      params: {
        parentElementBid: string;
        likeStatus?: LikeStatus | null;
        insertAfterElementBid?: string;
      },
    ) => {
      const { parentElementBid, insertAfterElementBid } = params;
      if (!parentElementBid) {
        return items;
      }

      const resolvedLikeStatus = params.likeStatus ?? LIKE_STATUS.NONE;
      const hitIndex = items.findIndex(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS &&
          item.parent_element_bid === parentElementBid,
      );

      if (hitIndex >= 0) {
        if (items[hitIndex].like_status === resolvedLikeStatus) {
          return items;
        }
        const nextItems = [...items];
        nextItems[hitIndex] = {
          ...nextItems[hitIndex],
          like_status: resolvedLikeStatus,
        };
        return nextItems;
      }

      const nextItems = [...items];
      const anchorElementBid = insertAfterElementBid || parentElementBid;
      const anchorIndex = nextItems.findIndex(
        item => item.element_bid === anchorElementBid,
      );
      const nextLikeStatusItem = createLikeStatusItem(
        parentElementBid,
        resolvedLikeStatus,
      );

      if (anchorIndex >= 0) {
        nextItems.splice(anchorIndex + 1, 0, nextLikeStatusItem);
        return nextItems;
      }

      nextItems.push(nextLikeStatusItem);
      return nextItems;
    },
    [createLikeStatusItem],
  );

  const removeLikeStatusByParent = useCallback(
    (items: ChatContentItem[], parentElementBid: string) => {
      if (!parentElementBid) {
        return items;
      }

      const hitIndex = items.findIndex(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS &&
          item.parent_element_bid === parentElementBid,
      );

      if (hitIndex < 0) {
        return items;
      }

      const nextItems = [...items];
      nextItems.splice(hitIndex, 1);
      return nextItems;
    },
    [],
  );

  const finalizeLikeStatusByParent = useCallback(
    (items: ChatContentItem[], parentElementBid: string) => {
      if (!parentElementBid) {
        return items;
      }

      const targetItem = items.find(
        item => item.element_bid === parentElementBid,
      );
      if (!targetItem) {
        return items;
      }

      const elementType =
        typeof targetItem.element_type === 'string'
          ? targetItem.element_type
          : undefined;
      const shouldAttachLikeStatus = shouldAttachLikeStatusByElement({
        elementBid: parentElementBid,
        elementType,
        content: targetItem.content,
      });

      if (!shouldAttachLikeStatus) {
        return removeLikeStatusByParent(items, parentElementBid);
      }

      return upsertLikeStatusByParent(items, {
        parentElementBid,
        likeStatus: targetItem.like_status,
        insertAfterElementBid: parentElementBid,
      });
    },
    [
      removeLikeStatusByParent,
      shouldAttachLikeStatusByElement,
      upsertLikeStatusByParent,
    ],
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
    [finalizeLikeStatusByParent, isListenModeLatest],
  );

  const resolveRecordUserInput = useCallback(
    (record?: Pick<StudyRecordItem, 'user_input' | 'payload'> | null) => {
      if (!record) {
        return undefined;
      }

      const payloadUserInput =
        typeof record.payload?.user_input === 'string'
          ? record.payload.user_input
          : undefined;

      return record.user_input ?? payloadUserInput;
    },
    [],
  );

  const resolveRecordElementType = useCallback(
    (record?: Pick<StudyRecordItem, 'element_type'> | null) => {
      const rawElementType = (record as { element_type?: unknown } | null)
        ?.element_type;
      return typeof rawElementType === 'string' ? rawElementType : '';
    },
    [],
  );

  const isAskOrAnswerElementType = useCallback(
    (elementType?: string | null) => {
      return (
        elementType === BLOCK_TYPE.ASK || elementType === BLOCK_TYPE.ANSWER
      );
    },
    [],
  );

  const resolveAskAnchorElementBid = useCallback(
    (record: StudyRecordItem, items: ChatContentItem[] = []) => {
      const payload = (record.payload ?? {}) as Record<string, unknown>;
      const payloadAnchorElementBid =
        typeof payload.anchor_element_bid === 'string'
          ? payload.anchor_element_bid
          : '';
      if (payloadAnchorElementBid) {
        return payloadAnchorElementBid;
      }

      const payloadAskElementBid =
        typeof payload.ask_element_bid === 'string'
          ? payload.ask_element_bid
          : '';
      if (!payloadAskElementBid) {
        return '';
      }

      const matchedAskBlock = items.find(
        item =>
          item.type === ChatContentItemType.ASK &&
          Array.isArray(item.ask_list) &&
          item.ask_list.some(
            askMessage => askMessage.element_bid === payloadAskElementBid,
          ),
      );
      return matchedAskBlock?.parent_element_bid || '';
    },
    [],
  );

  const upsertAskMessageByParent = useCallback(
    (
      items: ChatContentItem[],
      params: {
        parentElementBid: string;
        messageType: typeof BLOCK_TYPE.ASK | typeof BLOCK_TYPE.ANSWER;
        messageElementBid?: string;
        messageGeneratedBlockBid?: string;
        messageContent: string;
        isHistory?: boolean;
        insertionMode?: 'anchor' | 'sequence';
      },
    ) => {
      const { parentElementBid, messageType, messageContent } = params;
      if (!parentElementBid) {
        return items;
      }
      const shouldAutoExpandAskBlock = !mobileStyle;

      const resolvedMessageElementBid =
        params.messageElementBid ||
        params.messageGeneratedBlockBid ||
        `${messageType}-${parentElementBid}`;
      const nextMessage: ChatContentItem = {
        element_bid: resolvedMessageElementBid,
        generated_block_bid:
          params.messageGeneratedBlockBid || resolvedMessageElementBid,
        parent_element_bid: parentElementBid,
        type: messageType,
        content: messageContent,
        readonly: true,
        customRenderBar: () => null,
        user_input: '',
        isHistory: params.isHistory,
      };

      const nextItems = [...items];
      const askBlockIndex = nextItems.findIndex(
        item =>
          item.type === ChatContentItemType.ASK &&
          item.parent_element_bid === parentElementBid,
      );

      if (askBlockIndex >= 0) {
        const existingAskBlock = nextItems[askBlockIndex];
        const existingAskList = Array.isArray(existingAskBlock.ask_list)
          ? [...existingAskBlock.ask_list]
          : [];
        const existingMessageIndex = existingAskList.findIndex(
          message => message.element_bid === resolvedMessageElementBid,
        );
        if (existingMessageIndex >= 0) {
          existingAskList[existingMessageIndex] = {
            ...existingAskList[existingMessageIndex],
            ...nextMessage,
          };
        } else {
          existingAskList.push(nextMessage);
        }
        nextItems[askBlockIndex] = {
          ...existingAskBlock,
          ask_list: existingAskList,
          isAskExpanded:
            existingAskBlock.isAskExpanded ?? shouldAutoExpandAskBlock,
        };
        return nextItems;
      }

      const nextAskBlock: ChatContentItem = {
        element_bid: '',
        parent_element_bid: parentElementBid,
        type: ChatContentItemType.ASK,
        content: '',
        isAskExpanded: shouldAutoExpandAskBlock,
        ask_list: [nextMessage],
        readonly: false,
        customRenderBar: () => null,
        user_input: '',
      };
      if (params.insertionMode === 'sequence') {
        nextItems.push(nextAskBlock);
        return nextItems;
      }
      const likeStatusIndex = nextItems.findIndex(
        item =>
          item.parent_element_bid === parentElementBid &&
          item.type === ChatContentItemType.LIKE_STATUS,
      );
      const parentContentIndex =
        likeStatusIndex >= 0
          ? likeStatusIndex
          : nextItems.findIndex(item => item.element_bid === parentElementBid);

      if (parentContentIndex < 0) {
        nextItems.push(nextAskBlock);
        return nextItems;
      }

      nextItems.splice(parentContentIndex + 1, 0, nextAskBlock);
      return nextItems;
    },
    [mobileStyle],
  );

  const normalizeHistoryAudioTracks = useCallback(
    (
      audios: AudioSegmentData[] = [],
      audioComplete?: Partial<AudioCompleteData> | null,
    ): AudioTrack[] => {
      if (!audios.length) {
        return hydrateAudioTracksWithCompleteUrl([], audioComplete);
      }

      const trackByPosition = new Map<number, AudioTrack>();

      [...audios]
        .sort(
          (a, b) =>
            Number(a.position ?? 0) - Number(b.position ?? 0) ||
            Number(a.segment_index ?? 0) - Number(b.segment_index ?? 0),
        )
        .forEach(audio => {
          const position = Number(audio.position ?? 0);
          const track = trackByPosition.get(position) ?? {
            position,
            audioSegments: [],
            isAudioStreaming: false,
          };

          track.audioSegments = [
            ...(track.audioSegments ?? []),
            {
              segmentIndex: Number(audio.segment_index ?? 0),
              audioData: audio.audio_data,
              durationMs: Number(audio.duration_ms ?? 0),
              isFinal: Boolean(audio.is_final),
              position,
              elementId: audio.element_id,
              slideId: audio.slide_id,
              avContract: audio.av_contract ?? null,
              subtitleCues: audio.subtitle_cues,
            },
          ];
          track.isAudioStreaming = Boolean(
            track.audioSegments?.some(segment => !segment.isFinal),
          );

          trackByPosition.set(position, track);
        });

      return hydrateAudioTracksWithCompleteUrl(
        [...trackByPosition.values()],
        audioComplete,
      );
    },
    [],
  );

  const sortSlidesByTimeline = useCallback((slides: ListenSlideData[] = []) => {
    return [...slides].sort(
      (a, b) =>
        Number(a.slide_index ?? 0) - Number(b.slide_index ?? 0) ||
        Number(a.audio_position ?? 0) - Number(b.audio_position ?? 0),
    );
  }, []);

  const mergeListenSlides = useCallback(
    (...slideLists: Array<ListenSlideData[] | undefined>) => {
      const slideById = new Map<string, ListenSlideData>();
      slideLists.flat().forEach(slide => {
        if (!slide?.slide_id) {
          return;
        }
        slideById.set(slide.slide_id, {
          ...(slideById.get(slide.slide_id) ?? {}),
          ...slide,
        });
      });
      return sortSlidesByTimeline([...slideById.values()]);
    },
    [sortSlidesByTimeline],
  );

  const upsertListenSlide = useCallback(
    (slides: ListenSlideData[] = [], incoming: ListenSlideData) =>
      mergeListenSlides(slides, [incoming]),
    [mergeListenSlides],
  );

  const resolveListenSlideIdentityBids = useCallback(
    (
      ...sources: Array<
        Partial<StudyRecordItem & ListenSlideData> | string | null | undefined
      >
    ) => {
      const bids = new Set<string>();
      sources.forEach(source => {
        if (!source) {
          return;
        }
        if (typeof source === 'string') {
          if (source.trim()) {
            bids.add(source.trim());
          }
          return;
        }
        [
          source.target_element_bid,
          source.element_bid,
          source.generated_block_bid,
        ].forEach(bid => {
          if (typeof bid === 'string' && bid.trim()) {
            bids.add(bid.trim());
          }
        });
      });
      return Array.from(bids);
    },
    [],
  );

  const getPendingListenSlides = useCallback(
    (identityBids: string[]) => {
      const pendingSlidesByBid =
        getLessonRunContentCacheEntry().pendingSlidesByBid;
      const slideLists = identityBids
        .map(bid => pendingSlidesByBid[bid])
        .filter(Boolean);
      return mergeListenSlides(...slideLists);
    },
    [getLessonRunContentCacheEntry, mergeListenSlides],
  );

  const resolveListenSlidePrimaryIdentityBids = useCallback(
    (slide: Partial<ListenSlideData>) => {
      const generatedBlockBid = slide.generated_block_bid?.trim() || '';
      const slideElementBid = slide.element_bid?.trim() || '';
      const explicitBids = [
        slide.target_element_bid,
        slideElementBid && slideElementBid !== generatedBlockBid
          ? slideElementBid
          : undefined,
      ].filter((bid): bid is string => Boolean(bid?.trim()));

      return explicitBids.length
        ? Array.from(new Set(explicitBids.map(bid => bid.trim())))
        : generatedBlockBid
          ? [generatedBlockBid]
          : [];
    },
    [],
  );

  const itemMatchesListenSlide = useCallback(
    (item: ChatContentItem, slide: Partial<ListenSlideData>) => {
      const generatedBlockBid = slide.generated_block_bid?.trim() || '';
      const slideElementBid = slide.element_bid?.trim() || '';
      const explicitBids = [
        slide.target_element_bid,
        slideElementBid && slideElementBid !== generatedBlockBid
          ? slideElementBid
          : undefined,
      ].filter((bid): bid is string => Boolean(bid?.trim()));

      if (explicitBids.length > 0) {
        return explicitBids.some(
          bid => item.element_bid === bid || item.target_element_bid === bid,
        );
      }

      return Boolean(
        generatedBlockBid && item.generated_block_bid === generatedBlockBid,
      );
    },
    [],
  );

  const clearPendingListenSlides = useCallback(
    (identityBids: string[]) => {
      if (!identityBids.length) {
        return;
      }
      updateLessonRunPendingSlides(lessonRunContentCacheKey, pendingSlides => {
        const nextPendingSlides = { ...pendingSlides };
        identityBids.forEach(bid => {
          delete nextPendingSlides[bid];
        });
        return nextPendingSlides;
      });
    },
    [lessonRunContentCacheKey, updateLessonRunPendingSlides],
  );

  const stashPendingListenSlide = useCallback(
    (identityBids: string[], slide: ListenSlideData) => {
      if (!identityBids.length) {
        return;
      }
      updateLessonRunPendingSlides(lessonRunContentCacheKey, pendingSlides => {
        const nextPendingSlides = { ...pendingSlides };
        identityBids.forEach(bid => {
          nextPendingSlides[bid] = upsertListenSlide(
            nextPendingSlides[bid] ?? [],
            slide,
          );
        });
        return nextPendingSlides;
      });
    },
    [lessonRunContentCacheKey, updateLessonRunPendingSlides, upsertListenSlide],
  );

  const itemMatchesListenSlideIdentity = useCallback(
    (item: ChatContentItem, identityBids: Set<string>) =>
      Boolean(
        identityBids.has(item.element_bid) ||
        (item.generated_block_bid &&
          identityBids.has(item.generated_block_bid)) ||
        (item.target_element_bid && identityBids.has(item.target_element_bid)),
      ),
    [],
  );

  const resolveElementCacheIdentityBids = useCallback(
    (record: StudyRecordItem, itemBid: string) => {
      const primaryBid =
        record.is_new === false && record.target_element_bid
          ? record.target_element_bid
          : itemBid;
      return primaryBid ? [primaryBid] : [];
    },
    [],
  );

  const itemMatchesElementCacheIdentity = useCallback(
    (item: ChatContentItem, identityBids: Set<string>) =>
      Boolean(
        identityBids.has(item.element_bid) ||
        (item.target_element_bid && identityBids.has(item.target_element_bid)),
      ),
    [],
  );

  const buildElementContentItem = useCallback(
    (
      record: StudyRecordItem,
      options?: {
        isHistory?: boolean;
        shouldRenderAsHistoryInReadMode?: boolean;
        shouldUseTypewriter?: boolean;
        listenSlides?: ListenSlideData[];
        previousItem?: ChatContentItem;
      },
    ): ChatContentItem => {
      const itemBid = resolveElementItemBid(record);
      const previousAudioSegments = Array.isArray(
        options?.previousItem?.audio_segments,
      )
        ? options?.previousItem?.audio_segments
        : [];
      const previousTrackAudioSegments = getAudioSegmentDataListFromTracks(
        options?.previousItem?.audioTracks ?? [],
      );
      const incomingAudioSegments = Array.isArray(record.audio_segments)
        ? record.audio_segments
        : [];
      const mergedAudioSegments = mergeAudioSegmentDataList(itemBid, [
        ...previousAudioSegments,
        ...previousTrackAudioSegments,
        ...incomingAudioSegments,
      ]);
      const historyTracks = normalizeHistoryAudioTracks(
        mergedAudioSegments,
        resolveStudyRecordAudioComplete(record),
      );
      const singleTrack = historyTracks.length === 1 ? historyTracks[0] : null;
      const isInteractionElement =
        record.element_type === ELEMENT_TYPE.INTERACTION;
      const generatedBlockBid = record.generated_block_bid || itemBid;
      const identityBids = resolveListenSlideIdentityBids(
        record,
        itemBid,
        generatedBlockBid,
      );
      const pendingListenSlides = getPendingListenSlides(identityBids);
      const content = resolveRenderableRecordContent(record);

      return {
        ...options?.previousItem,
        ...record,
        element_bid: itemBid,
        generated_block_bid: generatedBlockBid,
        content,
        customRenderBar: () => null,
        user_input:
          resolveRecordUserInput(record) ??
          options?.previousItem?.user_input ??
          '',
        readonly: options?.previousItem?.readonly ?? false,
        isHistory: options?.isHistory,
        shouldRenderAsHistoryInReadMode:
          options?.shouldRenderAsHistoryInReadMode ??
          (options?.previousItem?.isHistory
            ? false
            : (options?.previousItem?.shouldRenderAsHistoryInReadMode ??
              false)),
        is_final:
          options?.previousItem?.is_final === true
            ? true
            : Boolean(record.is_final),
        shouldUseTypewriter:
          options?.shouldUseTypewriter ??
          options?.previousItem?.shouldUseTypewriter ??
          false,
        isAudioBackfillReady:
          options?.isHistory ||
          options?.previousItem?.isHistory ||
          options?.previousItem?.isAudioBackfillReady ||
          isAudioBackfillReadyForBlock(generatedBlockBid, itemBid),
        type: isInteractionElement
          ? ChatContentItemType.INTERACTION
          : ChatContentItemType.CONTENT,
        audioUrl:
          singleTrack?.audioUrl ??
          record.audio_url ??
          options?.previousItem?.audioUrl,
        audioDurationMs:
          singleTrack?.durationMs ?? options?.previousItem?.audioDurationMs,
        audioTracks:
          historyTracks.length > 0
            ? historyTracks
            : options?.previousItem?.audioTracks,
        audio_segments:
          mergedAudioSegments.length > 0
            ? mergedAudioSegments
            : options?.previousItem?.audio_segments,
        listenSlides: mergeListenSlides(
          options?.previousItem?.listenSlides,
          options?.listenSlides,
          pendingListenSlides,
        ),
      };
    },
    [
      getPendingListenSlides,
      isAudioBackfillReadyForBlock,
      mergeListenSlides,
      normalizeHistoryAudioTracks,
      resolveElementItemBid,
      resolveListenSlideIdentityBids,
      resolveRecordUserInput,
    ],
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

  // Use react-use hooks for safer state management
  const isMounted = useMountedState();
  const chatBoxBottomRefLatest = useLatest(chatBoxBottomRef);

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
        const nextList = prevState.filter(
          item => item.element_bid !== 'loading',
        );
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
        const nextList = prevState.filter(
          item => item.element_bid !== 'loading',
        );
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

  const ensureContentItem = useCallback(
    (items: ChatContentItem[], blockId: string): ChatContentItem[] => {
      if (!blockId || blockId === 'loading') {
        return items;
      }
      const hit = items.some(item => matchItemBid(item, blockId));
      if (hit) {
        return items;
      }
      return items;
    },
    [matchItemBid],
  );

  /**
   * Applies stream-driven lesson status updates and triggers follow-up actions.
   */
  const lessonUpdateResp = useCallback(
    (response, isEnd: boolean) => {
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
        runRef.current?.({
          input: '',
          input_type: SSE_INPUT_TYPE.NORMAL,
        });
      }

      if (status === LESSON_STATUS_VALUE.LEARNING && !isEnd) {
        updateSelectedLesson(currentOutlineBid);
      }
    },
    [lessonUpdate, updateSelectedLesson],
  );

  const stopActiveRunStream = useCallback(() => {
    clearRunStreamTimeout();
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
      let nextList = prevState.filter(item => item.element_bid !== 'loading');
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
    (sseParams: SSEParams) => {
      const runSerial = sseRunSerialRef.current + 1;
      sseRunSerialRef.current = runSerial;
      clearRunStreamTimeout();
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
      // setIsTypeFinished(false);
      isTypeFinishedRef.current = false;
      isStreamingRef.current = true;
      setIsOutputInProgress(true);
      isInitHistoryRef.current = false;
      currentBlockIdRef.current = null;
      setCurrentStreamingElementBid('');
      setCurrentTypewriterElementBid('');
      currentContentRef.current = '';
      // setLastInteractionBlock(null);
      lastInteractionBlockRef.current = null;
      if (!isListenMode) {
        setTrackedContentList(prev => {
          const hasLoading = prev.some(item => item.element_bid === 'loading');
          if (hasLoading) {
            return prev;
          }
          const placeholderItem: ChatContentItem = {
            element_bid: 'loading',
            content: '',
            customRenderBar: () => <LoadingBar />,
            type: ChatContentItemType.CONTENT,
          };
          return [...prev, placeholderItem];
        });
      }

      let isEnd = false;
      const clearLoadingPlaceholder = () => {
        setTrackedContentList(prev =>
          prev.filter(item => item.element_bid !== 'loading'),
        );
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

        cleanupRunStreamState();
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

      // Track run start event
      trackEvent('learner_run_start', {
        shifu_bid: shifuBid,
        outline_bid: outlineBid,
        learning_mode: isListenMode ? 'listen' : 'read',
      });
      source = getRunMessage(
        shifuBid,
        outlineBid,
        effectivePreviewMode,
        { ...sseParams, listen: listenRequestEnabled },
        async response => {
          if (
            sseRef.current !== source ||
            runSerial !== sseRunSerialRef.current
          ) {
            return;
          }
          armRunStreamTimeout();
          // if (response.type === SSE_OUTPUT_TYPE.HEARTBEAT) {
          //   if (!isEnd) {
          //     currentBlockIdRef.current = 'loading';
          //     setTrackedContentList(prev => {
          //       const hasLoading = prev.some(
          //         item => item.element_bid === 'loading',
          //       );
          //       if (hasLoading) {
          //         return prev;
          //       }
          //       const placeholderItem: ChatContentItem = {
          //         element_bid: 'loading',
          //         content: '',
          //         customRenderBar: () => <LoadingBar />,
          //         type: ChatContentItemType.CONTENT,
          //       };
          //       return [...prev, placeholderItem];
          //     });
          //   }
          //   return;
          // }
          try {
            if (response?.type === SSE_OUTPUT_TYPE.ERROR) {
              clearRunStreamTimeout();
              const rawContent = response?.content;
              const errorContent =
                typeof rawContent === 'string'
                  ? rawContent
                  : typeof rawContent?.content === 'string'
                    ? rawContent.content
                    : typeof rawContent?.message === 'string'
                      ? rawContent.message
                      : typeof response?.message === 'string'
                        ? response.message
                        : '';
              const businessCode =
                typeof response?.code === 'number'
                  ? response.code
                  : typeof rawContent?.code === 'number'
                    ? rawContent.code
                    : undefined;

              toast({
                title: errorContent || 'Request failed',
                variant: 'destructive',
              });
              if (
                effectivePreviewMode &&
                businessCode === CREDIT_INSUFFICIENT_ERROR_CODE &&
                errorContent
              ) {
                appendRunBusinessError(errorContent, businessCode);
              }
              return;
            }

            const nid =
              response?.content?.element_bid ||
              response?.element_bid ||
              response?.generated_block_bid ||
              '';
            if (
              response.type === SSE_OUTPUT_TYPE.ELEMENT ||
              response.type === SSE_OUTPUT_TYPE.INTERACTION ||
              response.type === SSE_OUTPUT_TYPE.CONTENT
            ) {
              if (
                contentListRef.current?.some(
                  item => item.element_bid === 'loading',
                )
              ) {
                // currentBlockIdRef.current = nid;
                // close loading
                setTrackedContentList(pre => {
                  const newList = pre.filter(
                    item => item.element_bid !== 'loading',
                  );
                  return newList;
                });
              }
            }
            const blockId = nid;
            // const blockId = currentBlockIdRef.current;

            if (blockId && [SSE_OUTPUT_TYPE.BREAK].includes(response.type)) {
              trackTrailProgress(shifuBid, blockId);
            }

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
                const parentElementBid = resolveAskAnchorElementBid(
                  elementRecord,
                  contentListRef.current,
                );
                if (!parentElementBid) {
                  return;
                }
                setTrackedContentList(prevState =>
                  upsertAskMessageByParent(prevState, {
                    parentElementBid,
                    messageType: elementType as
                      | typeof BLOCK_TYPE.ASK
                      | typeof BLOCK_TYPE.ANSWER,
                    messageElementBid: itemBid,
                    messageGeneratedBlockBid:
                      elementRecord.generated_block_bid || itemBid,
                    messageContent: elementRecord.content || '',
                    insertionMode: 'anchor',
                  }),
                );
                return;
              }

              const previousStreamingElementBid = currentBlockIdRef.current;
              if (
                previousStreamingElementBid &&
                previousStreamingElementBid !== itemBid
              ) {
                setTrackedContentList(prevState =>
                  finalizeElementOutputInList(
                    prevState,
                    previousStreamingElementBid,
                  ),
                );
              }

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
              const nextItem = buildElementContentItem(elementRecord, {
                previousItem,
                shouldUseTypewriter:
                  previousItem?.shouldUseTypewriter ?? elementType === 'text',
              });
              const isLessonFeedbackInteraction = isLessonFeedbackContent(
                nextItem.content,
              );

              setTrackedContentList(prevState => {
                const hitIndex = prevState.findIndex(item =>
                  itemMatchesElementCacheIdentity(
                    item,
                    elementCacheIdentitySet,
                  ),
                );
                let nextList = prevState;

                if (hitIndex >= 0) {
                  nextList = [...prevState];
                  nextList[hitIndex] = {
                    ...nextList[hitIndex],
                    ...nextItem,
                    listenSlides:
                      nextItem.listenSlides ?? nextList[hitIndex].listenSlides,
                  };
                } else {
                  nextList = [...prevState, nextItem];
                }

                return nextList;
              });
              clearPendingListenSlides(elementCacheIdentityBids);

              if (isLessonFeedbackInteraction && nextItem.element_bid) {
                openLessonFeedbackPopup({
                  elementBid: nextItem.element_bid,
                });
              }
            } else if (response.type === SSE_OUTPUT_TYPE.INTERACTION) {
              const isLessonFeedbackInteraction = isLessonFeedbackContent(
                response.content,
              );
              const interactionElementType =
                typeof response.content === 'object' && response.content
                  ? (response.content as { element_type?: ElementType })
                      .element_type
                  : undefined;
              const previousStreamingElementBid = currentBlockIdRef.current;
              if (
                previousStreamingElementBid &&
                previousStreamingElementBid !== nid
              ) {
                setTrackedContentList(prevState =>
                  finalizeElementOutputInList(
                    prevState,
                    previousStreamingElementBid,
                  ),
                );
              }
              if (nid) {
                currentBlockIdRef.current = nid;
                currentContentRef.current = '';
                setCurrentStreamingElementBid(nid);
              }
              setTrackedContentList((prev: ChatContentItem[]) => {
                // Use markdown-flow-ui default rendering for all interactions
                const interactionBlock: ChatContentItem = {
                  element_bid: nid,
                  content: response.content,
                  element_type:
                    interactionElementType || ELEMENT_TYPE.INTERACTION,
                  customRenderBar: () => null,
                  user_input: '',
                  readonly: false,
                  shouldRenderAsHistoryInReadMode: false,
                  type: ChatContentItemType.INTERACTION,
                };
                const hitIndex = prev.findIndex(
                  item => item.element_bid === nid,
                );
                const nextList =
                  hitIndex >= 0
                    ? prev.map((item, index) =>
                        index === hitIndex
                          ? { ...item, ...interactionBlock }
                          : item,
                      )
                    : [...prev, interactionBlock];

                if (isLessonFeedbackInteraction && nid) {
                  return removeLikeStatusByParent(nextList, nid);
                }

                return nextList;
              });
              if (isLessonFeedbackInteraction && nid) {
                openLessonFeedbackPopup({
                  elementBid: nid,
                });
              }
            } else if (response.type === SSE_OUTPUT_TYPE.CONTENT) {
              if (isEnd) {
                return;
              }

              const existingItem = blockId
                ? contentListRef.current.find(
                    item => item.element_bid === blockId,
                  )
                : undefined;
              const existingText =
                stripCustomButtonAfterContent(existingItem?.content) || '';
              const prevText = currentContentRef.current || existingText;
              const nextText = mergeStreamingMarkdownText(
                prevText,
                response.content || '',
              );

              if (blockId) {
                currentBlockIdRef.current = blockId;
                setCurrentStreamingElementBid(blockId);
                setCurrentTypewriterElementBid(blockId);
              }

              currentContentRef.current = nextText;
              const displayText = maskIncompleteMermaidBlock(nextText);
              if (blockId) {
                const generatedBlockBid =
                  response?.generated_block_bid || blockId;
                const contentIdentityBids = resolveListenSlideIdentityBids(
                  {
                    element_bid: blockId,
                    generated_block_bid: generatedBlockBid,
                  },
                  blockId,
                  generatedBlockBid,
                );
                const contentIdentitySet = new Set(contentIdentityBids);
                const pendingListenSlides =
                  getPendingListenSlides(contentIdentityBids);
                setTrackedContentList(prevState => {
                  let hasItem = false;
                  const updatedList = prevState.map(item => {
                    if (
                      itemMatchesListenSlideIdentity(item, contentIdentitySet)
                    ) {
                      hasItem = true;
                      return {
                        ...item,
                        generated_block_bid:
                          item.generated_block_bid || generatedBlockBid,
                        isAudioBackfillReady:
                          item.isAudioBackfillReady ||
                          isAudioBackfillReadyForBlock(
                            generatedBlockBid,
                            blockId,
                          ),
                        content: displayText,
                        is_final: false,
                        shouldRenderAsHistoryInReadMode: false,
                        customRenderBar: () => null,
                        listenSlides: mergeListenSlides(
                          item.listenSlides,
                          pendingListenSlides,
                        ),
                      };
                    }
                    return item;
                  });
                  if (!hasItem) {
                    updatedList.push({
                      element_bid: blockId,
                      content: displayText,
                      user_input: '',
                      readonly: false,
                      is_final: false,
                      shouldRenderAsHistoryInReadMode: false,
                      shouldUseTypewriter: true,
                      customRenderBar: () => null,
                      type: ChatContentItemType.CONTENT,
                      generated_block_bid: generatedBlockBid,
                      isAudioBackfillReady: isAudioBackfillReadyForBlock(
                        generatedBlockBid,
                        blockId,
                      ),
                      listenSlides: pendingListenSlides,
                    });
                  }
                  return updatedList;
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
                  }
                }
              } else {
                // only update current lesson
                if (outline_bid && outline_bid === lessonId) {
                  if (status === LESSON_STATUS_VALUE.COMPLETED) {
                    isEnd = true;
                  }
                  lessonUpdateResp(response, isEnd);
                }
              }
            } else if (
              // response.type === SSE_OUTPUT_TYPE.BREAK ||
              response.type === SSE_OUTPUT_TYPE.TEXT_END
            ) {
              if (response.is_terminal === true) {
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
                  item => item.element_bid !== 'loading',
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
                  lastRenderableItem &&
                  lastRenderableItem.type === ChatContentItemType.CONTENT
                ) {
                  runRef.current?.({
                    input: '',
                    input_type: SSE_INPUT_TYPE.NORMAL,
                  });
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
            } else if (response.type === SSE_OUTPUT_TYPE.NEW_SLIDE) {
              const incomingSlide = response.content as ListenSlideData;
              const slideGeneratedBlockBid =
                incomingSlide?.generated_block_bid ||
                response?.generated_block_bid ||
                blockId ||
                undefined;
              const nextSlide = {
                ...incomingSlide,
                element_bid:
                  incomingSlide.element_bid ||
                  incomingSlide.target_element_bid ||
                  slideGeneratedBlockBid,
                generated_block_bid: slideGeneratedBlockBid,
              };
              const slideIdentityBids =
                resolveListenSlidePrimaryIdentityBids(nextSlide);
              const currentStreamingBids = new Set(
                [currentBlockIdRef.current, blockId].filter(
                  (bid): bid is string => Boolean(bid),
                ),
              );
              if (!slideIdentityBids.length || !incomingSlide?.slide_id) {
                return;
              }

              stashPendingListenSlide(slideIdentityBids, nextSlide);

              setTrackedContentList(prevState => {
                const hasContentBlock = prevState.some(
                  item =>
                    itemMatchesListenSlide(item, nextSlide) ||
                    Boolean(
                      nextSlide.generated_block_bid &&
                      item.generated_block_bid ===
                        nextSlide.generated_block_bid &&
                      (currentStreamingBids.has(item.element_bid) ||
                        (item.type === ChatContentItemType.CONTENT &&
                          item.is_final !== true)),
                    ),
                );
                if (!hasContentBlock) {
                  return prevState;
                }

                return prevState.map(item => {
                  if (
                    !itemMatchesListenSlide(item, nextSlide) &&
                    !(
                      nextSlide.generated_block_bid &&
                      item.generated_block_bid ===
                        nextSlide.generated_block_bid &&
                      (currentStreamingBids.has(item.element_bid) ||
                        (item.type === ChatContentItemType.CONTENT &&
                          item.is_final !== true))
                    )
                  ) {
                    return item;
                  }
                  return {
                    ...item,
                    listenSlides: mergeListenSlides(item.listenSlides, [
                      nextSlide,
                    ]),
                  };
                });
              });
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
            } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
              if (!allowTtsStreaming) {
                return;
              }
              // Handle audio segment during TTS streaming
              const audioSegment = normalizeAudioSegmentPayload(
                response.content as Parameters<
                  typeof normalizeAudioSegmentPayload
                >[0],
              );
              if (!audioSegment) {
                return;
              }
              if (blockId) {
                setTrackedContentList(prevState =>
                  upsertAudioSegment(
                    prevState,
                    blockId,
                    toAudioSegmentData(audioSegment),
                    items => ensureContentItem(items, blockId),
                  ),
                );
              }
            } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
              if (!allowTtsStreaming) {
                return;
              }
              // Handle audio completion with OSS URL
              const audioComplete = normalizeAudioCompletePayload(
                response.content,
              );
              if (!audioComplete) {
                return;
              }
              if (blockId) {
                setTrackedContentList(prevState =>
                  upsertAudioComplete(
                    prevState,
                    blockId,
                    audioComplete,
                    items => ensureContentItem(items, blockId),
                  ),
                );
              }
            }
          } catch (error) {
            console.warn('SSE handling error:', error);
          }
        },
        error => {
          const isLatestRun = runSerial === sseRunSerialRef.current;
          const isCurrentSource =
            sseRef.current === source || sseRef.current === null;
          if (!isLatestRun || !isCurrentSource) {
            return;
          }
          const businessError = (
            error as { detail?: { code?: number; message?: string } }
          )?.detail;
          if (
            effectivePreviewMode &&
            businessError?.code === CREDIT_INSUFFICIENT_ERROR_CODE &&
            businessError?.message?.trim()
          ) {
            toast({
              title: businessError.message.trim(),
              variant: 'destructive',
            });
            cleanupRunStreamState();
            appendRunBusinessError(
              businessError.message.trim(),
              businessError.code,
            );
            return;
          }
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
            // Always clear the loading placeholder when the active stream closes.
            // Some interaction flows may only emit control events before closing,
            // which still leaves the placeholder visible without this cleanup.
            cleanupRunStreamState();
          }
        }
      });
    },
    [
      buildElementContentItem,
      chapterId,
      chapterUpdate,
      effectivePreviewMode,
      isListenMode,
      listenRequestEnabled,
      lessonUpdateResp,
      outlineBid,
      isTypeFinishedRef,
      setTrackedContentList,
      shifuBid,
      lessonId,
      mobileStyle,
      trackTrailProgress,
      allowTtsStreaming,
      appendRunBusinessError,
      appendRunTimeoutError,
      clearPendingListenSlides,
      clearRunStreamTimeout,
      ensureContentItem,
      finalizeElementOutputInList,
      getPendingListenSlides,
      isAskOrAnswerElementType,
      isAudioBackfillReadyForBlock,
      isLessonFeedbackContent,
      itemMatchesElementCacheIdentity,
      itemMatchesListenSlide,
      itemMatchesListenSlideIdentity,
      lessonRunContentCacheKey,
      markLessonRunAudioBackfillReady,
      matchItemBid,
      mergeListenSlides,
      openLessonFeedbackPopup,
      removeLikeStatusByParent,
      resolveAskAnchorElementBid,
      resolveElementItemBid,
      resolveElementCacheIdentityBids,
      resolveListenSlideIdentityBids,
      resolveListenSlidePrimaryIdentityBids,
      stashPendingListenSlide,
      upsertAskMessageByParent,
      updateUserInfo,
    ],
  );

  useEffect(() => {
    return () => {
      clearRunStreamTimeout();
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
          const parentElementBid = resolveAskAnchorElementBid(item, result);
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
            parentElementBid,
            messageType: elementType as
              | typeof BLOCK_TYPE.ASK
              | typeof BLOCK_TYPE.ANSWER,
            messageElementBid: itemBid,
            messageGeneratedBlockBid: item.generated_block_bid || itemBid,
            messageContent: item.content || '',
            isHistory: true,
            insertionMode: 'anchor',
          });
          result.splice(0, result.length, ...nextResult);
          return;
        }

        const nextItem = buildElementContentItem(item, {
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
    [
      buildElementContentItem,
      isAskOrAnswerElementType,
      removeLikeStatusByParent,
      resolveAskAnchorElementBid,
      resolveElementItemBid,
      resolveRecordElementType,
      shouldAttachLikeStatusByElement,
      upsertAskMessageByParent,
      upsertLikeStatusByParent,
    ],
  );

  /**
   * Loads the persisted lesson records and primes the chat stream.
   */
  const refreshData = useCallback(async () => {
    resetLessonRunContent(lessonRunContentCacheKey);
    setTrackedContentList(() => []);
    resetLessonFeedbackPopup();

    // setIsTypeFinished(true);
    isTypeFinishedRef.current = true;
    lastInteractionBlockRef.current = null;
    setIsLoading(true);
    hasScrolledToBottomRef.current = false;
    isInitHistoryRef.current = true;

    try {
      const recordResp = await getLessonStudyRecord({
        shifu_bid: shifuBid,
        outline_bid: outlineBid,
        preview_mode: effectivePreviewMode,
      });

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
        // setIsTypeFinished(true);
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
          runRef.current?.({
            input: '',
            input_type: SSE_INPUT_TYPE.NORMAL,
          });
        }
      } else {
        runRef.current?.({
          input: '',
          input_type: SSE_INPUT_TYPE.NORMAL,
        });
        if (!effectivePreviewMode) {
          trackEvent('learner_lesson_start', {
            shifu_bid: shifuBid,
            outline_bid: outlineBid,
          });
        }
      }
    } catch (error) {
      console.warn('refreshData error:', error);
    } finally {
      setIsLoading(false);
    }
  }, [
    chapterId,
    getLessonFeedbackDefaults,
    isLessonFeedbackContent,
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
          sseRef.current?.close();
          await refreshData();
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

  useEffect(() => {
    sseRef.current?.close();
    if (!lessonId || resetedLessonId === lessonId) {
      return;
    }
    refreshData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonId, resetedLessonId]);

  useEffect(() => {
    const onGoToNavigationNode = (
      event: CustomEvent<{ chapterId: string; lessonId: string }>,
    ) => {
      const { chapterId: targetChapterId, lessonId: targetLessonId } =
        event.detail;
      if (targetChapterId !== loadedChapterId) {
        return;
      }
      // setIsTypeFinished(true);
      isTypeFinishedRef.current = true;
      // setLastInteractionBlock(null);
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
    ): { newList: ChatContentItem[]; needChangeItemIndex: number } => {
      const newList = [...contentListRef.current];
      // first find the item with the same variable value
      let needChangeItemIndex = newList.findIndex(item =>
        item.content?.includes(params.variableName || ''),
      );
      // if has multiple items with the same variable value, we need to find the item with the same blockBid
      const sameVariableValueItems =
        newList.filter(item =>
          item.content?.includes(params.variableName || ''),
        ) || [];
      if (sameVariableValueItems.length > 1) {
        needChangeItemIndex = newList.findIndex(
          item => item.element_bid === blockBid,
        );
      }
      if (needChangeItemIndex !== -1) {
        newList[needChangeItemIndex] = {
          ...newList[needChangeItemIndex],
          readonly: false,
          user_input: resolveInteractionSubmission(params).userInput,
        };
        if (!isListenMode) {
          // Preserve follow-up helper rows for the current interaction item
          // so ask actions do not disappear when entering the thinking state.
          const trailingRows = newList.slice(needChangeItemIndex + 1);
          const preservedHelperRows = trailingRows.filter(
            item =>
              item.parent_element_bid === blockBid &&
              (item.type === ChatContentItemType.LIKE_STATUS ||
                item.type === ChatContentItemType.ASK),
          );
          newList.length = needChangeItemIndex + 1;
          if (preservedHelperRows.length > 0) {
            newList.push(...preservedHelperRows);
          }
        }
        setTrackedContentList(newList);
      }

      return { newList, needChangeItemIndex };
    },
    [isListenMode, setTrackedContentList],
  );

  /**
   * Resolves the last actionable element bid for regenerate checks.
   * Auxiliary rows (like-status / ask / loading placeholders) are ignored.
   */
  const resolveLastActionableElementBid = useCallback(
    (items: ChatContentItem[]) => {
      const lastActionableItem = [...items].reverse().find(item => {
        if (!item?.element_bid || item.element_bid === 'loading') {
          return false;
        }

        return (
          item.type !== ChatContentItemType.LIKE_STATUS &&
          item.type !== ChatContentItemType.ASK
        );
      });

      return lastActionableItem?.element_bid || '';
    },
    [],
  );

  /**
   * onRefresh replays a block from the server using the original inputs.
   */
  const onRefresh = useCallback(
    async (elementBid: string) => {
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return;
      }

      const runningRes = await checkIsRunning(shifuBid, outlineBid);
      if (runningRes.is_running) {
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

      newList.length = needChangeItemIndex;
      setTrackedContentList(newList);

      // setIsTypeFinished(false);
      isTypeFinishedRef.current = false;
      runRef.current?.({
        input: '',
        input_type: SSE_INPUT_TYPE.NORMAL,
        reload_generated_block_bid: sourceBlockBid,
        reload_element_bid: sourceBlockBid,
      });
    },
    [
      isTypeFinishedRef,
      outlineBid,
      resolveSourceGeneratedBlockBid,
      shifuBid,
      isStreamingRef,
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
      // Re-selecting an earlier interaction needs to bypass the streaming
      // guard and pop the regenerate-confirm dialog. Compute the flag
      // up front so the streaming / running-check branches below can
      // short-circuit only for non-regenerate submissions.
      let isReGenerate = false;
      const currentListSnapshot = contentListRef.current;
      if (currentListSnapshot.length > 0) {
        const lastActionableElementBid =
          resolveLastActionableElementBid(currentListSnapshot);
        isReGenerate =
          Boolean(lastActionableElementBid) &&
          blockBid !== lastActionableElementBid;
      }

      if (!isReGenerate && isStreamingRef.current) {
        showOutputInProgressToast();
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

      if (isReGenerate && !options?.skipConfirm) {
        setPendingRegenerate({ content, blockBid });
        setShowRegenerateConfirm(true);
        return;
      }

      const runningRes = await checkIsRunning(shifuBid, outlineBid).catch(
        () => {
          return null;
        },
      );
      if (!isReGenerate && runningRes?.is_running) {
        showOutputInProgressToast();
        return;
      }

      // Confirmed regenerate while a stream is still flowing: close the
      // current SSE locally before issuing the reload request so its late
      // chunks cannot bleed into the new run's list.
      if (isReGenerate && isStreamingRef.current) {
        stopActiveRunStream();
      }

      const { newList, needChangeItemIndex } = updateContentListWithUserOperate(
        content,
        blockBid,
      );

      if (needChangeItemIndex === -1) {
        setTrackedContentList(newList);
      }

      // setIsTypeFinished(false);
      isTypeFinishedRef.current = false;
      // scrollToBottom();

      const { values } = resolveInteractionSubmission(content);
      const reload_generated_block_bid =
        isReGenerate && needChangeItemIndex !== -1
          ? resolveSourceGeneratedBlockBid(
              newList[needChangeItemIndex].element_bid,
            )
          : undefined;
      runRef.current?.({
        input: {
          [variableName as string]: values,
        },
        input_type: SSE_INPUT_TYPE.NORMAL,
        reload_element_bid: reload_generated_block_bid,
        reload_generated_block_bid,
      });
    },
    [
      dismissLessonFeedbackPopup,
      getLessonFeedbackDefaults,
      getNextLessonId,
      isTypeFinishedRef,
      isLessonFeedbackContent,
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
      resolveLastActionableElementBid,
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
    ): Promise<AudioCompleteData | null> => {
      if (!elementBid) {
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
        return null;
      }

      if (!shouldApplyResult()) {
        notifyStreamSettled();
        return null;
      }

      const existingItem = contentListRef.current.find(
        item =>
          item.element_bid === targetElementBid ||
          item.generated_block_bid === sourceBlockBid,
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
        notifyStreamSettled();
        return null;
      }

      setTrackedContentList(prev =>
        prev.map(item => {
          if (!matchItemBid(item, targetElementBid)) {
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

        const resolveOnce = (value: AudioCompleteData | null) => {
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
            prev.map(item => {
              const isSourceBlockItem =
                Boolean(sourceBlockBid) &&
                item.type === ChatContentItemType.CONTENT &&
                item.generated_block_bid === sourceBlockBid;
              if (!matchItemBid(item, targetElementBid) && !isSourceBlockItem) {
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
          resolveOnce(null);
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
              setTrackedContentList(prevState =>
                upsertAudioSegment(
                  prevState,
                  audioTargetElementBid,
                  toAudioSegmentData(audioSegment),
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
                upsertAudioComplete(
                  prevState,
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
      effectivePreviewMode,
      listenRequestEnabled,
      matchItemBid,
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
  };
}

export default useChatLogicHook;

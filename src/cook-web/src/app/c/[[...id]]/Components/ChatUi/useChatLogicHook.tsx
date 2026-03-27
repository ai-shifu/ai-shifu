import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  useContext,
  useMemo,
} from 'react';
import React from 'react';
import { useLatest, useMountedState } from 'react-use';
import {
  fixMarkdownStream,
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
  BlockType,
  checkIsRunning,
  streamGeneratedBlockAudio,
  submitLessonFeedback,
  ELEMENT_TYPE,
} from '@/c-api/studyV2';
import {
  getAudioSegmentDataListFromTracks,
  getAudioTrackByPosition,
  mergeAudioSegmentDataList,
  upsertAudioComplete,
  upsertAudioSegment,
  type AudioTrack,
} from '@/c-utils/audio-utils';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from '@/app/c/[[...id]]/events';
import { EVENT_NAMES } from '@/c-common/hooks/useTracking';
import {
  buildLessonFeedbackUserInput,
  parseLessonFeedbackUserInput,
  resolveInteractionSubmission,
} from '@/c-utils/interaction-user-input';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import LoadingBar from './LoadingBar';
import type { PreviewVariablesMap } from '@/components/lesson-preview/variableStorage';
import { useTranslation } from 'react-i18next';
import { show as showToast, toast } from '@/hooks/useToast';
import AskIcon from '@/c-assets/newchat/light/icon_ask.svg';
import { AppContext } from '../AppContext';
import {
  appendCustomButtonAfterContent,
  normalizeLegacyBlockCompatList,
} from './chatUiUtils';

interface LessonFeedbackPopupState {
  open: boolean;
  elementBid: string;
  defaultScoreText: string;
  defaultCommentText: string;
  readonly: boolean;
}

const LESSON_FEEDBACK_DISMISS_CACHE_LIMIT = 200;

export enum ChatContentItemType {
  CONTENT = 'content',
  INTERACTION = 'interaction',
  ASK = 'ask',
  LIKE_STATUS = 'likeStatus',
}

export interface ChatContentItem {
  content?: string;
  customRenderBar?: (() => React.ReactNode | null) | ComponentType<any>;
  user_input?: string;
  readonly?: boolean;
  isHistory?: boolean;
  element_bid: string;
  generated_block_bid?: string; // legacy block-level compatibility field
  ask_element_bid?: string; // use for ask block, because an interaction block gid isn't ask gid
  parent_element_bid?: string; // when like_status is not none, the parent_element_bid is the element_bid of the interaction block
  parent_block_bid?: string; // legacy parent block compatibility field
  like_status?: LikeStatus;
  type: ChatContentItemType | BlockType | ElementType;
  ask_list?: ChatContentItem[]; // list of ask records for this content block
  isAskExpanded?: boolean; // whether the ask panel is expanded
  generateTime?: number;
  variables?: PreviewVariablesMap;
  // Audio properties for TTS
  audioUrl?: string;
  audioTracks?: AudioTrack[];
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
  listenSlides?: ListenSlideData[];
  // Preserve element-level fields from backend records for listen-mode rendering.
  element_type?: ElementType;
  sequence_number?: number;
  is_marker?: boolean;
  is_new?: boolean;
  is_renderable?: boolean;
  is_speakable?: boolean;
  audio_url?: string;
  audio_segments?: AudioSegmentData[];
}

interface SSEParams {
  input: string | Record<string, any>;
  input_type: SSE_INPUT_TYPE;
  reload_generated_block_bid?: string;
  reload_element_bid?: string;
}

export interface UseChatSessionParams {
  shifuBid: string;
  outlineBid: string;
  lessonId: string;
  chapterId?: string;
  previewMode?: boolean;
  isListenMode?: boolean;
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
  currentStreamingElementBid: string;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onRefresh: (elementBid: string) => void;
  toggleAskExpanded: (parentElementBid: string) => void;
  requestAudioForBlock: (
    elementBid: string,
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

  const { updateUserInfo } = useUserStore(
    useShallow(state => ({
      updateUserInfo: state.updateUserInfo,
    })),
  );
  const isStreamingRef = useRef(false);
  const { updateResetedChapterId, updateResetedLessonId, resetedLessonId } =
    useCourseStore(
      useShallow(state => ({
        resetedLessonId: state.resetedLessonId,
        updateResetedChapterId: state.updateResetedChapterId,
        updateResetedLessonId: state.updateResetedLessonId,
      })),
    );

  const [contentList, setContentList] = useState<ChatContentItem[]>([]);
  const [currentStreamingElementBid, setCurrentStreamingElementBid] =
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
  const ttsSseRef = useRef<Record<string, any>>({});
  const pendingSlidesRef = useRef<Record<string, ListenSlideData[]>>({});
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
      elementBid: '',
      defaultScoreText: '',
      defaultCommentText: '',
      readonly: false,
    });
  const dismissedLessonFeedbackOutlineBidsRef = useRef<Set<string>>(new Set());

  const effectivePreviewMode = previewMode ?? false;
  const allowTtsStreaming = !effectivePreviewMode;
  const getAskButtonMarkup = useCallback(
    () =>
      `<custom-button-after-content><img src="${AskIcon.src}" alt="ask" width="14" height="14" /><span>${t('module.chat.ask')}</span></custom-button-after-content>`,
    [t],
  );

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

  const resolveSourceGeneratedBlockBid = useCallback((bid: string) => bid, []);

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

  const normalizeHistoryAudioTracks = useCallback(
    (audios: AudioSegmentData[] = []): AudioTrack[] => {
      if (!audios.length) {
        return [];
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
            },
          ];
          track.isAudioStreaming = Boolean(
            track.audioSegments?.some(segment => !segment.isFinal),
          );

          trackByPosition.set(position, track);
        });

      return [...trackByPosition.values()];
    },
    [],
  );

  const buildElementContentItem = useCallback(
    (
      record: StudyRecordItem,
      options?: {
        appendAskButton?: boolean;
        isHistory?: boolean;
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
      const historyTracks = normalizeHistoryAudioTracks(mergedAudioSegments);
      const singleTrack = historyTracks.length === 1 ? historyTracks[0] : null;
      const isInteractionElement =
        record.element_type === ELEMENT_TYPE.INTERACTION;
      const rawContent = record.content ?? '';
      const content =
        options?.appendAskButton &&
        mobileStyle &&
        !isListenMode &&
        !isInteractionElement
          ? appendCustomButtonAfterContent(rawContent, getAskButtonMarkup())
          : rawContent;

      return {
        ...options?.previousItem,
        ...record,
        element_bid: itemBid,
        generated_block_bid: record.generated_block_bid || itemBid,
        content,
        customRenderBar: () => null,
        user_input:
          resolveRecordUserInput(record) ??
          options?.previousItem?.user_input ??
          '',
        readonly: options?.previousItem?.readonly ?? false,
        isHistory: options?.isHistory,
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
        listenSlides:
          options?.listenSlides ?? options?.previousItem?.listenSlides,
      };
    },
    [
      getAskButtonMarkup,
      isListenMode,
      mobileStyle,
      normalizeHistoryAudioTracks,
      resolveElementItemBid,
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
      elementBid: '',
      defaultScoreText: '',
      defaultCommentText: '',
      readonly: false,
    });
  }, []);

  const dismissLessonFeedbackPopup = useCallback(() => {
    markLessonFeedbackPopupDismissed(outlineBid);
    setLessonFeedbackPopupState({
      open: false,
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
        open: shouldPromptLessonFeedback,
        elementBid: interaction.elementBid,
        defaultScoreText: interaction.defaultScoreText || '',
        defaultCommentText: interaction.defaultCommentText || '',
        readonly: Boolean(interaction.readonly),
      });
    },
    [outlineBid, parseLessonFeedbackScore, shouldPromptLessonFeedback],
  );

  useEffect(() => {
    if (!shouldPromptLessonFeedback) {
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
      };
    });
  }, [outlineBid, shouldPromptLessonFeedback]);

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
      setContentList(prev => {
        const next =
          typeof updater === 'function'
            ? (updater as (prev: ChatContentItem[]) => ChatContentItem[])(prev)
            : updater;
        const normalizedNext = normalizeLegacyBlockCompatList(next);
        contentListRef.current = normalizedNext;
        return normalizedNext;
      });
    },
    [],
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

  const sortSlidesByTimeline = useCallback((slides: ListenSlideData[] = []) => {
    return [...slides].sort(
      (a, b) =>
        Number(a.slide_index ?? 0) - Number(b.slide_index ?? 0) ||
        Number(a.audio_position ?? 0) - Number(b.audio_position ?? 0),
    );
  }, []);

  const upsertListenSlide = useCallback(
    (slides: ListenSlideData[] = [], incoming: ListenSlideData) => {
      const nextSlides = [...slides];
      const hitIndex = nextSlides.findIndex(
        slide => slide.slide_id === incoming.slide_id,
      );
      if (hitIndex >= 0) {
        nextSlides[hitIndex] = {
          ...nextSlides[hitIndex],
          ...incoming,
        };
      } else {
        nextSlides.push(incoming);
      }
      return sortSlidesByTimeline(nextSlides);
    },
    [sortSlidesByTimeline],
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

  /**
   * Starts the SSE request and streams content into the chat list.
   */
  const run = useCallback(
    (sseParams: SSEParams) => {
      const runSerial = sseRunSerialRef.current + 1;
      sseRunSerialRef.current = runSerial;
      if (sseRef.current) {
        try {
          sseRef.current?.close();
        } catch {
        } finally {
          sseRef.current = null;
        }
      }
      // setIsTypeFinished(false);
      isTypeFinishedRef.current = false;
      isInitHistoryRef.current = false;
      // currentBlockIdRef.current = 'loading';
      setCurrentStreamingElementBid('');
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

      const source = getRunMessage(
        shifuBid,
        outlineBid,
        effectivePreviewMode,
        { ...sseParams, listen: isListenMode },
        async response => {
          if (
            sseRef.current !== source ||
            runSerial !== sseRunSerialRef.current
          ) {
            return;
          }
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

              toast({
                title: errorContent || 'Request failed',
                variant: 'destructive',
              });
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
              if (isEnd) {
                return;
              }

              const elementRecord = response.content as StudyRecordItem;
              const itemBid = resolveElementItemBid(elementRecord);

              if (!itemBid) {
                return;
              }

              currentBlockIdRef.current = itemBid;
              setCurrentStreamingElementBid(itemBid);

              const nextItem = buildElementContentItem(elementRecord, {
                previousItem: contentListRef.current.find(
                  item => item.element_bid === itemBid,
                ),
                listenSlides: pendingSlidesRef.current[itemBid],
              });
              const isLessonFeedbackInteraction = isLessonFeedbackContent(
                nextItem.content,
              );

              setTrackedContentList(prevState => {
                const hitIndex = prevState.findIndex(
                  item => item.element_bid === itemBid,
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

                const shouldAttachLikeStatus = shouldAttachLikeStatusByElement({
                  elementBid: itemBid,
                  elementType: elementRecord.element_type,
                  content: nextItem.content,
                });

                if (shouldAttachLikeStatus) {
                  return upsertLikeStatusByParent(nextList, {
                    parentElementBid: itemBid,
                    likeStatus: nextItem.like_status,
                    insertAfterElementBid: itemBid,
                  });
                }

                return removeLikeStatusByParent(nextList, itemBid);
              });

              if (pendingSlidesRef.current[itemBid]) {
                delete pendingSlidesRef.current[itemBid];
              }

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
              setTrackedContentList((prev: ChatContentItem[]) => {
                // Use markdown-flow-ui default rendering for all interactions
                const interactionBlock: ChatContentItem = {
                  element_bid: nid,
                  content: response.content,
                  customRenderBar: () => null,
                  user_input: '',
                  readonly: false,
                  type: ChatContentItemType.INTERACTION,
                };
                const hitIndex = prev.findIndex(
                  item => item.element_bid === nid,
                );
                let nextList =
                  hitIndex >= 0
                    ? prev.map((item, index) =>
                        index === hitIndex
                          ? { ...item, ...interactionBlock }
                          : item,
                      )
                    : [...prev, interactionBlock];

                const shouldAttachLikeStatus = shouldAttachLikeStatusByElement({
                  elementBid: nid,
                  elementType: interactionElementType,
                  content: interactionBlock.content,
                });

                if (
                  !shouldAttachLikeStatus ||
                  isLessonFeedbackInteraction ||
                  !nid
                ) {
                  return removeLikeStatusByParent(nextList, nid);
                }

                nextList = upsertLikeStatusByParent(nextList, {
                  parentElementBid: nid,
                  insertAfterElementBid: nid,
                });
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

              const prevText = currentContentRef.current || '';
              const delta = fixMarkdownStream(prevText, response.content || '');
              const nextText = prevText + delta;
              currentContentRef.current = nextText;
              const displayText = maskIncompleteMermaidBlock(nextText);
              if (blockId) {
                setTrackedContentList(prevState => {
                  let hasItem = false;
                  const updatedList = prevState.map(item => {
                    if (item.element_bid === blockId) {
                      hasItem = true;
                      return {
                        ...item,
                        content: displayText,
                        customRenderBar: () => null,
                        listenSlides:
                          item.listenSlides ??
                          pendingSlidesRef.current[blockId] ??
                          item.listenSlides,
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
                      customRenderBar: () => null,
                      type: ChatContentItemType.CONTENT,
                      listenSlides: pendingSlidesRef.current[blockId],
                    });
                  }
                  return updatedList;
                });
                if (pendingSlidesRef.current[blockId]) {
                  delete pendingSlidesRef.current[blockId];
                }
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
                  lessonUpdateResp(response, isEnd);
                }
              }
            } else if (
              // response.type === SSE_OUTPUT_TYPE.BREAK ||
              response.type === SSE_OUTPUT_TYPE.TEXT_END
            ) {
              setCurrentStreamingElementBid('');
              setTrackedContentList((prev: ChatContentItem[]) => {
                const updatedList = [...prev].filter(
                  item => item.element_bid !== 'loading',
                );
                // Find the last CONTENT type item and append AskButton to its content
                // Set isHistory=true to prevent triggering typewriter effect for AskButton
                if (mobileStyle && !isListenMode) {
                  for (let i = updatedList.length - 1; i >= 0; i--) {
                    if (
                      updatedList[i].type === ChatContentItemType.CONTENT &&
                      !updatedList[i].content?.includes(
                        `<custom-button-after-content>`,
                      )
                    ) {
                      updatedList[i] = {
                        ...updatedList[i],
                        content: appendCustomButtonAfterContent(
                          updatedList[i].content,
                          getAskButtonMarkup(),
                        ),
                        isHistory: true, // Prevent AskButton from triggering typewriter
                      };
                      break;
                    }
                  }
                }

                const lastRenderableItem = [...updatedList]
                  .reverse()
                  .find(item => item.type !== ChatContentItemType.LIKE_STATUS);
                if (
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
            } else if (response.type === SSE_OUTPUT_TYPE.VARIABLE_UPDATE) {
              if (response.content.variable_name === 'sys_user_nickname') {
                updateUserInfo({
                  name: response.content.variable_value,
                });
              }
            } else if (response.type === SSE_OUTPUT_TYPE.NEW_SLIDE) {
              const incomingSlide = response.content as ListenSlideData;
              const slideElementBid =
                incomingSlide?.element_bid ||
                incomingSlide?.target_element_bid ||
                currentBlockIdRef.current ||
                blockId ||
                '';
              if (!slideElementBid || !incomingSlide?.slide_id) {
                return;
              }

              const nextSlide = {
                ...incomingSlide,
                element_bid: slideElementBid,
              };

              setTrackedContentList(prevState => {
                const hasContentBlock = prevState.some(item =>
                  matchItemBid(item, slideElementBid),
                );
                if (!hasContentBlock) {
                  const pending =
                    pendingSlidesRef.current[slideElementBid] ?? [];
                  pendingSlidesRef.current[slideElementBid] = upsertListenSlide(
                    pending,
                    nextSlide,
                  );
                  return prevState;
                }

                return prevState.map(item => {
                  if (!matchItemBid(item, slideElementBid)) {
                    return item;
                  }
                  return {
                    ...item,
                    listenSlides: upsertListenSlide(
                      item.listenSlides ?? [],
                      nextSlide,
                    ),
                  };
                });
              });
            } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
              if (!allowTtsStreaming) {
                return;
              }
              // Handle audio segment during TTS streaming
              const audioSegment = response.content as AudioSegmentData;
              if (blockId) {
                setTrackedContentList(prevState =>
                  upsertAudioSegment(prevState, blockId, audioSegment, items =>
                    ensureContentItem(items, blockId),
                  ),
                );
              }
            } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
              if (!allowTtsStreaming) {
                return;
              }
              // Handle audio completion with OSS URL
              const audioComplete = response.content as AudioCompleteData;
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
        () => {
          const isLatestRun = runSerial === sseRunSerialRef.current;
          const isCurrentSource =
            sseRef.current === source || sseRef.current === null;
          if (!isLatestRun || !isCurrentSource) {
            return;
          }
          clearLoadingPlaceholder();
          isStreamingRef.current = false;
          sseRef.current = null;
          setCurrentStreamingElementBid('');
        },
      );
      sseRef.current = source;
      source.addEventListener('readystatechange', () => {
        // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
        const isActiveSource =
          sseRef.current === source && runSerial === sseRunSerialRef.current;
        if (source.readyState === 1) {
          if (isActiveSource) {
            isStreamingRef.current = true;
          }
        }
        if (source.readyState === 2) {
          if (isActiveSource) {
            // Always clear the loading placeholder when the active stream closes.
            // Some interaction flows may only emit control events before closing,
            // which still leaves the placeholder visible without this cleanup.
            clearLoadingPlaceholder();
            isStreamingRef.current = false;
            sseRef.current = null;
            setCurrentStreamingElementBid('');
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
      lessonUpdateResp,
      outlineBid,
      isTypeFinishedRef,
      setTrackedContentList,
      shifuBid,
      lessonId,
      mobileStyle,
      trackTrailProgress,
      allowTtsStreaming,
      ensureContentItem,
      getAskButtonMarkup,
      isLessonFeedbackContent,
      matchItemBid,
      openLessonFeedbackPopup,
      removeLikeStatusByParent,
      resolveElementItemBid,
      shouldAttachLikeStatusByElement,
      upsertLikeStatusByParent,
      upsertListenSlide,
      updateUserInfo,
    ],
  );

  useEffect(() => {
    return () => {
      sseRef.current?.close();
    };
  }, []);

  useEffect(() => {
    runRef.current = run;
  }, [run]);

  /**
   * Transforms persisted study records into chat-friendly content items.
   */
  const mapRecordsToContent = useCallback(
    (records: StudyRecordItem[]) => {
      const result: ChatContentItem[] = [];

      records.forEach((item: StudyRecordItem) => {
        const itemBid = resolveElementItemBid(item);

        if (!itemBid) {
          return;
        }

        const nextItem = buildElementContentItem(item, {
          appendAskButton: true,
          isHistory: true,
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
      removeLikeStatusByParent,
      resolveElementItemBid,
      shouldAttachLikeStatusByElement,
      upsertLikeStatusByParent,
    ],
  );

  /**
   * Loads the persisted lesson records and primes the chat stream.
   */
  const refreshData = useCallback(async () => {
    setTrackedContentList(() => []);
    pendingSlidesRef.current = {};
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
      // console.log('listen-refresh-end', { lessonId, outlineBid });
    }
  }, [
    chapterId,
    getLessonFeedbackDefaults,
    isLessonFeedbackContent,
    mapRecordsToContent,
    openLessonFeedbackPopup,
    outlineBid,
    resetLessonFeedbackPopup,
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
          newList.length = needChangeItemIndex + 1;
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
      if (isStreamingRef.current) {
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

      const runningRes = await checkIsRunning(shifuBid, outlineBid).catch(
        () => {
          return null;
        },
      );
      if (runningRes?.is_running) {
        showOutputInProgressToast();
        return;
      }

      let isReGenerate = false;
      const currentList = contentListRef.current;
      if (currentList.length > 0) {
        const lastActionableElementBid =
          resolveLastActionableElementBid(currentList);
        isReGenerate =
          Boolean(lastActionableElementBid) &&
          blockBid !== lastActionableElementBid;
      }

      if (isReGenerate && !options?.skipConfirm) {
        setPendingRegenerate({ content, blockBid });
        setShowRegenerateConfirm(true);
        return;
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
      return;
    }
    source.close();
    delete ttsSseRef.current[blockId];
  }, []);

  const requestAudioForBlock = useCallback(
    async (elementBid: string): Promise<AudioCompleteData | null> => {
      if (!elementBid) {
        return null;
      }

      const sourceBlockBid = resolveSourceGeneratedBlockBid(elementBid);

      if (!allowTtsStreaming) {
        return null;
      }

      const existingItem = contentListRef.current.find(
        item => item.element_bid === elementBid,
      );
      const cachedTrack = getAudioTrackByPosition(
        existingItem?.audioTracks ?? [],
      );
      if (cachedTrack?.audioUrl && !cachedTrack.isAudioStreaming) {
        return {
          audio_url: cachedTrack.audioUrl,
          audio_bid: '',
          duration_ms: cachedTrack.durationMs ?? 0,
        };
      }

      if (ttsSseRef.current[sourceBlockBid]) {
        return null;
      }

      setTrackedContentList(prev =>
        prev.map(item => {
          if (!matchItemBid(item, sourceBlockBid)) {
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
        let latestComplete: AudioCompleteData | null = null;
        const source = streamGeneratedBlockAudio({
          shifu_bid: shifuBid,
          generated_block_bid: sourceBlockBid,
          preview_mode: effectivePreviewMode,
          listen: isListenMode,
          onMessage: response => {
            if (response?.type === SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
              const audioPayload = response.content ?? response.data;
              setTrackedContentList(prevState =>
                upsertAudioSegment(
                  prevState,
                  sourceBlockBid,
                  audioPayload as AudioSegmentData,
                ),
              );
              return;
            }

            if (response?.type === SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
              const audioPayload = response.content ?? response.data;
              const audioComplete = audioPayload as AudioCompleteData;
              latestComplete = audioComplete ?? latestComplete;
              setTrackedContentList(prevState =>
                upsertAudioComplete(prevState, sourceBlockBid, audioComplete),
              );
              if (finalizeTimer) {
                clearTimeout(finalizeTimer);
              }
              const delayMs = isListenMode ? 500 : 0;
              finalizeTimer = setTimeout(() => {
                closeTtsStream(sourceBlockBid);
                resolve(latestComplete ?? null);
              }, delayMs);
            }
          },
          onError: () => {
            if (finalizeTimer) {
              clearTimeout(finalizeTimer);
            }
            setTrackedContentList(prev =>
              prev.map(item => {
                if (!matchItemBid(item, sourceBlockBid)) {
                  return item;
                }
                return {
                  ...item,
                  isAudioStreaming: false,
                };
              }),
            );
            closeTtsStream(sourceBlockBid);
            reject(new Error('TTS stream failed'));
          },
        });

        ttsSseRef.current[sourceBlockBid] = source;
      });
    },
    [
      allowTtsStreaming,
      closeTtsStream,
      effectivePreviewMode,
      isListenMode,
      matchItemBid,
      resolveSourceGeneratedBlockBid,
      setTrackedContentList,
      shifuBid,
    ],
  );

  useEffect(() => {
    return () => {
      Object.values(ttsSseRef.current).forEach(source => {
        source?.close?.();
      });
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
    currentStreamingElementBid,
    onSend,
    onRefresh,
    toggleAskExpanded,
    requestAudioForBlock,
    reGenerateConfirm: {
      open: showRegenerateConfirm,
      onConfirm: handleConfirmRegenerate,
      onCancel: handleCancelRegenerate,
    },
    lessonFeedbackPopup: {
      open:
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

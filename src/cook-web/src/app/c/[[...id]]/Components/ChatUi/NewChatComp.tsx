import styles from './ChatComponents.module.scss';
import { ChevronsDown, X } from 'lucide-react';
import { createPortal } from 'react-dom';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import {
  useContext,
  useRef,
  memo,
  useCallback,
  useState,
  useEffect,
  useMemo,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { runWithConcurrency } from '@/lib/runWithConcurrency';
import { getDocumentFullscreenElement } from '@/c-utils/browserFullscreen';
import { AppContext } from '../AppContext';
import { useChatComponentsScroll } from './ChatComponents/useChatComponentsScroll';
import { useTracking } from '@/c-common/hooks/useTracking';
import { useEnvStore } from '@/c-store/envStore';
import { useUserStore } from '@/store';
import { useCourseStore } from '@/c-store/useCourseStore';
import { fail, toast } from '@/hooks/useToast';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import AskIcon from '@/c-assets/newchat/light/icon_ask.svg';
import { resolveWideLogoSource } from '@/c-components/logo/logoSource';
import InteractionBlock from './InteractionBlock';
import useChatLogicHook, { ChatContentItemType } from './useChatLogicHook';
import type { ChatContentItem } from './useChatLogicHook';
import AskBlock from './AskBlock';
import InteractionBlockM from './InteractionBlockM';
import ContentBlock from './ContentBlock';
import ListenModeSlideRenderer from './ListenModeSlideRenderer';
import LessonFeedbackInteraction from './LessonFeedbackInteraction';
import LoadingBar from './LoadingBar';
import StreamingLoadingDotsBar from './StreamingLoadingDotsBar';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import {
  getAudioTrackByPosition,
  hasAudioContentInTrack,
} from '@/c-utils/audio-utils';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { useSystemStore } from '@/c-store/useSystemStore';
import {
  buildAskListByAnchorElementBid,
  hasStreamingAskMessage,
} from './askState';
import { useAskStateStore } from './useAskStateStore';
import type { ListenMobileViewModeChangeHandler } from './listenModeTypes';
import { isListenModeActive as getIsListenModeActive } from '../learningModeOptions';
import {
  getMissingListenModeAudioBlockBids,
  hasPlayableListenAudioForItem,
  isListenModeAudioBackfillReady,
  isListenModeAudioBackfillCandidate,
} from './listenModeUtils';
import {
  buildVisibleReadModeItems,
  isReadModeTextContentItem,
  isTrailingVisibleReadModeTextItem,
  normalizeReadModeTypewriterContent,
  resolveReadModeTypewriterKeepAliveElementBid,
  shouldEnableReadModeTypewriter,
  syncReadModeTypewriterCache,
  type ReadModeTypewriterCache,
} from './readModeTypewriterGate';
import { BILLING_PACKAGES_HREF } from '@/lib/billingNavigation';
import { Button } from '@/components/ui/Button';
import { shouldHideReadModeContentForLoading } from './readModeRenderState';
import {
  projectListenModeItems,
  projectReadModeItems,
} from './chatUiModeProjection';
import { findLastVisibleLessonFeedbackElementBid } from './lessonFeedbackPromptState';
import LessonPdfDownloadCard from './LessonPdfDownloadCard';
import {
  isLessonPdfContentReady,
  shouldExcludeLessonPdfInteraction,
} from './lessonPdfState';
import { useLessonPdfPrint } from './useLessonPdfPrint';
import LessonPdfPreparingOverlay from './LessonPdfPreparingOverlay';

const CREDIT_INSUFFICIENT_ERROR_CODE = 7101;

// Max concurrent listen-mode audio backfill requests. Entering listen mode used
// to fire TTS synthesis for every missing block at once (Promise.all), which
// could burst past the provider RPM limit; a small bounded pool keeps the
// instantaneous request rate well under it.
const LISTEN_AUDIO_BACKFILL_CONCURRENCY = 3;

interface NewChatComponentsProps {
  className?: string;
  lessonUpdate: (val: any) => void;
  onGoChapter: (id: any) => void;
  chapterId: string;
  lessonId?: string;
  lessonTitle?: string;
  lessonStatus?: string;
  lessonHasContentUpdate?: boolean;
  onPurchased: () => void;
  chapterUpdate: any;
  updateSelectedLesson: any;
  getNextLessonId: any;
  previewMode?: boolean;
  isNavOpen?: boolean;
  onListenPlayerVisibilityChange?: (visible: boolean) => void;
  onListenMobileViewModeChange?: ListenMobileViewModeChangeHandler;
  showGenerateBtn?: boolean;
  onLessonUpdateNoticeVisibilityChange?: (visible: boolean) => void;
}

const isContentItemWithElementBid = (item: ChatContentItem) =>
  item.type === ChatContentItemType.CONTENT &&
  Boolean(item.element_bid?.trim()) &&
  item.element_bid !== 'loading';

export const NewChatComponents = ({
  className,
  lessonUpdate,
  onGoChapter,
  chapterId,
  lessonId,
  lessonTitle = '',
  lessonStatus = '',
  lessonHasContentUpdate = false,
  onPurchased,
  chapterUpdate,
  updateSelectedLesson,
  getNextLessonId,
  previewMode = false,
  isNavOpen = false,
  onListenPlayerVisibilityChange,
  onListenMobileViewModeChange,
  showGenerateBtn = false,
  onLessonUpdateNoticeVisibilityChange,
}: NewChatComponentsProps) => {
  const { trackEvent, trackTrailProgress } = useTracking();
  const { t } = useTranslation();
  const router = useRouter();
  const lessonFeedbackSubmitLabel = t('module.chat.lessonFeedbackSubmit');
  const askButtonMarkup = useMemo(
    () =>
      `<custom-button-after-content><img src="${AskIcon.src}" alt="ask" width="14" height="14" /><span>${t('module.chat.ask')}</span></custom-button-after-content>`,
    [t],
  );
  const chatBoxBottomRef = useRef<HTMLDivElement | null>(null);
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('module.chat.outputInProgress'),
    });
  }, [t]);
  const handleGoToBilling = useCallback(() => {
    router.push(BILLING_PACKAGES_HREF);
  }, [router]);

  const { courseId: shifuBid } = useEnvStore.getState();
  const { logoHorizontal, logoWideUrl } = useEnvStore(
    useShallow(state => ({
      logoHorizontal: state.logoHorizontal,
      logoWideUrl: state.logoWideUrl,
    })),
  );
  const printBrandLogo = resolveWideLogoSource(logoWideUrl, logoHorizontal);
  const { refreshUserInfo } = useUserStore(
    useShallow(state => ({
      refreshUserInfo: state.refreshUserInfo,
    })),
  );
  const { courseAvatar, courseName } = useCourseStore(
    useShallow(state => ({
      courseAvatar: state.courseAvatar,
      courseName: state.courseName,
    })),
  );
  const { mobileStyle } = useContext(AppContext);

  const chatRef = useRef<HTMLDivElement | null>(null);
  const { scrollToLesson } = useChatComponentsScroll({
    chatRef,
    containerStyle: styles.chatComponents,
    messages: [],
    appendMsg: () => {},
    deleteMsg: () => {},
  });

  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);
  const [listenFullscreenPortalTarget, setListenFullscreenPortalTarget] =
    useState<HTMLElement | null>(null);
  // const { scrollToBottom } = useAutoScroll(chatRef as any, {
  //   threshold: 120,
  // });

  const [showScrollDown, setShowScrollDown] = useState(false);
  const [isReadFeedbackReady, setIsReadFeedbackReady] = useState(false);
  const [isReadFeedbackAnchorVisible, setIsReadFeedbackAnchorVisible] =
    useState(false);
  const [readFeedbackTriggerElement, setReadFeedbackTriggerElement] =
    useState<HTMLDivElement | null>(null);
  const listenTtsToastShownRef = useRef(false);
  const [isListenFeedbackReady, setIsListenFeedbackReady] = useState(false);
  const listenAudioBackfillInFlightRef = useRef<Record<string, Promise<any>>>(
    {},
  );
  const listenAudioBackfillFailedBlockBidsRef = useRef<Set<string>>(new Set());
  const listenAudioBackfillLessonIdRef = useRef('');

  const scrollToBottom = useCallback(() => {
    chatBoxBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const isNearBottom = useCallback(
    (element?: HTMLElement | Document | null) => {
      if (!element) {
        return true;
      }
      if (element instanceof HTMLElement) {
        const { scrollTop, scrollHeight, clientHeight } = element;
        return (
          scrollHeight <= clientHeight ||
          scrollHeight - scrollTop - clientHeight < 150
        );
      }
      const docEl = document.documentElement;
      const scrollTop = window.scrollY || docEl.scrollTop;
      const { scrollHeight, clientHeight } = docEl;
      return (
        scrollHeight <= clientHeight ||
        scrollHeight - scrollTop - clientHeight < 150
      );
    },
    [],
  );

  const isScrollableElement = useCallback((element?: HTMLElement | null) => {
    if (!element) {
      return false;
    }

    return element.scrollHeight > element.clientHeight + 1;
  }, []);

  const resolveScrollPresentation = useCallback(() => {
    const localContainers: HTMLElement[] = [];

    if (chatRef.current) {
      localContainers.push(chatRef.current);
      if (chatRef.current.parentElement) {
        localContainers.push(chatRef.current.parentElement);
      }
    }

    const containers: Array<HTMLElement | Document> = [...localContainers];
    const shouldUseDocumentScroll =
      mobileStyle || !localContainers.some(isScrollableElement);

    // Desktop read mode sometimes scrolls on the page instead of the chat body.
    // Fall back to the document scroll position so lesson feedback does not open early.
    if (shouldUseDocumentScroll) {
      containers.push(document);
    }

    const shouldShow = containers.some(container => !isNearBottom(container));
    return {
      shouldShow,
    };
  }, [isNearBottom, isScrollableElement, mobileStyle]);

  const resolveReadFeedbackObserverRoot = useCallback(() => {
    const chatContainer = chatRef.current;
    if (chatContainer && isScrollableElement(chatContainer)) {
      return chatContainer;
    }

    const parentContainer = chatContainer?.parentElement;
    if (parentContainer && isScrollableElement(parentContainer)) {
      return parentContainer;
    }

    return null;
  }, [isScrollableElement]);

  const checkScroll = useCallback(() => {
    requestAnimationFrame(() => {
      const nextPresentation = resolveScrollPresentation();
      setShowScrollDown(nextPresentation.shouldShow);
    });
  }, [resolveScrollPresentation]);

  const { openPayModal, payModalResult, resetedLessonId, resettingLessonId } =
    useCourseStore(
      useShallow(state => ({
        openPayModal: state.openPayModal,
        payModalResult: state.payModalResult,
        resetedLessonId: state.resetedLessonId,
        resettingLessonId: state.resettingLessonId,
      })),
    );
  const shouldShowResetLoading =
    mobileStyle &&
    (resettingLessonId === lessonId || resetedLessonId === lessonId);
  const { learningMode, updateLearningMode } = useSystemStore(
    useShallow(state => ({
      learningMode: state.learningMode,
      updateLearningMode: state.updateLearningMode,
    })),
  );
  const isListenMode = learningMode === 'listen';
  const isClassroomMode = learningMode === 'classroom';
  const isSlideMode = isListenMode || isClassroomMode;
  const [readModeTypewriterCache, setReadModeTypewriterCache] =
    useState<ReadModeTypewriterCache>({});
  const courseTtsEnabled = useCourseStore(state => state.courseTtsEnabled);
  const isListenModeAvailable = courseTtsEnabled !== false;
  const isListenModeActive = getIsListenModeActive({
    learningMode,
    courseTtsEnabled,
  });
  const isListenModeActiveRef = useRef(isListenModeActive);
  const previousListenModeActiveRef = useRef(isListenModeActive);
  // Normalize lesson scope for downstream APIs and stores that require a string key.
  const resolvedLessonId = lessonId || '';
  const promptContextKey = `${resolvedLessonId}:${
    isClassroomMode ? 'classroom' : isListenModeActive ? 'listen' : 'read'
  }`;
  const [settledPromptContextKey, setSettledPromptContextKey] =
    useState(promptContextKey);
  const isPreviewReadMode = previewMode && learningMode === 'read';
  const shouldShowAudioAction =
    !isClassroomMode &&
    (previewMode || isListenModeActive) &&
    !isPreviewReadMode;
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  const isPromptContextSettled = settledPromptContextKey === promptContextKey;
  const ensureLessonScope = useAskStateStore(state => state.ensureLessonScope);
  const hydrateAskListMap = useAskStateStore(state => state.hydrateAskListMap);
  const lessonScopeKey = useAskStateStore(state => state.lessonScopeKey);
  const storedAskListByAnchorElementBid = useAskStateStore(
    state => state.askListByAnchorElementBid,
  );

  useEffect(() => {
    listenAudioBackfillLessonIdRef.current = resolvedLessonId;
    listenAudioBackfillInFlightRef.current = {};
    listenAudioBackfillFailedBlockBidsRef.current = new Set();
  }, [resolvedLessonId]);

  useEffect(() => {
    if (!previousListenModeActiveRef.current && isListenModeActive) {
      listenAudioBackfillFailedBlockBidsRef.current = new Set();
    }
    previousListenModeActiveRef.current = isListenModeActive;
    isListenModeActiveRef.current = isListenModeActive;
  }, [isListenModeActive]);

  const onPayModalOpen = useCallback(() => {
    openPayModal();
  }, [openPayModal]);

  useEffect(() => {
    if (payModalResult === 'ok') {
      onPurchased?.();
      refreshUserInfo();
    }
  }, [onPurchased, payModalResult, refreshUserInfo]);

  const [mobileInteraction, setMobileInteraction] = useState({
    open: false,
    position: { x: 0, y: 0 },
    elementBid: '',
  });
  const [longPressedBlockBid, setLongPressedBlockBid] = useState<string>('');
  const dismissMobileInteraction = useCallback(() => {
    setMobileInteraction(prev => {
      if (!prev.open) {
        return prev;
      }
      return { ...prev, open: false };
    });
    setLongPressedBlockBid('');
  }, []);

  // Streaming TTS sequential playback (auto-play next block)
  const autoPlayAudio = isListenModeActive;
  const [currentPlayingBlockBid, setCurrentPlayingBlockBid] = useState<
    string | null
  >(null);
  const currentPlayingBlockBidRef = useRef<string | null>(null);
  const playedBlocksRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    currentPlayingBlockBidRef.current = currentPlayingBlockBid;
  }, [currentPlayingBlockBid]);

  useEffect(() => {
    if (isListenModeActive) {
      return;
    }
    requestExclusive(() => {});
    releaseExclusive();
    currentPlayingBlockBidRef.current = null;
    setCurrentPlayingBlockBid(null);
  }, [isListenModeActive, releaseExclusive, requestExclusive]);

  useEffect(() => {
    if (!isListenMode || isListenModeAvailable) {
      listenTtsToastShownRef.current = false;
      return;
    }
    if (listenTtsToastShownRef.current) {
      return;
    }
    fail(t('module.chat.listenModeTtsDisabled'));
    listenTtsToastShownRef.current = true;
  }, [isListenMode, isListenModeAvailable, t]);

  const {
    items,
    isLoading,
    isOutputInProgress,
    hasRunFailed,
    currentStreamingElementBid,
    currentTypewriterElementBid,
    onSend,
    onRefresh,
    toggleAskExpanded,
    reGenerateConfirm,
    requestAudioForBlock,
    lessonFeedbackPopup,
    showLessonUpdateNotice,
  } = useChatLogicHook({
    onGoChapter,
    shifuBid,
    outlineBid: resolvedLessonId,
    lessonId: resolvedLessonId,
    chapterId,
    previewMode,
    lessonHasContentUpdate,
    isListenMode: isListenModeActive,
    trackEvent,
    chatBoxBottomRef,
    trackTrailProgress,
    lessonUpdate,
    chapterUpdate,
    updateSelectedLesson,
    getNextLessonId,
    scrollToLesson,
    listenRequestEnabled: isListenModeActive,
    shouldPromptLessonFeedback:
      !isClassroomMode &&
      isPromptContextSettled &&
      (isListenModeActive
        ? isListenFeedbackReady
        : isReadFeedbackReady && isReadFeedbackAnchorVisible),
    // scrollToBottom,
    showOutputInProgressToast,
    onPayModalOpen,
  });

  useEffect(() => {
    onLessonUpdateNoticeVisibilityChange?.(showLessonUpdateNotice);
  }, [onLessonUpdateNoticeVisibilityChange, showLessonUpdateNotice]);

  useEffect(
    () => () => {
      onLessonUpdateNoticeVisibilityChange?.(false);
    },
    [onLessonUpdateNoticeVisibilityChange],
  );

  const requestListenAudioBackfillForBlock = useCallback(
    (blockBid: string, lessonIdAtRequest: string) => {
      const existingPromise = listenAudioBackfillInFlightRef.current[blockBid];
      if (existingPromise) {
        return existingPromise;
      }

      let streamSettled = false;
      let trackedPromise: Promise<any> | null = null;
      const clearTrackedRequest = () => {
        streamSettled = true;
        if (
          trackedPromise &&
          listenAudioBackfillInFlightRef.current[blockBid] === trackedPromise
        ) {
          delete listenAudioBackfillInFlightRef.current[blockBid];
        }
      };

      trackedPromise = requestAudioForBlock(blockBid, {
        listen: true,
        shouldApplyResult: () =>
          listenAudioBackfillLessonIdRef.current === lessonIdAtRequest,
        onStreamSettled: clearTrackedRequest,
      }).then(result => {
        if (result) {
          listenAudioBackfillFailedBlockBidsRef.current.delete(blockBid);
        }
        return result;
      });

      listenAudioBackfillInFlightRef.current[blockBid] = trackedPromise;
      if (streamSettled) {
        clearTrackedRequest();
      }
      return trackedPromise;
    },
    [requestAudioForBlock],
  );

  const baseAskListByAnchorElementBid = useMemo(
    () => buildAskListByAnchorElementBid(items),
    [items],
  );
  const scopedAskListByAnchorElementBid = useMemo(
    () =>
      lessonScopeKey === resolvedLessonId
        ? storedAskListByAnchorElementBid
        : {},
    [resolvedLessonId, lessonScopeKey, storedAskListByAnchorElementBid],
  );
  const readModeItems = useMemo(
    () =>
      projectReadModeItems({
        items: items.filter(
          item =>
            item.type !== ChatContentItemType.ERROR ||
            item.business_code === CREDIT_INSUFFICIENT_ERROR_CODE,
        ),
        askListByAnchorElementBid: scopedAskListByAnchorElementBid,
        mobileStyle,
        askButtonMarkup,
      }),
    [askButtonMarkup, items, mobileStyle, scopedAskListByAnchorElementBid],
  );
  // console.log('readModeItems', readModeItems);
  const visibleReadModeItems = useMemo(
    () => buildVisibleReadModeItems(readModeItems, readModeTypewriterCache),
    [readModeItems, readModeTypewriterCache],
  );
  const isFollowUpStreaming = useMemo(
    () =>
      Object.values(scopedAskListByAnchorElementBid).some(
        hasStreamingAskMessage,
      ),
    [scopedAskListByAnchorElementBid],
  );
  const trailingVisibleReadModeTextBid = useMemo(
    () =>
      [...visibleReadModeItems]
        .reverse()
        .find(item => isReadModeTextContentItem(item))?.element_bid || '',
    [visibleReadModeItems],
  );
  const readModeFeedbackElementBid = useMemo(
    () => findLastVisibleLessonFeedbackElementBid(visibleReadModeItems),
    [visibleReadModeItems],
  );
  const isTrailingVisibleReadModeItemText = useMemo(
    () =>
      isTrailingVisibleReadModeTextItem(
        visibleReadModeItems,
        trailingVisibleReadModeTextBid,
      ),
    [trailingVisibleReadModeTextBid, visibleReadModeItems],
  );
  const readModeTypewriterKeepAliveElementBid = useMemo(
    () =>
      resolveReadModeTypewriterKeepAliveElementBid({
        isOutputInProgress,
        currentStreamingTextElementBid:
          trailingVisibleReadModeTextBid === currentStreamingElementBid
            ? currentStreamingElementBid
            : '',
        currentOutputTextElementBid: currentTypewriterElementBid,
      }),
    [
      currentStreamingElementBid,
      currentTypewriterElementBid,
      isOutputInProgress,
      trailingVisibleReadModeTextBid,
    ],
  );
  const handleReadModeTypeFinished = useCallback(
    (blockBid: string, content: string) => {
      if (!blockBid) {
        return;
      }

      const normalizedContent = normalizeReadModeTypewriterContent(content);

      setReadModeTypewriterCache(prevCache => {
        const existingEntry = prevCache[blockBid];
        if (
          existingEntry?.content === normalizedContent &&
          existingEntry.isFinished === true
        ) {
          return prevCache;
        }

        return {
          ...prevCache,
          [blockBid]: {
            content: normalizedContent,
            isFinished: true,
          },
        };
      });
    },
    [],
  );
  const getReadModeElementPadding = useCallback(
    (isFirstElement: boolean) => (isFirstElement ? '20px 20px 0' : '0 20px'),
    [],
  );
  const shouldShowReadModeStreamingDots =
    isOutputInProgress &&
    !visibleReadModeItems.some(item => item.element_bid === 'loading');
  const isReadModeStreamingDotsFirstElement = visibleReadModeItems.length === 0;
  const shouldHideReadModeContent = shouldHideReadModeContentForLoading({
    isLoading,
    hasReadModeItems: visibleReadModeItems.length > 0,
    shouldShowReadModeStreamingDots,
  });
  const isLessonPdfReady = isLessonPdfContentReady({
    courseName,
    lessonTitle,
    lessonStatus,
    isSlideMode,
    isLoading,
    isOutputInProgress,
    hasGenerationError:
      hasRunFailed ||
      items.some(item => item.type === ChatContentItemType.ERROR),
    currentStreamingElementBid,
    readModeItems,
    visibleReadModeItems,
    readModeTypewriterCache,
  });
  const handleLessonPdfPrintError = useCallback(() => {
    fail(t('module.chat.lessonPdfPrepareFailed'));
  }, [t]);
  const { isPreparing: isPreparingLessonPdf, printLessonPdf } =
    useLessonPdfPrint({
      printRootRef: chatRef,
      lessonId: resolvedLessonId,
      courseName,
      lessonTitle,
      onError: handleLessonPdfPrintError,
    });

  useEffect(() => {
    ensureLessonScope(resolvedLessonId);
  }, [ensureLessonScope, resolvedLessonId]);

  useEffect(() => {
    hydrateAskListMap(baseAskListByAnchorElementBid);
  }, [baseAskListByAnchorElementBid, hydrateAskListMap]);

  useEffect(() => {
    if (isListenModeActive && !isLoading) {
      return;
    }
    onListenPlayerVisibilityChange?.(false);
  }, [isListenModeActive, isLoading, onListenPlayerVisibilityChange]);

  useEffect(() => {
    setShowScrollDown(false);
  }, [isSlideMode, lessonId]);

  useEffect(() => {
    if (isSlideMode) {
      setIsReadFeedbackAnchorVisible(false);
      setReadFeedbackTriggerElement(null);
      return;
    }

    if (!readFeedbackTriggerElement) {
      setIsReadFeedbackAnchorVisible(false);
      return;
    }

    const observer = new IntersectionObserver(
      entries => {
        const [entry] = entries;
        setIsReadFeedbackAnchorVisible(Boolean(entry?.isIntersecting));
      },
      {
        root: resolveReadFeedbackObserverRoot(),
        threshold: 0.98,
      },
    );

    observer.observe(readFeedbackTriggerElement);

    return () => {
      observer.disconnect();
    };
  }, [
    isSlideMode,
    lessonId,
    mobileStyle,
    readFeedbackTriggerElement,
    resolveReadFeedbackObserverRoot,
  ]);

  useEffect(() => {
    setReadModeTypewriterCache(prevCache =>
      syncReadModeTypewriterCache(readModeItems, prevCache, {
        markFinalTextItemsFinished: isClassroomMode,
      }),
    );
  }, [isClassroomMode, readModeItems]);

  useEffect(() => {
    if (!isListenModeActive) {
      return;
    }

    if (!isListenModeAvailable) {
      updateLearningMode('read');
      return;
    }

    const contentItems = items.filter(isContentItemWithElementBid);

    if (!contentItems.length) {
      return;
    }

    const backfillCandidateItems = contentItems.filter(
      isListenModeAudioBackfillCandidate,
    );
    const hasPlayableAudio = contentItems.some(hasPlayableListenAudioForItem);
    const readyBackfillCandidateItems = backfillCandidateItems.filter(
      isListenModeAudioBackfillReady,
    );

    if (!backfillCandidateItems.length) {
      return;
    }

    if (!readyBackfillCandidateItems.length) {
      return;
    }

    const missingAudioBlockBids = getMissingListenModeAudioBlockBids(
      readyBackfillCandidateItems,
    ).filter(
      blockBid => !listenAudioBackfillFailedBlockBidsRef.current.has(blockBid),
    );

    if (!missingAudioBlockBids.length) {
      return;
    }

    const lessonIdAtRequest = resolvedLessonId;

    listenAudioBackfillLessonIdRef.current = lessonIdAtRequest;

    // Prioritise blocks that will actually be played (non-history) so the first
    // playable block is synthesised before history blocks, which auto-play
    // skips. Otherwise the bounded pool could spend its slots on leading history
    // blocks and delay first playback.
    const historyBlockBidSet = new Set(
      readyBackfillCandidateItems
        .filter(item => item.isHistory)
        .map(item => item.element_bid),
    );
    const prioritizedBlockBids = [
      ...missingAudioBlockBids.filter(bid => !historyBlockBidSet.has(bid)),
      ...missingAudioBlockBids.filter(bid => historyBlockBidSet.has(bid)),
    ];

    void runWithConcurrency(
      prioritizedBlockBids,
      LISTEN_AUDIO_BACKFILL_CONCURRENCY,
      blockBid =>
        requestListenAudioBackfillForBlock(blockBid, lessonIdAtRequest)
          .then(result => {
            if (listenAudioBackfillLessonIdRef.current !== lessonIdAtRequest) {
              return null;
            }

            return result;
          })
          .catch(() => null),
    ).then(results => {
      if (listenAudioBackfillLessonIdRef.current !== lessonIdAtRequest) {
        return;
      }

      const hasGeneratedAudio = results.some(Boolean);
      const failedBlockBids = prioritizedBlockBids.filter(
        (_, index) => !results[index],
      );
      failedBlockBids.forEach(blockBid => {
        listenAudioBackfillFailedBlockBidsRef.current.add(blockBid);
      });
      const hasBackfillFailure = failedBlockBids.length > 0;
      const hasBackfillInFlight =
        Object.keys(listenAudioBackfillInFlightRef.current).length > 0;

      if (hasBackfillFailure && isListenModeActiveRef.current) {
        if (hasGeneratedAudio || hasPlayableAudio || isOutputInProgress) {
          return;
        }

        fail(t('module.chat.listenAudioBackfillFailed'));
        return;
      }

      if (
        hasGeneratedAudio ||
        hasPlayableAudio ||
        !isListenModeActiveRef.current
      ) {
        return;
      }

      if (hasBackfillInFlight) {
        return;
      }

      fail(t('module.chat.listenAudioBackfillFailed'));
    });
  }, [
    isListenModeActive,
    isListenModeAvailable,
    isOutputInProgress,
    items,
    previewMode,
    requestListenAudioBackfillForBlock,
    resolvedLessonId,
    t,
    updateLearningMode,
  ]);

  useEffect(() => {
    setIsListenFeedbackReady(false);
    setIsReadFeedbackReady(false);
    setSettledPromptContextKey(promptContextKey);
  }, [promptContextKey]);

  useEffect(() => {
    if (!isListenModeActive) {
      setIsListenFeedbackReady(false);
      return;
    }

    if (isLoading) {
      setIsListenFeedbackReady(false);
      return;
    }
  }, [isListenModeActive, isLoading, lessonId]);

  useEffect(() => {
    if (isSlideMode) {
      setIsReadFeedbackReady(false);
      return;
    }

    if (
      isLoading ||
      isOutputInProgress ||
      Boolean(currentTypewriterElementBid)
    ) {
      setIsReadFeedbackReady(false);
      return;
    }

    setIsReadFeedbackReady(false);

    const rafId = window.requestAnimationFrame(() => {
      const nextPresentation = resolveScrollPresentation();
      setShowScrollDown(nextPresentation.shouldShow);
      setIsReadFeedbackReady(true);
    });

    return () => {
      window.cancelAnimationFrame(rafId);
    };
  }, [
    currentTypewriterElementBid,
    isSlideMode,
    isLoading,
    isOutputInProgress,
    items.length,
    promptContextKey,
    resolveScrollPresentation,
  ]);

  const slideModeItems = useMemo(
    () =>
      projectListenModeItems({
        items,
        askButtonMarkup,
        variant: isClassroomMode ? 'classroom' : 'listen',
      }),
    [askButtonMarkup, isClassroomMode, items],
  );

  const itemByGeneratedBid = useMemo(() => {
    const mapping = new Map<string, ChatContentItem>();
    items.forEach(item => {
      if (item.element_bid) {
        mapping.set(item.element_bid, item);
      }
    });
    return mapping;
  }, [items]);

  const handleAudioPlayStateChange = useCallback(
    (blockBid: string, isPlaying: boolean) => {
      if (!isPlaying) {
        return;
      }
      currentPlayingBlockBidRef.current = blockBid;
      setCurrentPlayingBlockBid(blockBid);
    },
    [],
  );

  const handleAudioEnded = useCallback((blockBid: string) => {
    if (currentPlayingBlockBidRef.current !== blockBid) {
      return;
    }
    playedBlocksRef.current.add(blockBid);
    currentPlayingBlockBidRef.current = null;
    setCurrentPlayingBlockBid(null);
  }, []);

  useEffect(() => {
    playedBlocksRef.current.clear();
    currentPlayingBlockBidRef.current = null;
    setCurrentPlayingBlockBid(null);
  }, [lessonId]);

  const autoPlayTargetBlockBid = useMemo(() => {
    if (!autoPlayAudio) {
      return null;
    }

    if (currentPlayingBlockBid) {
      return currentPlayingBlockBid;
    }

    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      if (item.isHistory) {
        continue;
      }
      const blockBid = item.element_bid;
      if (!blockBid || blockBid === 'loading') {
        continue;
      }
      if (playedBlocksRef.current.has(blockBid)) {
        continue;
      }
      const primaryTrack = getAudioTrackByPosition(item.audioTracks ?? []);
      if (!hasAudioContentInTrack(primaryTrack)) {
        continue;
      }
      return blockBid;
    }

    return null;
  }, [autoPlayAudio, currentPlayingBlockBid, items]);

  const mobileInteractionPrimaryTrack = useMemo(
    () =>
      getAudioTrackByPosition(
        itemByGeneratedBid.get(mobileInteraction.elementBid)?.audioTracks ?? [],
      ),
    [itemByGeneratedBid, mobileInteraction.elementBid],
  );

  // Memoize onSend to prevent new function references
  const memoizedOnSend = useCallback(onSend, [onSend]);

  const handleLongPress = useCallback(
    (event: any, currentBlock: ChatContentItem) => {
      if (currentBlock.type !== ChatContentItemType.CONTENT) {
        return;
      }
      if (
        currentStreamingElementBid &&
        currentBlock.element_bid === currentStreamingElementBid
      ) {
        return;
      }
      const primaryTrack = getAudioTrackByPosition(
        currentBlock.audioTracks ?? [],
      );
      const hasMobileAudioAction =
        shouldShowAudioAction &&
        (hasAudioContentInTrack(primaryTrack) ||
          Boolean(primaryTrack?.isAudioStreaming) ||
          (!previewMode && Boolean(currentBlock.element_bid)));
      if (!showGenerateBtn && !hasMobileAudioAction) {
        return;
      }
      const target = event.target as HTMLElement;
      const rect = target.getBoundingClientRect();
      // Use requestAnimationFrame to avoid blocking rendering
      requestAnimationFrame(() => {
        setLongPressedBlockBid(currentBlock.element_bid);
        setMobileInteraction({
          open: true,
          position: {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
          },
          elementBid: currentBlock.element_bid || '',
        });
      });
    },
    [
      currentStreamingElementBid,
      previewMode,
      shouldShowAudioAction,
      showGenerateBtn,
    ],
  );

  useEffect(() => {
    if (!mobileStyle) {
      dismissMobileInteraction();
    }
  }, [dismissMobileInteraction, mobileStyle]);

  // Close mobile interaction popover on outside interaction or page context changes.
  useEffect(() => {
    if (!mobileStyle || !mobileInteraction.open) {
      return;
    }

    const isInsideMobileInteractionPopover = (target: EventTarget | null) => {
      if (!(target instanceof Node)) {
        return false;
      }
      const element =
        target instanceof Element ? target : (target.parentElement ?? null);
      return Boolean(
        element?.closest('[data-mobile-interaction-popover="true"]'),
      );
    };

    const handleOutsidePointerDown = (event: Event) => {
      if (isInsideMobileInteractionPopover(event.target)) {
        return;
      }
      dismissMobileInteraction();
    };

    const handleTouchMove = (event: TouchEvent) => {
      if (isInsideMobileInteractionPopover(event.target)) {
        return;
      }
      dismissMobileInteraction();
    };

    const handleScroll = () => {
      dismissMobileInteraction();
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        dismissMobileInteraction();
      }
    };

    const handlePageHide = () => {
      dismissMobileInteraction();
    };

    const handleWindowBlur = () => {
      dismissMobileInteraction();
    };

    const chatContainer = chatRef.current;
    const parentContainer = chatContainer?.parentElement;

    document.addEventListener('pointerdown', handleOutsidePointerDown, true);
    document.addEventListener('touchmove', handleTouchMove, {
      capture: true,
      passive: true,
    });
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleWindowBlur);
    window.addEventListener('pagehide', handlePageHide);
    window.addEventListener('scroll', handleScroll, {
      capture: true,
      passive: true,
    });
    chatContainer?.addEventListener('scroll', handleScroll, { passive: true });
    if (parentContainer) {
      parentContainer.addEventListener('scroll', handleScroll, {
        passive: true,
      });
    }

    return () => {
      document.removeEventListener(
        'pointerdown',
        handleOutsidePointerDown,
        true,
      );
      document.removeEventListener('touchmove', handleTouchMove, true);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleWindowBlur);
      window.removeEventListener('pagehide', handlePageHide);
      window.removeEventListener('scroll', handleScroll, true);
      chatContainer?.removeEventListener('scroll', handleScroll);
      parentContainer?.removeEventListener('scroll', handleScroll);
    };
  }, [dismissMobileInteraction, mobileStyle, mobileInteraction.open]);

  // Memoize callbacks to prevent unnecessary re-renders
  const handleClickAskButton = useCallback(
    (blockBid: string) => {
      toggleAskExpanded(blockBid);
    },
    [toggleAskExpanded],
  );

  useEffect(() => {
    const container = chatRef.current;
    const parentContainer = container?.parentElement;
    const listeners: Array<{ element: EventTarget; handler: () => void }> = [];
    const shouldTrackWindowScroll =
      mobileStyle ||
      ![container, parentContainer].some(
        element => element && isScrollableElement(element),
      );

    if (container) {
      container.addEventListener('scroll', checkScroll, { passive: true });
      listeners.push({ element: container, handler: checkScroll });
    }

    if (parentContainer) {
      parentContainer.addEventListener('scroll', checkScroll, {
        passive: true,
      });
      listeners.push({ element: parentContainer, handler: checkScroll });
    }

    if (shouldTrackWindowScroll) {
      window.addEventListener('scroll', checkScroll, { passive: true });
      listeners.push({ element: window, handler: checkScroll });
    }

    const resizeObserver = new ResizeObserver(() => {
      checkScroll();
    });

    if (container) {
      resizeObserver.observe(container);

      if (container.firstElementChild) {
        resizeObserver.observe(container.firstElementChild);
      }
    }

    checkScroll();

    return () => {
      listeners.forEach(({ element, handler }) => {
        element.removeEventListener('scroll', handler);
      });
      resizeObserver.disconnect();
    };
  }, [checkScroll, isSlideMode, isScrollableElement, items, mobileStyle]);

  useEffect(() => {
    if (mobileStyle) {
      setPortalTarget(document.getElementById('chat-scroll-target'));
    } else {
      setPortalTarget(null);
    }
  }, [mobileStyle]);

  const syncListenFullscreenPortalTarget = useCallback(() => {
    const chatElement = chatRef.current;
    if (!isListenModeActive || !chatElement) {
      setListenFullscreenPortalTarget(null);
      return;
    }

    const nextContainer =
      chatElement.querySelector<HTMLElement>(
        '.listen-slide-root .slide__viewport',
      ) ?? null;
    const fullscreenElement = getDocumentFullscreenElement();
    const isCurrentSlideInBrowserFullscreen = Boolean(
      fullscreenElement && chatElement.contains(fullscreenElement),
    );

    setListenFullscreenPortalTarget(
      isCurrentSlideInBrowserFullscreen ? nextContainer : null,
    );
  }, [isListenModeActive]);

  useEffect(() => {
    const syncContainer = () => {
      window.requestAnimationFrame(() => {
        syncListenFullscreenPortalTarget();
      });
    };

    syncContainer();

    document.addEventListener('fullscreenchange', syncContainer);
    document.addEventListener('webkitfullscreenchange', syncContainer);

    return () => {
      document.removeEventListener('fullscreenchange', syncContainer);
      document.removeEventListener('webkitfullscreenchange', syncContainer);
    };
  }, [lessonId, syncListenFullscreenPortalTarget]);

  const containerClassName = cn(
    styles.chatComponents,
    className,
    mobileStyle ? styles.mobile : '',
  );

  const scrollButton = (
    <button
      className={cn(
        styles.scrollToBottom,
        showScrollDown ? styles.visible : '',
        mobileStyle ? styles.mobileScrollBtn : '',
      )}
      onClick={scrollToBottom}
    >
      <ChevronsDown size={20} />
    </button>
  );

  const lessonFeedbackPopupContent =
    lessonFeedbackPopup.open && !(mobileStyle && isNavOpen) ? (
      <div
        className={cn(
          'pointer-events-none z-20',
          mobileStyle
            ? isListenModeActive
              ? 'fixed left-3 right-3 bottom-[88px]'
              : 'fixed left-3 right-3 bottom-[56px]'
            : 'absolute right-6 w-[260px] max-w-[calc(100%-48px)] bottom-6',
        )}
      >
        <div className='pointer-events-auto rounded-2xl border border-[var(--border)] bg-[var(--card)] p-3 shadow-lg'>
          <div className='mb-2 flex items-center justify-between gap-2'>
            <p className='text-[14px] leading-5 text-[var(--foreground)]'>
              {t('module.chat.lessonFeedbackPrompt')}
            </p>
            <button
              type='button'
              aria-label={t('common.core.cancel')}
              onClick={lessonFeedbackPopup.onClose}
              className='inline-flex h-6 w-6 items-center justify-center rounded text-foreground/50 transition-colors hover:bg-[var(--muted)] hover:text-foreground/75'
            >
              <X className='h-4 w-4' />
            </button>
          </div>
          <LessonFeedbackInteraction
            defaultScoreText={lessonFeedbackPopup.defaultScoreText}
            defaultCommentText={lessonFeedbackPopup.defaultCommentText}
            placeholder={t('module.chat.lessonFeedbackCommentPlaceholder')}
            submitLabel={lessonFeedbackSubmitLabel}
            clearLabel={t('module.chat.lessonFeedbackClearInput')}
            readonly={lessonFeedbackPopup.readonly}
            onSubmit={lessonFeedbackPopup.onSubmit}
          />
        </div>
      </div>
    ) : null;
  return (
    <div
      data-lesson-print-content='true'
      className={containerClassName}
      style={{ position: 'relative', overflow: 'hidden', padding: 0 }}
    >
      {isSlideMode ? (
        isClassroomMode || isListenModeAvailable ? (
          <>
            <ListenModeSlideRenderer
              items={slideModeItems}
              mobileStyle={mobileStyle}
              chatRef={chatRef as React.RefObject<HTMLDivElement>}
              isLoading={isLoading}
              courseAvatar={courseAvatar}
              courseName={courseName}
              sectionTitle={lessonTitle}
              lessonId={lessonId}
              shifuBid={shifuBid}
              previewMode={previewMode}
              lessonStatus={lessonStatus}
              variant={isClassroomMode ? 'classroom' : 'listen'}
              onMobileViewModeChange={onListenMobileViewModeChange}
              onSend={memoizedOnSend}
              onPlayerVisibilityChange={onListenPlayerVisibilityChange}
              onLessonFeedbackPromptStateChange={setIsListenFeedbackReady}
            />
          </>
        ) : (
          <div
            className={cn(
              containerClassName,
              'listen-reveal-wrapper',
              mobileStyle
                ? 'mobile bg-white'
                : 'bg-[var(--color-slide-desktop-bg)]',
            )}
          />
        )
      ) : (
        <div
          data-lesson-print-scroll='true'
          className={containerClassName}
          ref={chatRef}
          style={{ width: '100%', height: '100%', overflowY: 'auto' }}
        >
          <div>
            <header
              data-lesson-print-only='true'
              className='lesson-pdf-print-header mx-auto max-w-[1000px] border-b border-border px-5 pb-5'
            >
              <div className='flex items-center gap-4'>
                {courseAvatar ? (
                  <Image
                    data-lesson-print-course-avatar='true'
                    src={courseAvatar}
                    alt=''
                    width={44}
                    height={44}
                    loading='eager'
                    unoptimized
                    className='h-11 w-11 shrink-0 rounded-full object-cover'
                  />
                ) : null}
                <div className='min-w-0 flex-1'>
                  <h1
                    data-lesson-print-course-name='true'
                    className='break-words text-2xl font-semibold leading-tight text-foreground'
                  >
                    {courseName}
                  </h1>
                  <h2
                    data-lesson-print-lesson-title='true'
                    className='mt-2 break-words text-lg font-medium leading-tight text-muted-foreground'
                  >
                    {lessonTitle}
                  </h2>
                </div>
                <Image
                  data-lesson-print-site-logo='true'
                  src={printBrandLogo}
                  alt=''
                  width={92}
                  height={24}
                  loading='eager'
                  unoptimized
                  className='h-6 w-auto shrink-0 object-contain'
                />
              </div>
            </header>
            {shouldShowResetLoading ? (
              <div
                style={{
                  margin: '0 auto',
                  maxWidth: '1000px',
                  padding: getReadModeElementPadding(true),
                }}
              >
                <LoadingBar />
              </div>
            ) : shouldHideReadModeContent ? (
              <></>
            ) : (
              <>
                {visibleReadModeItems.map((item, idx) => {
                  const isLongPressed =
                    longPressedBlockBid === item.element_bid;
                  const baseKey = item.element_bid || `${item.type}-${idx}`;
                  const parentKey = item.parent_element_bid || baseKey;
                  if (item.type === ChatContentItemType.ASK) {
                    return (
                      <div
                        data-lesson-print-follow-up='true'
                        key={`ask-${parentKey}`}
                        style={{
                          position: 'relative',
                          margin: '0 auto',
                          maxWidth: mobileStyle ? '100%' : '1000px',
                          padding: '0 20px',
                        }}
                      >
                        <AskBlock
                          isExpanded={item.isAskExpanded}
                          printMode={isPreparingLessonPdf}
                          shifu_bid={shifuBid}
                          outline_bid={resolvedLessonId}
                          preview_mode={previewMode}
                          element_bid={item.parent_element_bid || ''}
                          onToggleAskExpanded={toggleAskExpanded}
                          askList={(item.ask_list || []) as any[]}
                        />
                      </div>
                    );
                  }

                  if (item.type === ChatContentItemType.LIKE_STATUS) {
                    const parentElementBid = item.parent_element_bid || '';
                    if (!parentElementBid) {
                      return null;
                    }
                    const parentContentItem = parentElementBid
                      ? itemByGeneratedBid.get(parentElementBid)
                      : undefined;
                    const parentPrimaryTrack = getAudioTrackByPosition(
                      parentContentItem?.audioTracks ?? [],
                    );
                    const canRequestAudio =
                      !previewMode && Boolean(parentElementBid);
                    const hasAudioForElement =
                      hasAudioContentInTrack(parentPrimaryTrack);
                    const shouldAutoPlayElement =
                      autoPlayTargetBlockBid === parentElementBid;
                    const isInteractionFollowUp =
                      parentContentItem?.type ===
                      ChatContentItemType.INTERACTION;
                    const shouldRenderMobileAskAction =
                      mobileStyle && isInteractionFollowUp;

                    if (mobileStyle && !shouldRenderMobileAskAction) {
                      return null;
                    }

                    return (
                      <div
                        data-lesson-print-exclude='true'
                        key={`like-${parentKey}`}
                        className={cn(!mobileStyle && 'flex justify-end')}
                        style={{
                          margin: '0 auto',
                          maxWidth: mobileStyle ? '100%' : '1000px',
                          padding: '0px 20px',
                        }}
                      >
                        <InteractionBlock
                          shifu_bid={shifuBid}
                          element_bid={parentElementBid}
                          className={
                            isInteractionFollowUp
                              ? 'interaction-block--no-padding-top'
                              : undefined
                          }
                          readonly={item.readonly}
                          disableAskButton={isInteractionFollowUp}
                          onRefresh={onRefresh}
                          onToggleAskExpanded={toggleAskExpanded}
                          askButtonVariant={
                            shouldRenderMobileAskAction ? 'content' : 'default'
                          }
                          showGenerateBtn={!mobileStyle && showGenerateBtn}
                          extraActions={
                            !mobileStyle &&
                            shouldShowAudioAction &&
                            (canRequestAudio || hasAudioForElement) ? (
                              <AudioPlayer
                                audioUrl={parentPrimaryTrack?.audioUrl}
                                streamingSegments={
                                  parentPrimaryTrack?.audioSegments
                                }
                                isStreaming={Boolean(
                                  parentPrimaryTrack?.isAudioStreaming,
                                )}
                                alwaysVisible={canRequestAudio}
                                onRequestAudio={
                                  canRequestAudio
                                    ? () =>
                                        requestAudioForBlock(parentElementBid)
                                    : undefined
                                }
                                autoPlay={shouldAutoPlayElement}
                                onPlayStateChange={isPlaying =>
                                  handleAudioPlayStateChange(
                                    parentElementBid,
                                    isPlaying,
                                  )
                                }
                                onEnded={() =>
                                  handleAudioEnded(parentElementBid)
                                }
                                className='interaction-icon-btn'
                                size={16}
                              />
                            ) : null
                          }
                        />
                      </div>
                    );
                  }

                  if (item.type === ChatContentItemType.ERROR) {
                    return (
                      <div
                        data-lesson-print-exclude='true'
                        key={`error-${baseKey}`}
                        style={{
                          position: 'relative',
                          margin: !idx ? '0 auto' : '40px auto 0 auto',
                          maxWidth: mobileStyle ? '100%' : '1000px',
                          padding: getReadModeElementPadding(idx === 0),
                        }}
                      >
                        <ContentBlock
                          item={item}
                          mobileStyle={mobileStyle}
                          blockBid={item.element_bid}
                          onClickCustomButtonAfterContent={handleClickAskButton}
                          onSend={memoizedOnSend}
                          onLongPress={handleLongPress}
                          autoPlayAudio={false}
                          showAudioAction={false}
                          onAudioPlayStateChange={handleAudioPlayStateChange}
                          onAudioEnded={handleAudioEnded}
                        />
                        {item.business_code ===
                        CREDIT_INSUFFICIENT_ERROR_CODE ? (
                          <Button
                            type='button'
                            size='sm'
                            onClick={handleGoToBilling}
                          >
                            {t('module.shifu.previewArea.goToBilling')}
                          </Button>
                        ) : null}
                      </div>
                    );
                  }

                  const isCourseInteraction =
                    item.type === ChatContentItemType.INTERACTION &&
                    !shouldExcludeLessonPdfInteraction(item.content);

                  return (
                    <div
                      data-lesson-print-exclude={
                        item.type === ChatContentItemType.INTERACTION &&
                        !isCourseInteraction
                          ? 'true'
                          : undefined
                      }
                      data-lesson-print-interaction={
                        isCourseInteraction ? 'true' : undefined
                      }
                      key={`content-${baseKey}`}
                      style={{
                        position: 'relative',
                        margin:
                          !idx || item.type === ChatContentItemType.INTERACTION
                            ? '0 auto'
                            : '40px auto 0 auto',
                        maxWidth: mobileStyle ? '100%' : '1000px',
                        padding: getReadModeElementPadding(idx === 0),
                      }}
                    >
                      {isLongPressed && mobileStyle && (
                        <div className='long-press-overlay' />
                      )}
                      {item.element_bid === readModeFeedbackElementBid ? (
                        <div
                          ref={setReadFeedbackTriggerElement}
                          aria-hidden='true'
                          className='h-px w-full'
                        />
                      ) : null}
                      {/*
                        Keep typewriter enabled when the current element content
                        has already grown beyond the finished cache snapshot.
                      */}
                      <ContentBlock
                        item={item}
                        printMode={isPreparingLessonPdf && isCourseInteraction}
                        mobileStyle={mobileStyle}
                        blockBid={item.element_bid}
                        enableStreamingTypewriter={shouldEnableReadModeTypewriter(
                          item,
                          readModeTypewriterCache[item.element_bid || ''],
                          {
                            keepAliveWhileStreaming:
                              isOutputInProgress &&
                              isTrailingVisibleReadModeItemText &&
                              readModeTypewriterKeepAliveElementBid ===
                                item.element_bid &&
                              trailingVisibleReadModeTextBid ===
                                item.element_bid,
                          },
                        )}
                        onClickCustomButtonAfterContent={handleClickAskButton}
                        onSend={memoizedOnSend}
                        onLongPress={handleLongPress}
                        autoPlayAudio={
                          autoPlayTargetBlockBid === item.element_bid
                        }
                        showAudioAction={shouldShowAudioAction}
                        onAudioPlayStateChange={handleAudioPlayStateChange}
                        onAudioEnded={handleAudioEnded}
                        onTypeFinished={handleReadModeTypeFinished}
                      />
                    </div>
                  );
                })}
                {shouldShowReadModeStreamingDots ? (
                  <div
                    data-lesson-print-exclude='true'
                    style={{
                      margin: visibleReadModeItems.length
                        ? '16px auto 0'
                        : '0 auto',
                      maxWidth: mobileStyle ? '100%' : '1000px',
                      padding: getReadModeElementPadding(
                        isReadModeStreamingDotsFirstElement,
                      ),
                    }}
                  >
                    <StreamingLoadingDotsBar />
                  </div>
                ) : null}
                {isLessonPdfReady ? (
                  <LessonPdfDownloadCard
                    isFollowUpStreaming={isFollowUpStreaming}
                    isPreparing={isPreparingLessonPdf}
                    onDownload={printLessonPdf}
                  />
                ) : null}
              </>
            )}
            <div
              data-lesson-print-exclude='true'
              ref={chatBoxBottomRef}
              id='chat-box-bottom'
            ></div>
          </div>
        </div>
      )}
      {!isSlideMode &&
        (mobileStyle && portalTarget
          ? createPortal(scrollButton, portalTarget)
          : scrollButton)}
      {mobileStyle && mobileInteraction?.elementBid && (
        <InteractionBlockM
          open={mobileInteraction.open}
          onOpenChange={open => {
            if (open) {
              setMobileInteraction(prev => ({ ...prev, open: true }));
              return;
            }
            dismissMobileInteraction();
          }}
          position={mobileInteraction.position}
          shifu_bid={shifuBid}
          element_bid={mobileInteraction.elementBid}
          onRefresh={onRefresh}
          audioUrl={mobileInteractionPrimaryTrack?.audioUrl}
          streamingSegments={mobileInteractionPrimaryTrack?.audioSegments}
          isStreaming={Boolean(mobileInteractionPrimaryTrack?.isAudioStreaming)}
          onRequestAudio={
            !previewMode && mobileInteraction.elementBid
              ? () => requestAudioForBlock(mobileInteraction.elementBid)
              : undefined
          }
          showAudioAction={shouldShowAudioAction}
          showGenerateBtn={showGenerateBtn}
        />
      )}
      {!isClassroomMode && lessonFeedbackPopupContent
        ? listenFullscreenPortalTarget
          ? createPortal(
              lessonFeedbackPopupContent,
              listenFullscreenPortalTarget,
            )
          : lessonFeedbackPopupContent
        : null}
      {isPreparingLessonPdf ? <LessonPdfPreparingOverlay /> : null}
      <Dialog
        open={reGenerateConfirm.open}
        onOpenChange={open => {
          if (!open) {
            reGenerateConfirm.onCancel();
          }
        }}
      >
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>{t('module.chat.regenerateConfirmTitle')}</DialogTitle>
            <DialogDescription>
              {t('module.chat.regenerateConfirmDescription')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className='flex gap-2 sm:gap-2'>
            <button
              type='button'
              onClick={reGenerateConfirm.onCancel}
              className='px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50'
            >
              {t('common.core.cancel')}
            </button>
            <button
              type='button'
              onClick={reGenerateConfirm.onConfirm}
              className='px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-lighter'
            >
              {t('common.core.ok')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

NewChatComponents.displayName = 'NewChatComponents';

export default memo(NewChatComponents);

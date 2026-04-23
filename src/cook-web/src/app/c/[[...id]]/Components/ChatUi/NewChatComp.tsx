import styles from './ChatComponents.module.scss';
import { ChevronsDown, Loader2, X } from 'lucide-react';
import { createPortal } from 'react-dom';
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
import InteractionBlock from './InteractionBlock';
import useChatLogicHook, { ChatContentItemType } from './useChatLogicHook';
import type { ChatContentItem } from './useChatLogicHook';
import AskBlock from './AskBlock';
import type { AskMessage } from './AskBlock';
import InteractionBlockM from './InteractionBlockM';
import ContentBlock from './ContentBlock';
import ListenModeSlideRenderer from './ListenModeSlideRenderer';
import LessonFeedbackInteraction from './LessonFeedbackInteraction';
import LoadingBar from './LoadingBar';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import {
  getAudioTrackByPosition,
  hasAudioContentInTrack,
} from '@/c-utils/audio-utils';
import { ELEMENT_TYPE } from '@/c-api/studyV2';
import { syncCustomButtonAfterContent } from './chatUiUtils';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { useSystemStore } from '@/c-store/useSystemStore';
import { buildAskListByAnchorElementBid } from './askState';
import { useAskStateStore } from './useAskStateStore';
import type { ListenMobileViewModeChangeHandler } from './listenModeTypes';
import { isListenModeActive as getIsListenModeActive } from '../learningModeOptions';
import { useSingleFlight } from '@/hooks/useSingleFlight';
import { stopActiveLessonStream } from '@/app/c/[[...id]]/events';

interface NewChatComponentsProps {
  className?: string;
  lessonUpdate: (val: any) => void;
  onGoChapter: (id: any) => Promise<void>;
  chapterId: string;
  lessonId?: string;
  lessonTitle?: string;
  lessonStatus?: string;
  onPurchased: () => void;
  chapterUpdate: any;
  updateSelectedLesson: any;
  getNextLessonId: any;
  previewMode?: boolean;
  isNavOpen?: boolean;
  onListenPlayerVisibilityChange?: (visible: boolean) => void;
  onListenMobileViewModeChange?: ListenMobileViewModeChangeHandler;
  showGenerateBtn?: boolean;
}

const buildReadModeItemsWithAskState = ({
  items,
  askListByAnchorElementBid,
  mobileStyle,
}: {
  items: ChatContentItem[];
  askListByAnchorElementBid: Record<string, AskMessage[]>;
  mobileStyle: boolean;
}) => {
  const existingAskAnchorSet = new Set<string>();
  const likeStatusAnchorSet = new Set<string>();

  items.forEach(item => {
    if (item.type === ChatContentItemType.ASK && item.parent_element_bid) {
      existingAskAnchorSet.add(item.parent_element_bid);
    }

    if (
      item.type === ChatContentItemType.LIKE_STATUS &&
      item.parent_element_bid
    ) {
      likeStatusAnchorSet.add(item.parent_element_bid);
    }
  });

  const insertedAskAnchorSet = new Set<string>();
  const nextItems: ChatContentItem[] = [];

  items.forEach(item => {
    if (item.type === ChatContentItemType.ASK) {
      const anchorElementBid = item.parent_element_bid || '';
      const storedAskList = anchorElementBid
        ? askListByAnchorElementBid[anchorElementBid]
        : undefined;

      nextItems.push(
        storedAskList
          ? ({
              ...item,
              ask_list: storedAskList as ChatContentItem[],
            } satisfies ChatContentItem)
          : item,
      );

      if (anchorElementBid) {
        insertedAskAnchorSet.add(anchorElementBid);
      }

      return;
    }

    nextItems.push(item);

    const anchorElementBid =
      item.type === ChatContentItemType.LIKE_STATUS
        ? item.parent_element_bid || ''
        : item.element_bid || '';

    if (
      !anchorElementBid ||
      existingAskAnchorSet.has(anchorElementBid) ||
      insertedAskAnchorSet.has(anchorElementBid)
    ) {
      return;
    }

    const storedAskList = askListByAnchorElementBid[anchorElementBid];

    if (!storedAskList?.length) {
      return;
    }

    const shouldInsertAfterCurrent =
      item.type === ChatContentItemType.LIKE_STATUS ||
      (!likeStatusAnchorSet.has(anchorElementBid) &&
        (item.type === ChatContentItemType.CONTENT ||
          item.type === ChatContentItemType.INTERACTION));

    if (!shouldInsertAfterCurrent) {
      return;
    }

    nextItems.push({
      element_bid: '',
      parent_element_bid: anchorElementBid,
      type: ChatContentItemType.ASK,
      content: '',
      isAskExpanded: !mobileStyle,
      ask_list: storedAskList as ChatContentItem[],
      readonly: false,
      customRenderBar: () => null,
      user_input: '',
    });
    insertedAskAnchorSet.add(anchorElementBid);
  });

  return nextItems;
};

const getFirstHistoryTextContentItem = (items: ChatContentItem[]) =>
  items.find(
    item =>
      item.isHistory === true &&
      item.type === ChatContentItemType.CONTENT &&
      item.element_type === ELEMENT_TYPE.TEXT,
  );

const hasItemAudio = (item?: ChatContentItem) =>
  Boolean(item?.audio_url?.trim() || item?.audioUrl?.trim());

const shouldBlockListenModeForLegacyHistory = (items: ChatContentItem[]) => {
  const firstTextContentItem = getFirstHistoryTextContentItem(items);

  if (!firstTextContentItem) {
    return false;
  }

  return !hasItemAudio(firstTextContentItem);
};

export const NewChatComponents = ({
  className,
  lessonUpdate,
  onGoChapter,
  chapterId,
  lessonId,
  lessonTitle = '',
  lessonStatus = '',
  onPurchased,
  chapterUpdate,
  updateSelectedLesson,
  getNextLessonId,
  previewMode = false,
  isNavOpen = false,
  onListenPlayerVisibilityChange,
  onListenMobileViewModeChange,
  showGenerateBtn = false,
}: NewChatComponentsProps) => {
  const { trackEvent, trackTrailProgress } = useTracking();
  const { t } = useTranslation();
  const confirmButtonText = t('module.renderUi.core.confirm');
  const copyButtonText = t('module.renderUi.core.copyCode');
  const copiedButtonText = t('module.renderUi.core.copied');
  const askButtonMarkup = useMemo(
    () =>
      `<custom-button-after-content><img src="${AskIcon.src}" alt="ask" width="14" height="14" /><span>${t('module.chat.ask')}</span></custom-button-after-content>`,
    [t],
  );
  const listenModeUpgradeDialogTitle = t(
    'module.chat.listenModeUpgradeDialogTitle',
  );
  const listenModeUpgradeDialogDescription = t(
    'module.chat.listenModeUpgradeDialogDescription',
  );
  const listenModeUpgradeDialogRedo = t(
    'module.chat.listenModeUpgradeDialogRedo',
  );
  const listenModeUpgradeDialogReadLegacy = t(
    'module.chat.listenModeUpgradeDialogReadLegacy',
  );
  const chatBoxBottomRef = useRef<HTMLDivElement | null>(null);
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('module.chat.outputInProgress'),
    });
  }, [t]);

  const { courseId: shifuBid } = useEnvStore.getState();
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
  const [isAtBottom, setIsAtBottom] = useState(false);
  const listenTtsToastShownRef = useRef(false);
  const listenFeedbackReadyTimerRef = useRef<number | null>(null);
  const [listenPlaybackState, setListenPlaybackState] = useState({
    isAudioPlaying: false,
    isAudioSequenceActive: false,
  });
  const [isListenFeedbackReady, setIsListenFeedbackReady] = useState(false);
  const [showListenModeUpgradeDialog, setShowListenModeUpgradeDialog] =
    useState(false);

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

  const checkScroll = useCallback(() => {
    requestAnimationFrame(() => {
      const containers: Array<HTMLElement | Document> = [];

      if (chatRef.current) {
        containers.push(chatRef.current);
        if (chatRef.current.parentElement) {
          containers.push(chatRef.current.parentElement);
        }
      }

      if (mobileStyle) {
        containers.push(document);
      }

      const shouldShow = containers.some(container => !isNearBottom(container));
      setIsAtBottom(!shouldShow);
      setShowScrollDown(shouldShow);
    });
  }, [isNearBottom, mobileStyle]);

  const {
    openPayModal,
    payModalResult,
    resetChapter,
    resetedLessonId,
    resettingLessonId,
  } = useCourseStore(
    useShallow(state => ({
      openPayModal: state.openPayModal,
      payModalResult: state.payModalResult,
      resetChapter: state.resetChapter,
      resetedLessonId: state.resetedLessonId,
      resettingLessonId: state.resettingLessonId,
    })),
  );
  const shouldShowResetLoading =
    mobileStyle &&
    (resettingLessonId === lessonId || resetedLessonId === lessonId);
  const { learningMode, showLearningModeToggle, updateLearningMode } =
    useSystemStore(
      useShallow(state => ({
        learningMode: state.learningMode,
        showLearningModeToggle: state.showLearningModeToggle,
        updateLearningMode: state.updateLearningMode,
      })),
    );
  const isListenMode = learningMode === 'listen';
  const previousLearningModeRef = useRef(learningMode);
  const lastReadModeItemsRef = useRef<ChatContentItem[]>([]);
  const pendingListenAfterResetLessonIdRef = useRef<string | null>(null);
  const listenModeRestoreReadyRef = useRef(false);
  const courseTtsEnabled = useCourseStore(state => state.courseTtsEnabled);
  const isListenModeAvailable = courseTtsEnabled !== false;
  const isListenModeActive = getIsListenModeActive({
    learningMode,
    courseTtsEnabled,
  });
  // Normalize lesson scope for downstream APIs and stores that require a string key.
  const resolvedLessonId = lessonId || '';
  const isListenModeResetting =
    Boolean(resolvedLessonId) && resettingLessonId === resolvedLessonId;
  const promptContextKey = `${resolvedLessonId}:${isListenModeActive ? 'listen' : 'read'}`;
  const [settledPromptContextKey, setSettledPromptContextKey] =
    useState(promptContextKey);
  const shouldShowAudioAction = previewMode || isListenModeActive;
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  const isListenPlaybackBusy =
    listenPlaybackState.isAudioPlaying ||
    listenPlaybackState.isAudioSequenceActive;
  const isPromptContextSettled = settledPromptContextKey === promptContextKey;
  const ensureLessonScope = useAskStateStore(state => state.ensureLessonScope);
  const hydrateAskListMap = useAskStateStore(state => state.hydrateAskListMap);
  const lessonScopeKey = useAskStateStore(state => state.lessonScopeKey);
  const storedAskListByAnchorElementBid = useAskStateStore(
    state => state.askListByAnchorElementBid,
  );

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
    currentStreamingElementBid,
    onSend,
    onRefresh,
    toggleAskExpanded,
    reGenerateConfirm,
    requestAudioForBlock,
    lessonFeedbackPopup,
  } = useChatLogicHook({
    onGoChapter,
    shifuBid,
    outlineBid: resolvedLessonId,
    lessonId: resolvedLessonId,
    chapterId,
    previewMode,
    isListenMode: isListenModeActive,
    trackEvent,
    chatBoxBottomRef,
    trackTrailProgress,
    lessonUpdate,
    chapterUpdate,
    updateSelectedLesson,
    getNextLessonId,
    scrollToLesson,
    listenRequestEnabled: showLearningModeToggle,
    shouldPromptLessonFeedback:
      isPromptContextSettled &&
      (isListenModeActive ? isListenFeedbackReady : isAtBottom),
    // scrollToBottom,
    showOutputInProgressToast,
    onPayModalOpen,
  });

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
      buildReadModeItemsWithAskState({
        items: items.filter(item => item.type !== ChatContentItemType.ERROR),
        askListByAnchorElementBid: scopedAskListByAnchorElementBid,
        mobileStyle,
      }),
    [items, mobileStyle, scopedAskListByAnchorElementBid],
  );

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
    setIsAtBottom(false);
    setShowScrollDown(false);
  }, [isListenModeActive, lessonId]);

  useEffect(() => {
    if (learningMode !== 'read') {
      return;
    }

    lastReadModeItemsRef.current = items;
  }, [items, learningMode]);

  useEffect(() => {
    const previousLearningMode = previousLearningModeRef.current;
    previousLearningModeRef.current = learningMode;

    if (previousLearningMode !== 'read' || learningMode !== 'listen') {
      return;
    }

    const sourceItems = lastReadModeItemsRef.current.length
      ? lastReadModeItemsRef.current
      : items;

    if (!shouldBlockListenModeForLegacyHistory(sourceItems)) {
      return;
    }

    setShowListenModeUpgradeDialog(true);
    updateLearningMode('read');
  }, [items, learningMode, updateLearningMode]);

  useEffect(() => {
    const pendingLessonId = pendingListenAfterResetLessonIdRef.current;

    if (!pendingLessonId || pendingLessonId !== resolvedLessonId) {
      return;
    }

    if (resetedLessonId === resolvedLessonId) {
      listenModeRestoreReadyRef.current = true;
      return;
    }

    if (
      !listenModeRestoreReadyRef.current ||
      isLoading ||
      resettingLessonId === resolvedLessonId
    ) {
      return;
    }

    pendingListenAfterResetLessonIdRef.current = null;
    listenModeRestoreReadyRef.current = false;
    updateLearningMode('listen');
  }, [
    isLoading,
    resetedLessonId,
    resettingLessonId,
    resolvedLessonId,
    updateLearningMode,
  ]);

  useEffect(() => {
    setIsListenFeedbackReady(false);
    setSettledPromptContextKey(promptContextKey);
  }, [promptContextKey]);

  useEffect(() => {
    if (listenFeedbackReadyTimerRef.current !== null) {
      window.clearTimeout(listenFeedbackReadyTimerRef.current);
      listenFeedbackReadyTimerRef.current = null;
    }

    if (!isListenModeActive) {
      setIsListenFeedbackReady(true);
      return;
    }

    if (isLoading || isListenPlaybackBusy) {
      setIsListenFeedbackReady(false);
      return;
    }

    listenFeedbackReadyTimerRef.current = window.setTimeout(() => {
      setIsListenFeedbackReady(true);
      listenFeedbackReadyTimerRef.current = null;
    }, 1200);

    return () => {
      if (listenFeedbackReadyTimerRef.current !== null) {
        window.clearTimeout(listenFeedbackReadyTimerRef.current);
        listenFeedbackReadyTimerRef.current = null;
      }
    };
  }, [isListenModeActive, isLoading, isListenPlaybackBusy, lessonId]);

  const listenModeItems = useMemo(() => {
    if (!isListenModeActive || !mobileStyle) {
      return items;
    }
    let hasChanges = false;
    const nextItems = items.map(item => {
      if (item.type !== ChatContentItemType.CONTENT) {
        return item;
      }
      const sanitizedContent = syncCustomButtonAfterContent({
        content: item.content,
        buttonMarkup: askButtonMarkup,
        shouldShowButton: false,
      });
      if (sanitizedContent === item.content) {
        return item;
      }
      hasChanges = true;
      return {
        ...item,
        content: sanitizedContent ?? '',
      };
    });
    return hasChanges ? nextItems : items;
  }, [askButtonMarkup, isListenModeActive, items, mobileStyle]);

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
    if (!autoPlayAudio || previewMode) {
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
  }, [autoPlayAudio, currentPlayingBlockBid, items, previewMode]);

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

  const handleReadLegacyMode = useCallback(() => {
    if (isListenModeResetting) {
      return;
    }

    stopActiveLessonStream(resolvedLessonId);
    pendingListenAfterResetLessonIdRef.current = null;
    listenModeRestoreReadyRef.current = false;
    updateLearningMode('read');
    setShowListenModeUpgradeDialog(false);
  }, [isListenModeResetting, resolvedLessonId, updateLearningMode]);

  const handleResetChapterForListenMode = useSingleFlight(async () => {
    if (!resolvedLessonId) {
      return;
    }

    stopActiveLessonStream(resolvedLessonId);
    pendingListenAfterResetLessonIdRef.current = resolvedLessonId || null;
    listenModeRestoreReadyRef.current = false;
    updateLearningMode('read');
    await resetChapter(resolvedLessonId);
    setShowListenModeUpgradeDialog(false);
  });

  const handleListenModeUpgradeDialogOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        handleReadLegacyMode();
      }
    },
    [handleReadLegacyMode],
  );

  useEffect(() => {
    const container = chatRef.current;
    const parentContainer = container?.parentElement;
    const listeners: Array<{ element: EventTarget; handler: () => void }> = [];

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

    if (mobileStyle) {
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
  }, [checkScroll, isListenModeActive, items, mobileStyle]);

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
            submitLabel={confirmButtonText}
            clearLabel={t('module.chat.lessonFeedbackClearInput')}
            readonly={lessonFeedbackPopup.readonly}
            onSubmit={lessonFeedbackPopup.onSubmit}
          />
        </div>
      </div>
    ) : null;

  return (
    <div
      className={containerClassName}
      style={{ position: 'relative', overflow: 'hidden', padding: 0 }}
    >
      {isListenMode ? (
        isListenModeAvailable ? (
          <ListenModeSlideRenderer
            items={listenModeItems}
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
            isOutputInProgress={isOutputInProgress}
            onMobileViewModeChange={onListenMobileViewModeChange}
            onSend={memoizedOnSend}
            onPlayerVisibilityChange={onListenPlayerVisibilityChange}
            onPlaybackStateChange={setListenPlaybackState}
          />
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
          className={containerClassName}
          ref={chatRef}
          style={{ width: '100%', height: '100%', overflowY: 'auto' }}
        >
          <div>
            {shouldShowResetLoading ? (
              <div
                style={{
                  margin: '0 auto',
                  maxWidth: '1000px',
                  padding: '24px 20px 0',
                }}
              >
                <LoadingBar />
              </div>
            ) : isLoading ? (
              <></>
            ) : (
              readModeItems.map((item, idx) => {
                const isLongPressed = longPressedBlockBid === item.element_bid;
                const baseKey = item.element_bid || `${item.type}-${idx}`;
                const parentKey = item.parent_element_bid || baseKey;
                if (item.type === ChatContentItemType.ASK) {
                  return (
                    <div
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
                        shifu_bid={shifuBid}
                        outline_bid={resolvedLessonId}
                        preview_mode={previewMode}
                        element_bid={item.parent_element_bid || ''}
                        isOutputInProgress={isOutputInProgress}
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
                    parentContentItem?.type === ChatContentItemType.INTERACTION;
                  const shouldRenderMobileAskAction =
                    mobileStyle && isInteractionFollowUp;

                  if (mobileStyle && !shouldRenderMobileAskAction) {
                    return null;
                  }

                  return (
                    <div
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
                                  ? () => requestAudioForBlock(parentElementBid)
                                  : undefined
                              }
                              autoPlay={shouldAutoPlayElement}
                              onPlayStateChange={isPlaying =>
                                handleAudioPlayStateChange(
                                  parentElementBid,
                                  isPlaying,
                                )
                              }
                              onEnded={() => handleAudioEnded(parentElementBid)}
                              className='interaction-icon-btn'
                              size={16}
                            />
                          ) : null
                        }
                      />
                    </div>
                  );
                }

                return (
                  <div
                    key={`content-${baseKey}`}
                    style={{
                      position: 'relative',
                      margin:
                        !idx || item.type === ChatContentItemType.INTERACTION
                          ? '0 auto'
                          : '40px auto 0 auto',
                      maxWidth: mobileStyle ? '100%' : '1000px',
                      padding: '0 20px',
                    }}
                  >
                    {isLongPressed && mobileStyle && (
                      <div className='long-press-overlay' />
                    )}
                    <ContentBlock
                      item={item}
                      mobileStyle={mobileStyle}
                      blockBid={item.element_bid}
                      confirmButtonText={confirmButtonText}
                      copyButtonText={copyButtonText}
                      copiedButtonText={copiedButtonText}
                      onClickCustomButtonAfterContent={handleClickAskButton}
                      onSend={memoizedOnSend}
                      onLongPress={handleLongPress}
                      autoPlayAudio={
                        autoPlayTargetBlockBid === item.element_bid
                      }
                      showAudioAction={shouldShowAudioAction}
                      onAudioPlayStateChange={handleAudioPlayStateChange}
                      onAudioEnded={handleAudioEnded}
                    />
                  </div>
                );
              })
            )}
            <div
              ref={chatBoxBottomRef}
              id='chat-box-bottom'
            ></div>
          </div>
        </div>
      )}
      {!isListenMode &&
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
      {lessonFeedbackPopupContent
        ? listenFullscreenPortalTarget
          ? createPortal(
              lessonFeedbackPopupContent,
              listenFullscreenPortalTarget,
            )
          : lessonFeedbackPopupContent
        : null}
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
      <Dialog
        open={showListenModeUpgradeDialog}
        onOpenChange={handleListenModeUpgradeDialogOpenChange}
      >
        <DialogContent
          className='sm:max-w-md'
          showClose={!isListenModeResetting}
          onEscapeKeyDown={event => {
            if (isListenModeResetting) {
              event.preventDefault();
            }
          }}
          onPointerDownOutside={event => {
            if (isListenModeResetting) {
              event.preventDefault();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>{listenModeUpgradeDialogTitle}</DialogTitle>
            <DialogDescription>
              {listenModeUpgradeDialogDescription}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className='flex gap-2 sm:gap-2'>
            <button
              type='button'
              onClick={() => {
                void handleResetChapterForListenMode();
              }}
              disabled={isListenModeResetting}
              className='cursor-pointer px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-lighter disabled:cursor-not-allowed disabled:bg-primary/60'
            >
              {isListenModeResetting ? (
                <Loader2 className='mr-2 inline h-4 w-4 animate-spin' />
              ) : null}
              {listenModeUpgradeDialogRedo}
            </button>
            <button
              type='button'
              onClick={handleReadLegacyMode}
              disabled={isListenModeResetting}
              className='cursor-pointer px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:bg-gray-100 disabled:text-gray-400'
            >
              {listenModeUpgradeDialogReadLegacy}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

NewChatComponents.displayName = 'NewChatComponents';

export default memo(NewChatComponents);

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import Reveal, { Options } from 'reveal.js';
import {
  splitContentSegments,
  type RenderSegment,
} from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import type { AudioPlayerHandle } from '@/components/audio/AudioPlayer';
import { type AudioSegment } from '@/c-utils/audio-utils';
import { LESSON_FEEDBACK_INTERACTION_MARKER } from '@/c-api/studyV2';
import {
  buildSlidePageMapping,
  resolveListenModeTtsReadyElementBids,
  normalizeAudioTracks,
  sortSegmentsByIndex,
} from './listenModeUtils';

export type AudioInteractionItem = ChatContentItem & {
  page: number;
  sequenceKind: 'audio' | 'interaction';
  audioPosition?: number;
  listenSlideId?: string;
  audioSegments?: AudioSegment[];
};

export type ListenSlideItem = {
  item: ChatContentItem;
  segments: RenderSegment[];
};

export const LISTEN_AUDIO_BID_DELIMITER = '::listen-audio-pos::';
const AUDIO_END_TRANSITION_DEDUP_WINDOW_MS = 1200;

export const buildListenAudioSequenceBid = (
  elementBid: string,
  position: number,
) => `${elementBid}${LISTEN_AUDIO_BID_DELIMITER}${position}`;

export const resolveListenAudioSourceBid = (bid: string | null) => {
  if (!bid) {
    return null;
  }
  const hit = bid.indexOf(LISTEN_AUDIO_BID_DELIMITER);
  if (hit < 0) {
    return bid;
  }
  return bid.slice(0, hit) || null;
};

export const isLessonFeedbackInteractionItem = (
  item?: ChatContentItem | null,
) =>
  Boolean(
    item?.type === ChatContentItemType.INTERACTION &&
    item.content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER),
  );

export const useListenContentData = (items: ChatContentItem[]) => {
  const orderedContentElementBids = useMemo(() => {
    const seen = new Set<string>();
    const bids: string[] = [];
    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      const bid = item.element_bid;
      if (!bid || bid === 'loading') {
        continue;
      }
      if (seen.has(bid)) {
        continue;
      }
      seen.add(bid);
      bids.push(bid);
    }
    return bids;
  }, [items]);

  const { slideItems, interactionByPage, audioAndInteractionList } =
    useMemo(() => {
      let pageCursor = 0;
      const mapping = new Map<number, ChatContentItem>();
      const nextSlideItems: ListenSlideItem[] = [];
      const nextAudioAndInteractionList: AudioInteractionItem[] = [];

      items.forEach(item => {
        const segments =
          item.type === ChatContentItemType.CONTENT && !!item.content
            ? splitContentSegments(item.content || '', true)
            : [];
        const slideSegments = segments.filter(
          segment => segment.type === 'markdown' || segment.type === 'sandbox',
        );
        const fallbackPage = Math.max(pageCursor - 1, 0);
        const interactionPage = fallbackPage;
        const pageIndices = slideSegments.map(
          (_segment, index) => pageCursor + index,
        );

        if (item.type === ChatContentItemType.INTERACTION) {
          mapping.set(interactionPage, item);
          nextAudioAndInteractionList.push({
            ...item,
            page: interactionPage,
            sequenceKind: 'interaction',
          });
        }

        if (item.type === ChatContentItemType.CONTENT) {
          const tracks = normalizeAudioTracks(item);
          const { pageBySlideId, resolvePageByPosition } =
            buildSlidePageMapping(item, pageIndices, fallbackPage);

          if (
            tracks.length === 0 &&
            item.element_bid &&
            item.element_bid !== 'loading'
          ) {
            const defaultPosition = 0;
            const sequenceBid = buildListenAudioSequenceBid(
              item.element_bid,
              defaultPosition,
            );
            nextAudioAndInteractionList.push({
              ...item,
              element_bid: sequenceBid,
              page: resolvePageByPosition(defaultPosition),
              sequenceKind: 'audio',
              audioPosition: defaultPosition,
              listenSlideId: undefined,
              audioUrl: undefined,
              audioDurationMs: undefined,
              isAudioStreaming: Boolean(item.isAudioStreaming),
              audioSegments: [],
              audioTracks: [],
            });
          }

          tracks.forEach(track => {
            const position = Number(track.position ?? 0);
            const page =
              (track.slideId ? pageBySlideId.get(track.slideId) : undefined) ??
              resolvePageByPosition(position);
            const sequenceBid = buildListenAudioSequenceBid(
              item.element_bid,
              position,
            );

            nextAudioAndInteractionList.push({
              ...item,
              element_bid: sequenceBid,
              page,
              sequenceKind: 'audio',
              audioPosition: position,
              listenSlideId: track.slideId,
              audioUrl: track.audioUrl,
              audioDurationMs: track.durationMs,
              isAudioStreaming: Boolean(track.isAudioStreaming),
              audioSegments: sortSegmentsByIndex(track.audioSegments ?? []),
              audioTracks: [track],
            });
          });
        }

        if (slideSegments.length > 0) {
          nextSlideItems.push({
            item,
            segments: slideSegments,
          });
        }

        pageCursor += slideSegments.length;
      });
      // console.log('items', items);
      return {
        slideItems: nextSlideItems,
        interactionByPage: mapping,
        audioAndInteractionList: nextAudioAndInteractionList,
      };
    }, [items]);

  const { lastInteractionBid, lastItemIsInteraction } = useMemo(() => {
    let latestInteractionBid: string | null = null;
    for (let i = audioAndInteractionList.length - 1; i >= 0; i -= 1) {
      if (audioAndInteractionList[i].type === ChatContentItemType.INTERACTION) {
        latestInteractionBid = audioAndInteractionList[i].element_bid;
        break;
      }
    }
    const lastItem =
      audioAndInteractionList[audioAndInteractionList.length - 1];
    return {
      lastInteractionBid: latestInteractionBid,
      lastItemIsInteraction: lastItem?.type === ChatContentItemType.INTERACTION,
    };
  }, [audioAndInteractionList]);

  const contentByBid = useMemo(() => {
    const mapping = new Map<string, ChatContentItem>();
    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      const bid = item.element_bid;
      if (!bid || bid === 'loading') {
        continue;
      }
      mapping.set(bid, item);
    }
    return mapping;
  }, [items]);

  const audioContentByBid = useMemo(() => {
    const mapping = new Map<string, ChatContentItem>();
    for (const item of audioAndInteractionList) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      const bid = item.element_bid;
      if (!bid || bid === 'loading') {
        continue;
      }
      mapping.set(bid, item);
    }
    return mapping;
  }, [audioAndInteractionList]);

  const ttsReadyElementBids = useMemo(() => {
    return resolveListenModeTtsReadyElementBids(items);
  }, [items]);

  const firstContentItem = useMemo(() => {
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (
        item.type === ChatContentItemType.CONTENT &&
        item.element_bid &&
        item.element_bid !== 'loading'
      ) {
        return item;
      }
    }
    return null;
  }, [items]);

  return {
    orderedContentElementBids,
    slideItems,
    interactionByPage,
    audioAndInteractionList,
    contentByBid,
    audioContentByBid,
    ttsReadyElementBids,
    lastInteractionBid,
    lastItemIsInteraction,
    firstContentItem,
  };
};

interface UseListenPptParams {
  chatRef: React.RefObject<HTMLDivElement>;
  deckRef: React.MutableRefObject<Reveal.Api | null>;
  currentPptPageRef: React.MutableRefObject<number>;
  activeElementBidRef: React.MutableRefObject<string | null>;
  pendingAutoNextRef: React.MutableRefObject<boolean>;
  slideItems: ListenSlideItem[];
  interactionByPage: Map<number, ChatContentItem>;
  sectionTitle?: string;
  isLoading: boolean;
  isAudioPlaying: boolean;
  isSlideNavigationLocked: boolean;
  allowAutoPlayback: boolean;
  activeContentItem?: ChatContentItem;
  shouldRenderEmptyPpt: boolean;
  onResetSequence?: () => void;
  getNextContentBid: (currentBid: string | null) => string | null;
  goToBlock: (blockBid: string) => boolean;
  resolveContentBid: (blockBid: string | null) => string | null;
}

export const useListenPpt = ({
  chatRef,
  deckRef,
  currentPptPageRef,
  activeElementBidRef,
  pendingAutoNextRef,
  slideItems,
  interactionByPage,
  sectionTitle,
  isLoading,
  isAudioPlaying,
  isSlideNavigationLocked,
  allowAutoPlayback,
  activeContentItem,
  shouldRenderEmptyPpt,
  onResetSequence,
  getNextContentBid,
  goToBlock,
  resolveContentBid,
}: UseListenPptParams) => {
  const prevSlidesLengthRef = useRef(0);
  const shouldSlideToFirstRef = useRef(false);
  const hasAutoSlidToLatestRef = useRef(false);
  const prevFirstSlideBidRef = useRef<string | null>(null);
  const prevSectionTitleRef = useRef<string | null>(null);
  const [currentInteraction, setCurrentInteraction] =
    useState<ChatContentItem | null>(null);
  const [isPrevDisabled, setIsPrevDisabled] = useState(true);
  const [isNextDisabled, setIsNextDisabled] = useState(true);

  const firstSlideBid = useMemo(
    () => slideItems[0]?.item.element_bid ?? null,
    [slideItems],
  );

  useLayoutEffect(() => {
    if (!firstSlideBid) {
      prevFirstSlideBidRef.current = null;
      return;
    }
    if (!prevFirstSlideBidRef.current) {
      shouldSlideToFirstRef.current = true;
      // Avoid resetting sequence while audio is actively playing.
      if (allowAutoPlayback && !isAudioPlaying) {
        onResetSequence?.();
      }
    } else if (prevFirstSlideBidRef.current !== firstSlideBid) {
      shouldSlideToFirstRef.current = true;
      // Avoid interrupting the current playing sequence on stream append.
      if (allowAutoPlayback && !isAudioPlaying) {
        onResetSequence?.();
      }
    }
    prevFirstSlideBidRef.current = firstSlideBid;
  }, [allowAutoPlayback, firstSlideBid, isAudioPlaying, onResetSequence]);

  useLayoutEffect(() => {
    if (!sectionTitle) {
      prevSectionTitleRef.current = null;
      return;
    }
    if (
      prevSectionTitleRef.current &&
      prevSectionTitleRef.current !== sectionTitle
    ) {
      shouldSlideToFirstRef.current = true;
      // Keep current audio session stable when section title updates mid-playback.
      if (allowAutoPlayback && !isAudioPlaying) {
        onResetSequence?.();
      }
    }
    prevSectionTitleRef.current = sectionTitle;
  }, [allowAutoPlayback, sectionTitle, isAudioPlaying, onResetSequence]);

  const syncInteractionForCurrentPage = useCallback(
    (pageIndex?: number) => {
      const targetPage =
        typeof pageIndex === 'number' ? pageIndex : currentPptPageRef.current;
      setCurrentInteraction(interactionByPage.get(targetPage) ?? null);
    },
    [interactionByPage, currentPptPageRef],
  );

  const syncPptPageFromDeck = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    const nextIndex = deck.getIndices()?.h ?? 0;
    if (currentPptPageRef.current === nextIndex) {
      return;
    }
    currentPptPageRef.current = nextIndex;
    syncInteractionForCurrentPage(nextIndex);
  }, [currentPptPageRef, deckRef, syncInteractionForCurrentPage]);

  useEffect(() => {
    syncInteractionForCurrentPage();
  }, [syncInteractionForCurrentPage]);

  const getBlockBidFromSlide = useCallback((slide: HTMLElement | null) => {
    if (!slide) {
      return null;
    }
    return slide.getAttribute('data-element-bid') || null;
  }, []);

  const syncActiveBlockFromDeck = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    const slide = deck.getCurrentSlide?.() as HTMLElement | undefined;
    const nextBid = getBlockBidFromSlide(slide ?? null);
    if (!nextBid || nextBid === activeElementBidRef.current) {
      return;
    }
    if (shouldRenderEmptyPpt) {
      if (!activeElementBidRef.current?.startsWith('empty-ppt-')) {
        activeElementBidRef.current = nextBid;
      }
      return;
    }
    activeElementBidRef.current = nextBid;
  }, [
    activeElementBidRef,
    deckRef,
    getBlockBidFromSlide,
    shouldRenderEmptyPpt,
  ]);

  const updateNavState = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      setIsPrevDisabled(true);
      setIsNextDisabled(true);
      return;
    }
    const totalSlides =
      typeof deck.getTotalSlides === 'function' ? deck.getTotalSlides() : 0;
    const indices = deck.getIndices?.();
    const currentIndex = indices?.h ?? 0;
    const isFirstSlide =
      typeof deck.isFirstSlide === 'function'
        ? deck.isFirstSlide()
        : totalSlides <= 1 || currentIndex <= 0;
    const isLastSlide =
      typeof deck.isLastSlide === 'function'
        ? deck.isLastSlide()
        : totalSlides <= 1 || currentIndex >= Math.max(totalSlides - 1, 0);
    setIsPrevDisabled(isFirstSlide);
    setIsNextDisabled(isLastSlide);
  }, [deckRef]);

  const goToNextBlock = useCallback(() => {
    const currentBid = resolveContentBid(activeElementBidRef.current);
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      return false;
    }
    return goToBlock(nextBid);
  }, [activeElementBidRef, getNextContentBid, goToBlock, resolveContentBid]);

  useEffect(() => {
    if (!chatRef.current || deckRef.current || isLoading) {
      return;
    }

    if (!slideItems.length) {
      return;
    }

    const slideNodes = chatRef.current.querySelectorAll('.slides > section');
    if (!slideNodes.length) {
      return;
    }

    const revealOptions: Options = {
      width: '100%',
      height: '100%',
      margin: 0,
      minScale: 1,
      maxScale: 1,
      transition: 'slide',
      slideNumber: false,
      progress: false,
      controls: false,
      hideInactiveCursor: false,
      center: false,
      disableLayout: true,
      view: null,
      scrollActivationWidth: 0,
      scrollProgress: false,
      scrollSnap: false,
    };

    deckRef.current = new Reveal(chatRef.current, revealOptions);

    deckRef.current.initialize().then(() => {
      syncActiveBlockFromDeck();
      syncPptPageFromDeck();
      updateNavState();
    });
  }, [
    chatRef,
    deckRef,
    slideItems.length,
    isLoading,
    syncActiveBlockFromDeck,
    syncPptPageFromDeck,
    updateNavState,
  ]);

  useEffect(() => {
    if (!slideItems.length && deckRef.current) {
      try {
        console.log('销毁reveal实例 (no content)');
        deckRef.current?.destroy();
      } catch (e) {
        console.warn('Reveal.js destroy 調用失敗。');
      } finally {
        deckRef.current = null;
        hasAutoSlidToLatestRef.current = false;
        setIsPrevDisabled(true);
        setIsNextDisabled(true);
      }
    }
  }, [deckRef, slideItems.length]);

  useEffect(() => {
    return () => {
      if (!deckRef.current) {
        return;
      }
      try {
        deckRef.current?.destroy();
      } catch (e) {
        console.warn('Reveal.js destroy 調用失敗。');
      } finally {
        deckRef.current = null;
        hasAutoSlidToLatestRef.current = false;
        prevSlidesLengthRef.current = 0;
      }
    };
  }, [deckRef]);

  useEffect(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }

    const handleSlideChanged = () => {
      syncActiveBlockFromDeck();
      syncPptPageFromDeck();
      updateNavState();
    };

    deck.on('slidechanged', handleSlideChanged as unknown as EventListener);
    deck.on('ready', handleSlideChanged as unknown as EventListener);

    return () => {
      deck.off('slidechanged', handleSlideChanged as unknown as EventListener);
      deck.off('ready', handleSlideChanged as unknown as EventListener);
    };
  }, [deckRef, syncActiveBlockFromDeck, syncPptPageFromDeck, updateNavState]);

  useEffect(() => {
    if (!deckRef.current || isLoading) {
      return;
    }
    if (typeof deckRef.current.sync !== 'function') {
      return;
    }
    const slides =
      typeof deckRef.current.getSlides === 'function'
        ? deckRef.current.getSlides()
        : Array.from(
            chatRef.current?.querySelectorAll('.slides > section') || [],
          );
    if (!slides.length) {
      return;
    }
    try {
      deckRef.current.sync();
      deckRef.current.layout();
      const indices = deckRef.current.getIndices?.();
      const prevSlidesLength = prevSlidesLengthRef.current;
      const nextSlidesLength = slides.length;
      const lastIndex = Math.max(nextSlidesLength - 1, 0);
      const currentIndex = indices?.h ?? 0;
      const prevLastIndex = Math.max(prevSlidesLength - 1, 0);

      if (shouldSlideToFirstRef.current) {
        deckRef.current.slide(0);
        shouldSlideToFirstRef.current = false;
        hasAutoSlidToLatestRef.current = true;
        updateNavState();
        prevSlidesLengthRef.current = nextSlidesLength;
        return;
      }

      if (isSlideNavigationLocked) {
        prevSlidesLengthRef.current = nextSlidesLength;
        return;
      }

      if (!allowAutoPlayback) {
        shouldSlideToFirstRef.current = false;
        prevSlidesLengthRef.current = nextSlidesLength;
        updateNavState();
        return;
      }

      const shouldAutoFollowOnAppend =
        prevSlidesLength > 0 &&
        nextSlidesLength > prevSlidesLength &&
        currentIndex >= prevLastIndex;
      const shouldHoldForStreamingAudio =
        isAudioPlaying &&
        Boolean(
          activeContentItem?.audioTracks?.some(
            track =>
              Boolean(track.isAudioStreaming) ||
              Boolean(track.audioSegments && track.audioSegments.length > 0),
          ),
        );
      const resolvedActiveBid = resolveContentBid(
        activeContentItem?.element_bid ?? null,
      );
      const resolvedCurrentBid = resolveContentBid(activeElementBidRef.current);
      if (resolvedActiveBid && resolvedActiveBid !== resolvedCurrentBid) {
        const moved = goToBlock(resolvedActiveBid);
        if (moved) {
          pendingAutoNextRef.current = false;
          updateNavState();
          prevSlidesLengthRef.current = nextSlidesLength;
          return;
        }
      }

      if (pendingAutoNextRef.current) {
        const moved = goToNextBlock();
        pendingAutoNextRef.current = !moved;
      }

      if (shouldHoldForStreamingAudio) {
        prevSlidesLengthRef.current = nextSlidesLength;
        return;
      }

      if (isAudioPlaying && !shouldAutoFollowOnAppend) {
        prevSlidesLengthRef.current = nextSlidesLength;
        return;
      }

      const shouldFollowLatest =
        shouldAutoFollowOnAppend ||
        !hasAutoSlidToLatestRef.current ||
        currentIndex >= lastIndex;
      if (shouldFollowLatest) {
        deckRef.current.slide(lastIndex);
        hasAutoSlidToLatestRef.current = true;
      } else if (indices) {
        deckRef.current.slide(indices.h, indices.v, indices.f);
      }
      updateNavState();
      prevSlidesLengthRef.current = nextSlidesLength;
    } catch {
      // Ignore reveal sync errors
    }
  }, [
    slideItems,
    isAudioPlaying,
    isSlideNavigationLocked,
    allowAutoPlayback,
    isLoading,
    goToNextBlock,
    goToBlock,
    chatRef,
    updateNavState,
    activeContentItem?.element_bid,
    activeContentItem?.audioTracks,
    deckRef,
    pendingAutoNextRef,
    resolveContentBid,
  ]);

  const goPrev = useCallback(() => {
    const deck = deckRef.current;
    if (!deck || isPrevDisabled) {
      return null;
    }
    shouldSlideToFirstRef.current = false;
    hasAutoSlidToLatestRef.current = true;
    deck.prev();
    currentPptPageRef.current = deck.getIndices().h;
    syncInteractionForCurrentPage(currentPptPageRef.current);
    updateNavState();
    return currentPptPageRef.current;
  }, [
    deckRef,
    isPrevDisabled,
    currentPptPageRef,
    syncInteractionForCurrentPage,
    updateNavState,
  ]);

  const goNext = useCallback(() => {
    const deck = deckRef.current;
    if (!deck || isNextDisabled) {
      return null;
    }
    shouldSlideToFirstRef.current = false;
    hasAutoSlidToLatestRef.current = true;
    deck.next();
    currentPptPageRef.current = deck.getIndices().h;
    syncInteractionForCurrentPage(currentPptPageRef.current);
    updateNavState();
    return currentPptPageRef.current;
  }, [
    deckRef,
    isNextDisabled,
    currentPptPageRef,
    syncInteractionForCurrentPage,
    updateNavState,
  ]);

  return {
    currentInteraction,
    isPrevDisabled,
    isNextDisabled,
    goPrev,
    goNext,
  };
};

interface UseListenAudioSequenceParams {
  audioAndInteractionList: AudioInteractionItem[];
  deckRef: React.MutableRefObject<Reveal.Api | null>;
  currentPptPageRef: React.MutableRefObject<number>;
  activeElementBidRef: React.MutableRefObject<string | null>;
  pendingAutoNextRef: React.MutableRefObject<boolean>;
  shouldStartSequenceRef: React.MutableRefObject<boolean>;
  sequenceStartSignal: number;
  contentByBid: Map<string, ChatContentItem>;
  audioContentByBid: Map<string, ChatContentItem>;
  previewMode: boolean;
  shouldRenderEmptyPpt: boolean;
  getNextContentBid: (currentBid: string | null) => string | null;
  goToBlock: (blockBid: string) => boolean;
  resolveContentBid: (blockBid: string | null) => string | null;
  allowAutoPlayback: boolean;
  isAudioPlaying: boolean;
  setIsAudioPlaying: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useListenAudioSequence = ({
  audioAndInteractionList,
  deckRef,
  currentPptPageRef,
  activeElementBidRef,
  pendingAutoNextRef,
  shouldStartSequenceRef,
  sequenceStartSignal,
  contentByBid,
  audioContentByBid,
  previewMode,
  shouldRenderEmptyPpt,
  getNextContentBid,
  goToBlock,
  resolveContentBid,
  allowAutoPlayback,
  isAudioPlaying,
  setIsAudioPlaying,
}: UseListenAudioSequenceParams) => {
  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);
  const audioSequenceIndexRef = useRef(-1);
  const audioSequenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const audioSequenceListRef = useRef<AudioInteractionItem[]>([]);
  const prevAudioSequenceLengthRef = useRef(0);
  const [activeAudioBid, setActiveAudioBid] = useState<string | null>(null);
  const [sequenceInteraction, setSequenceInteraction] =
    useState<AudioInteractionItem | null>(null);
  const [isAudioSequenceActive, setIsAudioSequenceActive] = useState(false);
  const [audioSequenceToken, setAudioSequenceToken] = useState(0);
  const isSequencePausedRef = useRef(false);
  const isAudioSequenceActiveRef = useRef(false);
  const activeAudioBidRef = useRef<string | null>(null);
  const isAudioPlayingRef = useRef(isAudioPlaying);
  const recentHandledAudioEndedRef = useRef<{
    index: number;
    activeAudioBid: string | null;
    at: number;
  } | null>(null);
  const recentEndedAdvanceRef = useRef<{
    nextIndex: number;
    at: number;
  } | null>(null);

  const lastPlayedAudioBidRef = useRef<string | null>(null);

  useEffect(() => {
    isAudioSequenceActiveRef.current = isAudioSequenceActive;
  }, [isAudioSequenceActive]);

  useEffect(() => {
    activeAudioBidRef.current = activeAudioBid;
  }, [activeAudioBid]);

  useEffect(() => {
    isAudioPlayingRef.current = Boolean(isAudioPlaying);
  }, [isAudioPlaying]);

  useEffect(() => {
    audioSequenceListRef.current = audioAndInteractionList;
  }, [audioAndInteractionList]);

  const clearAudioSequenceTimer = useCallback(() => {
    if (audioSequenceTimerRef.current) {
      clearTimeout(audioSequenceTimerRef.current);
      audioSequenceTimerRef.current = null;
    }
  }, []);

  const shouldSkipAppendAutoPlayFromRecentEnded = useCallback(
    (targetIndex: number) => {
      const recentEndedAdvance = recentEndedAdvanceRef.current;
      if (!recentEndedAdvance) {
        return false;
      }
      const elapsed = Date.now() - recentEndedAdvance.at;
      if (elapsed > AUDIO_END_TRANSITION_DEDUP_WINDOW_MS) {
        recentEndedAdvanceRef.current = null;
        return false;
      }
      if (recentEndedAdvance.nextIndex !== targetIndex) {
        return false;
      }
      return true;
    },
    [],
  );

  const syncToSequencePage = useCallback(
    (page: number) => {
      if (page < 0) {
        return;
      }
      const deck = deckRef.current;
      if (!deck) {
        return;
      }
      const currentIndex = deck.getIndices?.().h ?? 0;
      if (currentIndex !== page) {
        deck.slide(page);
      }
    },
    [deckRef],
  );

  const resolveSequenceStartIndex = useCallback((page: number) => {
    const list = audioSequenceListRef.current;
    if (!list.length) {
      return -1;
    }
    const audioIndex = list.findIndex(
      item => item.page === page && item.type === ChatContentItemType.CONTENT,
    );
    if (audioIndex >= 0) {
      return audioIndex;
    }
    const pageIndex = list.findIndex(item => item.page === page);
    if (pageIndex >= 0) {
      return pageIndex;
    }
    const nextIndex = list.findIndex(item => item.page > page);
    return nextIndex;
  }, []);

  const playAudioSequenceFromIndex = useCallback(
    (index: number) => {
      // Prevent redundant calls for the same index if already active
      if (
        audioSequenceIndexRef.current === index &&
        isAudioSequenceActiveRef.current
      ) {
        return;
      }
      if (isSequencePausedRef.current) {
        return;
      }

      clearAudioSequenceTimer();
      const recentEndedAdvance = recentEndedAdvanceRef.current;
      if (
        recentEndedAdvance &&
        (Date.now() - recentEndedAdvance.at >
          AUDIO_END_TRANSITION_DEDUP_WINDOW_MS ||
          recentEndedAdvance.nextIndex !== index)
      ) {
        recentEndedAdvanceRef.current = null;
      }
      const list = audioSequenceListRef.current;
      const nextItem = list[index];

      if (!nextItem) {
        setSequenceInteraction(null);
        setActiveAudioBid(null);
        activeAudioBidRef.current = null;
        setIsAudioSequenceActive(false);
        isAudioSequenceActiveRef.current = false;
        return;
      }
      syncToSequencePage(nextItem.page);
      audioSequenceIndexRef.current = index;
      setIsAudioSequenceActive(true);
      isAudioSequenceActiveRef.current = true;
      if (nextItem.element_bid) {
        lastPlayedAudioBidRef.current = nextItem.element_bid;
      }

      if (nextItem.type === ChatContentItemType.INTERACTION) {
        setSequenceInteraction(nextItem);
        setActiveAudioBid(null);
        activeAudioBidRef.current = null;
        if (isLessonFeedbackInteractionItem(nextItem)) {
          // Keep feedback popup behavior, but do not block following CTA interactions
          // (next/login/pay) from being shown in listen mode.
          if (index < list.length - 1) {
            audioSequenceTimerRef.current = setTimeout(() => {
              playAudioSequenceFromIndex(index + 1);
            }, 0);
          }
          return;
        }
        if (index >= list.length - 1) {
          return;
        }
        audioSequenceTimerRef.current = setTimeout(() => {
          playAudioSequenceFromIndex(index + 1);
        }, 2000);
        return;
      }
      setSequenceInteraction(null);
      setActiveAudioBid(nextItem.element_bid);
      activeAudioBidRef.current = nextItem.element_bid;
      setAudioSequenceToken(prev => prev + 1);
    },
    [clearAudioSequenceTimer, syncToSequencePage],
  );

  useEffect(() => {
    const prevLength = prevAudioSequenceLengthRef.current;
    const nextLength = audioAndInteractionList.length;
    prevAudioSequenceLengthRef.current = nextLength;
    if (previewMode || !nextLength) {
      return;
    }
    if (!allowAutoPlayback) {
      return;
    }
    if (isSequencePausedRef.current) {
      return;
    }
    const isSequenceActive = isAudioSequenceActiveRef.current;
    const isAudioPlayingNow = isAudioPlayingRef.current;
    const currentIndex = audioSequenceIndexRef.current;

    if (
      isSequenceActive &&
      sequenceInteraction &&
      currentIndex >= 0 &&
      prevLength > 0 &&
      currentIndex === prevLength - 1 &&
      nextLength > prevLength
    ) {
      // Continue after the last interaction when new audio arrives.
      const targetIndex = currentIndex + 1;
      if (shouldSkipAppendAutoPlayFromRecentEnded(targetIndex)) {
        return;
      }
      playAudioSequenceFromIndex(targetIndex);
      return;
    }

    // Auto-play new content if it matches the current page (e.g. Retake, or streaming new content)
    if (nextLength > prevLength) {
      const newItemIndex = nextLength - 1;
      const newItem = audioAndInteractionList[newItemIndex];
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
      const newItemSourceBid = resolveContentBid(newItem?.element_bid ?? null);
      const lastPlayedSourceBid = resolveContentBid(
        lastPlayedAudioBidRef.current,
      );
      const shouldResumeLateAudioFromSameBlock =
        !isSequenceActive &&
        !isAudioPlayingNow &&
        Boolean(
          newItemSourceBid &&
          lastPlayedSourceBid &&
          newItemSourceBid === lastPlayedSourceBid,
        );

      if (newItem?.page === currentPage) {
        // If it's the first item ever (prevLength === 0), or if we are appending to the current page sequence
        // we should play it.
        // But if we are just appending a new item to the END of the list, we should only play it if
        // we are not currently playing something else (unless it's a replacement/retake of the same index).
        if (prevLength === 0) {
          // Initial load for this page
          // Check if we are recovering from a flash (list became empty then full again)
          const lastBid = lastPlayedAudioBidRef.current;
          const resumeIndex = lastBid
            ? audioAndInteractionList.findIndex(
                item => item.element_bid === lastBid,
              )
            : -1;

          if (resumeIndex >= 0) {
            // Resume playback from the last known block to maintain continuity
            playAudioSequenceFromIndex(resumeIndex);
          } else {
            const startIndex = resolveSequenceStartIndex(currentPage);
            if (startIndex >= 0) {
              playAudioSequenceFromIndex(startIndex);
            }
          }
        } else {
          // Appending new item
          // Guard against interruption: only block when audio is actively playing.
          // If sequence is idle at tail, allow continuing with appended item.
          const isSwitchingToDifferentItem = currentIndex !== newItemIndex;
          const isIdleAtTail =
            isSequenceActive &&
            !isAudioPlayingNow &&
            currentIndex >= 0 &&
            currentIndex === prevLength - 1 &&
            newItemIndex === nextLength - 1;
          const shouldBlockAutoSwitch =
            isAudioPlayingNow && isSwitchingToDifferentItem;

          if (shouldBlockAutoSwitch) {
            return;
          }
          if (
            !isSequenceActive ||
            audioSequenceIndexRef.current === newItemIndex ||
            isIdleAtTail
          ) {
            if (shouldSkipAppendAutoPlayFromRecentEnded(newItemIndex)) {
              return;
            }
            playAudioSequenceFromIndex(newItemIndex);
          }
        }
      } else if (shouldResumeLateAudioFromSameBlock) {
        if (shouldSkipAppendAutoPlayFromRecentEnded(newItemIndex)) {
          return;
        }
        playAudioSequenceFromIndex(newItemIndex);
      } else {
        // Keep silent for this high-frequency non-action branch.
      }
    }
  }, [
    audioAndInteractionList,
    playAudioSequenceFromIndex,
    previewMode,
    allowAutoPlayback,
    sequenceInteraction,
    deckRef,
    currentPptPageRef,
    resolveContentBid,
    resolveSequenceStartIndex,
    shouldSkipAppendAutoPlayFromRecentEnded,
  ]);

  const resetSequenceState = useCallback(() => {
    isSequencePausedRef.current = false;
    clearAudioSequenceTimer();
    audioPlayerRef.current?.pause({
      traceId: 'sequence-reset',
      keepAutoPlay: true,
    });
    audioSequenceIndexRef.current = -1;
    setSequenceInteraction(null);
    setActiveAudioBid(null);
    activeAudioBidRef.current = null;
    setIsAudioSequenceActive(false);
    isAudioSequenceActiveRef.current = false;
  }, [clearAudioSequenceTimer]);

  const startSequenceFromIndex = useCallback(
    (index: number) => {
      const listLength = audioSequenceListRef.current.length;
      if (!listLength) {
        return;
      }
      const maxIndex = Math.max(listLength - 1, 0);
      const nextIndex = Math.min(Math.max(index, 0), maxIndex);
      resetSequenceState();
      playAudioSequenceFromIndex(nextIndex);
    },
    [playAudioSequenceFromIndex, resetSequenceState],
  );

  const startSequenceFromPage = useCallback(
    (page: number) => {
      const startIndex = resolveSequenceStartIndex(page);
      if (startIndex < 0) {
        return;
      }
      startSequenceFromIndex(startIndex);
    },
    [resolveSequenceStartIndex, startSequenceFromIndex],
  );

  useEffect(() => {
    return () => {
      clearAudioSequenceTimer();
    };
  }, [clearAudioSequenceTimer]);

  useEffect(() => {
    if (audioAndInteractionList.length) {
      return;
    }
    clearAudioSequenceTimer();
    audioSequenceIndexRef.current = -1;
    setActiveAudioBid(null);
    activeAudioBidRef.current = null;
    setSequenceInteraction(null);
    setIsAudioSequenceActive(false);
    isAudioSequenceActiveRef.current = false;
  }, [audioAndInteractionList.length, clearAudioSequenceTimer]);

  useEffect(() => {
    if (!allowAutoPlayback) {
      return;
    }
    if (!shouldStartSequenceRef.current) {
      return;
    }
    if (!audioAndInteractionList.length) {
      return;
    }
    if (isSequencePausedRef.current) {
      isSequencePausedRef.current = false;
    }
    shouldStartSequenceRef.current = false;

    // Check if we can resume from the last played block (e.g. after a list flash/refresh)
    if (lastPlayedAudioBidRef.current) {
      const resumeIndex = audioAndInteractionList.findIndex(
        item => item.element_bid === lastPlayedAudioBidRef.current,
      );
      if (resumeIndex >= 0) {
        // We found the last played item, so we are likely just recovering from a refresh.
        // Resume from there instead of restarting.
        playAudioSequenceFromIndex(resumeIndex);
        return;
      }
    }

    // Otherwise, truly start from the beginning
    playAudioSequenceFromIndex(0);
  }, [
    audioAndInteractionList,
    sequenceStartSignal,
    playAudioSequenceFromIndex,
    shouldStartSequenceRef,
    allowAutoPlayback,
  ]);

  const activeSequenceElementBid = useMemo(() => {
    if (!activeAudioBid) {
      return null;
    }
    return activeAudioBid;
  }, [activeAudioBid]);

  const activeAudioElementBid = useMemo(() => {
    if (!activeAudioBid) {
      return null;
    }
    return resolveContentBid(activeAudioBid);
  }, [activeAudioBid, resolveContentBid]);

  const activeContentItem = useMemo(() => {
    if (!activeAudioElementBid) {
      return undefined;
    }
    return (
      audioContentByBid.get(activeAudioElementBid) ??
      contentByBid.get(activeAudioElementBid)
    );
  }, [activeAudioElementBid, audioContentByBid, contentByBid]);

  const tryAdvanceToNextBlock = useCallback(() => {
    const currentBid = resolveContentBid(activeElementBidRef.current);
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      return false;
    }

    const moved = goToBlock(nextBid);
    if (moved) {
      return true;
    }

    if (shouldRenderEmptyPpt) {
      activeElementBidRef.current = `empty-ppt-${nextBid}`;
      return true;
    }

    pendingAutoNextRef.current = true;
    return true;
  }, [
    activeElementBidRef,
    getNextContentBid,
    goToBlock,
    pendingAutoNextRef,
    resolveContentBid,
    shouldRenderEmptyPpt,
  ]);

  const handleAudioEnded = useCallback(() => {
    if (isSequencePausedRef.current) {
      return;
    }
    const now = Date.now();
    const currentIndex = audioSequenceIndexRef.current;
    const currentActiveAudioBid = activeAudioBidRef.current;
    const recentEnded = recentHandledAudioEndedRef.current;
    if (
      recentEnded &&
      recentEnded.index === currentIndex &&
      recentEnded.activeAudioBid === currentActiveAudioBid &&
      now - recentEnded.at < AUDIO_END_TRANSITION_DEDUP_WINDOW_MS
    ) {
      return;
    }
    recentHandledAudioEndedRef.current = {
      index: currentIndex,
      activeAudioBid: currentActiveAudioBid,
      at: now,
    };
    const list = audioSequenceListRef.current;
    if (list.length) {
      const nextIndex = audioSequenceIndexRef.current + 1;
      if (nextIndex >= list.length) {
        setActiveAudioBid(null);
        activeAudioBidRef.current = null;
        setIsAudioSequenceActive(false);
        isAudioSequenceActiveRef.current = false;
        recentEndedAdvanceRef.current = null;
        void tryAdvanceToNextBlock();
        return;
      }
      recentEndedAdvanceRef.current = {
        nextIndex,
        at: now,
      };
      playAudioSequenceFromIndex(nextIndex);
      return;
    }
    recentEndedAdvanceRef.current = null;
    void tryAdvanceToNextBlock();
  }, [playAudioSequenceFromIndex, tryAdvanceToNextBlock]);

  const handlePlay = useCallback(() => {
    if (previewMode) {
      return;
    }
    isSequencePausedRef.current = false;
    if (!activeAudioBid && audioSequenceListRef.current.length) {
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
      startSequenceFromPage(currentPage);
      return;
    }
    audioPlayerRef.current?.play();
  }, [
    previewMode,
    activeAudioBid,
    startSequenceFromPage,
    deckRef,
    currentPptPageRef,
  ]);

  const handlePause = useCallback(
    (traceId?: string) => {
      if (previewMode) {
        return;
      }
      isSequencePausedRef.current = true;
      clearAudioSequenceTimer();
      audioPlayerRef.current?.pause({ traceId });
    },
    [previewMode, clearAudioSequenceTimer],
  );

  useEffect(() => {
    setIsAudioPlaying(false);
  }, [activeAudioBid, setIsAudioPlaying]);

  return {
    audioPlayerRef,
    activeContentItem,
    activeSequenceElementBid,
    activeAudioElementBid,
    sequenceInteraction,
    isAudioSequenceActive,
    audioSequenceToken,
    handleAudioEnded,
    handlePlay,
    handlePause,
    startSequenceFromIndex,
    startSequenceFromPage,
  };
};

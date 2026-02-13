import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Reveal, { Options } from 'reveal.js';
import {
  splitContentSegments,
  type RenderSegment,
} from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import type { AudioPlayerHandle } from '@/components/audio/AudioPlayer';

export type AudioInteractionItem = ChatContentItem & {
  page: number;
  audioPlaybackBid?: string;
};

export type ListenSlideItem = {
  item: ChatContentItem;
  segments: RenderSegment[];
};

export const useListenContentData = (items: ChatContentItem[]) => {
  const orderedContentBlockBids = useMemo(() => {
    const seen = new Set<string>();
    const bids: string[] = [];
    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      const bid = item.generated_block_bid;
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

  const { lastInteractionBid, lastItemIsInteraction } = useMemo(() => {
    let latestInteractionBid: string | null = null;
    for (let i = items.length - 1; i >= 0; i -= 1) {
      if (items[i].type === ChatContentItemType.INTERACTION) {
        latestInteractionBid = items[i].generated_block_bid;
        break;
      }
    }
    const lastItem = items[items.length - 1];
    return {
      lastInteractionBid: latestInteractionBid,
      lastItemIsInteraction: lastItem?.type === ChatContentItemType.INTERACTION,
    };
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
        const contentPage =
          slideSegments.length > 0 ? pageCursor : fallbackPage;
        const interactionPage = fallbackPage;
        const hasAudioTracks = Boolean(
          item.audioTracks && item.audioTracks.length > 0,
        );
        const shouldUseAudioTracks = hasAudioTracks && !item.isAudioStreaming;
        const hasAudio = Boolean(
          shouldUseAudioTracks ||
          item.audioUrl ||
          (item.audioSegments && item.audioSegments.length > 0) ||
          item.isAudioStreaming,
        );

        if (item.type === ChatContentItemType.CONTENT && hasAudio) {
          if (shouldUseAudioTracks) {
            const sortedTracks = [...(item.audioTracks || [])].sort(
              (a, b) => a.position - b.position,
            );
            sortedTracks.forEach(track => {
              nextAudioAndInteractionList.push({
                ...item,
                audioPlaybackBid: `${item.generated_block_bid}::${track.position}`,
                audioUrl: track.audioUrl,
                audioDurationMs: track.durationMs,
                audioTracks: [track],
                audioSegments: undefined,
                isAudioStreaming: false,
                page: contentPage,
              });
            });
          } else {
            nextAudioAndInteractionList.push({
              ...item,
              audioPlaybackBid: item.generated_block_bid,
              page: contentPage,
            });
          }
        }

        if (item.type === ChatContentItemType.INTERACTION) {
          mapping.set(interactionPage, item);
          nextAudioAndInteractionList.push({
            ...item,
            page: interactionPage,
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

  const contentByBid = useMemo(() => {
    const mapping = new Map<string, ChatContentItem>();
    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      const bid = item.generated_block_bid;
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
      const bid = item.generated_block_bid;
      if (!bid || bid === 'loading') {
        continue;
      }
      mapping.set(bid, item);
    }
    return mapping;
  }, [audioAndInteractionList]);

  const ttsReadyBlockBids = useMemo(() => {
    const ready = new Set<string>();
    for (const item of items) {
      if (item.type !== ChatContentItemType.LIKE_STATUS) {
        continue;
      }
      const parentBid = item.parent_block_bid;
      if (!parentBid) {
        continue;
      }
      ready.add(parentBid);
    }
    return ready;
  }, [items]);

  const firstContentItem = useMemo(() => {
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (
        item.type === ChatContentItemType.CONTENT &&
        item.generated_block_bid &&
        item.generated_block_bid !== 'loading'
      ) {
        return item;
      }
    }
    return null;
  }, [items]);

  return {
    orderedContentBlockBids,
    slideItems,
    interactionByPage,
    audioAndInteractionList,
    contentByBid,
    audioContentByBid,
    ttsReadyBlockBids,
    lastInteractionBid,
    lastItemIsInteraction,
    firstContentItem,
  };
};

interface UseListenPptParams {
  chatRef: React.RefObject<HTMLDivElement>;
  deckRef: React.MutableRefObject<Reveal.Api | null>;
  currentPptPageRef: React.MutableRefObject<number>;
  activeBlockBidRef: React.MutableRefObject<string | null>;
  pendingAutoNextRef: React.MutableRefObject<boolean>;
  slideItems: ListenSlideItem[];
  interactionByPage: Map<number, ChatContentItem>;
  sectionTitle?: string;
  isLoading: boolean;
  isAudioPlaying: boolean;
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
  activeBlockBidRef,
  pendingAutoNextRef,
  slideItems,
  interactionByPage,
  sectionTitle,
  isLoading,
  isAudioPlaying,
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
    () => slideItems[0]?.item.generated_block_bid ?? null,
    [slideItems],
  );

  useEffect(() => {
    if (!firstSlideBid) {
      prevFirstSlideBidRef.current = null;
      return;
    }
    if (!prevFirstSlideBidRef.current) {
      shouldSlideToFirstRef.current = true;
      onResetSequence?.();
    } else if (prevFirstSlideBidRef.current !== firstSlideBid) {
      shouldSlideToFirstRef.current = true;
      onResetSequence?.();
    }
    prevFirstSlideBidRef.current = firstSlideBid;
  }, [firstSlideBid, onResetSequence]);

  useEffect(() => {
    if (!sectionTitle) {
      prevSectionTitleRef.current = null;
      return;
    }
    if (
      prevSectionTitleRef.current &&
      prevSectionTitleRef.current !== sectionTitle
    ) {
      shouldSlideToFirstRef.current = true;
      onResetSequence?.();
    }
    prevSectionTitleRef.current = sectionTitle;
  }, [sectionTitle, onResetSequence]);

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
    return slide.getAttribute('data-generated-block-bid') || null;
  }, []);

  const syncActiveBlockFromDeck = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    const slide = deck.getCurrentSlide?.() as HTMLElement | undefined;
    const nextBid = getBlockBidFromSlide(slide ?? null);
    if (!nextBid || nextBid === activeBlockBidRef.current) {
      return;
    }
    if (shouldRenderEmptyPpt) {
      if (!activeBlockBidRef.current?.startsWith('empty-ppt-')) {
        activeBlockBidRef.current = nextBid;
      }
      return;
    }
    activeBlockBidRef.current = nextBid;
  }, [activeBlockBidRef, deckRef, getBlockBidFromSlide, shouldRenderEmptyPpt]);

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
    const currentBid = resolveContentBid(activeBlockBidRef.current);
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      return false;
    }
    return goToBlock(nextBid);
  }, [activeBlockBidRef, getNextContentBid, goToBlock, resolveContentBid]);

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

      const shouldAutoFollowOnAppend =
        prevSlidesLength > 0 &&
        nextSlidesLength > prevSlidesLength &&
        currentIndex >= prevLastIndex;
      const shouldHoldForStreamingAudio =
        isAudioPlaying &&
        Boolean(
          activeContentItem?.isAudioStreaming ||
          (activeContentItem?.audioSegments &&
            activeContentItem.audioSegments.length > 0),
        );
      const resolvedActiveBid = resolveContentBid(
        activeContentItem?.generated_block_bid ?? null,
      );
      const resolvedCurrentBid = resolveContentBid(activeBlockBidRef.current);
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
    isLoading,
    goToNextBlock,
    goToBlock,
    chatRef,
    updateNavState,
    activeContentItem?.generated_block_bid,
    activeContentItem?.isAudioStreaming,
    activeContentItem?.audioSegments?.length,
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
  activeBlockBidRef: React.MutableRefObject<string | null>;
  pendingAutoNextRef: React.MutableRefObject<boolean>;
  shouldStartSequenceRef: React.MutableRefObject<boolean>;
  contentByBid: Map<string, ChatContentItem>;
  audioContentByBid: Map<string, ChatContentItem>;
  ttsReadyBlockBids: Set<string>;
  onRequestAudioForBlock?: (generatedBlockBid: string) => Promise<any>;
  previewMode: boolean;
  shouldRenderEmptyPpt: boolean;
  getNextContentBid: (currentBid: string | null) => string | null;
  goToBlock: (blockBid: string) => boolean;
  resolveContentBid: (blockBid: string | null) => string | null;
  setIsAudioPlaying: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useListenAudioSequence = ({
  audioAndInteractionList,
  deckRef,
  currentPptPageRef,
  activeBlockBidRef,
  pendingAutoNextRef,
  shouldStartSequenceRef,
  contentByBid,
  audioContentByBid,
  ttsReadyBlockBids,
  onRequestAudioForBlock,
  previewMode,
  shouldRenderEmptyPpt,
  getNextContentBid,
  goToBlock,
  resolveContentBid,
  setIsAudioPlaying,
}: UseListenAudioSequenceParams) => {
  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);
  const requestedAudioBlockBidsRef = useRef<Set<string>>(new Set());
  const audioSequenceIndexRef = useRef(-1);
  const audioSequenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const audioSequenceListRef = useRef<AudioInteractionItem[]>([]);
  const prevAudioSequenceLengthRef = useRef(0);
  const [activeAudioPlaybackBid, setActiveAudioPlaybackBid] = useState<
    string | null
  >(null);
  const [activeAudioBlockBidRaw, setActiveAudioBlockBidRaw] = useState<
    string | null
  >(null);
  const [sequenceInteraction, setSequenceInteraction] =
    useState<AudioInteractionItem | null>(null);
  const [isAudioSequenceActive, setIsAudioSequenceActive] = useState(false);
  const [audioSequenceToken, setAudioSequenceToken] = useState(0);
  const isSequencePausedRef = useRef(false);

  const lastPlayedPlaybackBidRef = useRef<string | null>(null);
  const resolveAudioPlaybackBid = useCallback(
    (item: AudioInteractionItem | null | undefined) =>
      item?.audioPlaybackBid || item?.generated_block_bid || null,
    [],
  );

  useEffect(() => {
    audioSequenceListRef.current = audioAndInteractionList;
    // console.log('audioAndInteractionList', audioSequenceListRef.current);
    // console.log('listen-sequence-list-update', {
    //   listLength: audioAndInteractionList.length,
    //   contentCount: audioAndInteractionList.filter(
    //     item => item.type === ChatContentItemType.CONTENT,
    //   ).length,
    //   interactionCount: audioAndInteractionList.filter(
    //     item => item.type === ChatContentItemType.INTERACTION,
    //   ).length,
    // });
  }, [audioAndInteractionList]);

  const clearAudioSequenceTimer = useCallback(() => {
    if (audioSequenceTimerRef.current) {
      clearTimeout(audioSequenceTimerRef.current);
      audioSequenceTimerRef.current = null;
    }
  }, []);

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
      if (audioSequenceIndexRef.current === index && isAudioSequenceActive) {
        return;
      }
      if (isSequencePausedRef.current) {
        // console.log('listen-sequence-skip-play-paused', { index });
        return;
      }

      clearAudioSequenceTimer();
      const list = audioSequenceListRef.current;
      const nextItem = list[index];

      if (!nextItem) {
        // console.log('listen-sequence-end', { index, listLength: list.length });
        setSequenceInteraction(null);
        setActiveAudioPlaybackBid(null);
        setActiveAudioBlockBidRaw(null);
        setIsAudioSequenceActive(false);
        return;
      }
      // console.log('listen-sequence-play', {
      //   index,
      //   page: nextItem.page,
      //   type: nextItem.type,
      //   blockBid: nextItem.generated_block_bid ?? null,
      // });
      syncToSequencePage(nextItem.page);
      audioSequenceIndexRef.current = index;
      setIsAudioSequenceActive(true);
      const playbackBid = resolveAudioPlaybackBid(nextItem);
      if (playbackBid) {
        lastPlayedPlaybackBidRef.current = playbackBid;
      }

      if (nextItem.type === ChatContentItemType.INTERACTION) {
        setSequenceInteraction(nextItem);
        setActiveAudioPlaybackBid(null);
        setActiveAudioBlockBidRaw(null);
        if (index >= list.length - 1) {
          return;
        }
        audioSequenceTimerRef.current = setTimeout(() => {
          playAudioSequenceFromIndex(index + 1);
        }, 2000);
        return;
      }
      setSequenceInteraction(null);
      setActiveAudioPlaybackBid(playbackBid);
      setActiveAudioBlockBidRaw(nextItem.generated_block_bid);
      setAudioSequenceToken(prev => prev + 1);
    },
    [
      clearAudioSequenceTimer,
      syncToSequencePage,
      isAudioSequenceActive,
      resolveAudioPlaybackBid,
    ],
  );

  useEffect(() => {
    const prevLength = prevAudioSequenceLengthRef.current;
    const nextLength = audioAndInteractionList.length;
    prevAudioSequenceLengthRef.current = nextLength;
    // console.log('listen-sequence-length-change', {
    //   prevLength,
    //   nextLength,
    //   isAudioSequenceActive,
    //   sequenceIndex: audioSequenceIndexRef.current,
    // });
    if (previewMode || !nextLength) {
      return;
    }
    if (isSequencePausedRef.current) {
      // console.log('listen-sequence-skip-length-change-paused', {
      //   nextLength,
      // });
      return;
    }
    const currentIndex = audioSequenceIndexRef.current;

    if (
      isAudioSequenceActive &&
      sequenceInteraction &&
      currentIndex >= 0 &&
      prevLength > 0 &&
      currentIndex === prevLength - 1 &&
      nextLength > prevLength
    ) {
      // Continue after the last interaction when new audio arrives.
      playAudioSequenceFromIndex(currentIndex + 1);
      return;
    }

    // Auto-play new content if it matches the current page (e.g. Retake, or streaming new content)
    if (nextLength > prevLength) {
      const newItemIndex = nextLength - 1;
      const newItem = audioAndInteractionList[newItemIndex];
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;

      if (newItem?.page === currentPage) {
        // If it's the first item ever (prevLength === 0), or if we are appending to the current page sequence
        // we should play it.
        // But if we are just appending a new item to the END of the list, we should only play it if
        // we are not currently playing something else (unless it's a replacement/retake of the same index).
        if (prevLength === 0) {
          // Initial load for this page
          // Check if we are recovering from a flash (list became empty then full again)
          const lastBid = lastPlayedPlaybackBidRef.current;
          const resumeIndex = lastBid
            ? audioAndInteractionList.findIndex(
                item => resolveAudioPlaybackBid(item) === lastBid,
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
          if (
            !isAudioSequenceActive ||
            audioSequenceIndexRef.current === newItemIndex
          ) {
            playAudioSequenceFromIndex(newItemIndex);
          }
        }
      }
    }
  }, [
    audioAndInteractionList,
    isAudioSequenceActive,
    playAudioSequenceFromIndex,
    previewMode,
    sequenceInteraction,
    deckRef,
    currentPptPageRef,
    resolveSequenceStartIndex,
    resolveAudioPlaybackBid,
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
    setActiveAudioPlaybackBid(null);
    setActiveAudioBlockBidRaw(null);
    setIsAudioSequenceActive(false);
    // console.log('listen-sequence-reset');
  }, [clearAudioSequenceTimer]);

  const startSequenceFromIndex = useCallback(
    (index: number) => {
      const listLength = audioSequenceListRef.current.length;
      if (!listLength) {
        // console.log('listen-sequence-start-empty', { index });
        return;
      }
      const maxIndex = Math.max(listLength - 1, 0);
      const nextIndex = Math.min(Math.max(index, 0), maxIndex);
      resetSequenceState();
      // console.log('listen-sequence-start-index', { index, nextIndex });
      playAudioSequenceFromIndex(nextIndex);
    },
    [playAudioSequenceFromIndex, resetSequenceState],
  );

  const startSequenceFromPage = useCallback(
    (page: number) => {
      const startIndex = resolveSequenceStartIndex(page);
      if (startIndex < 0) {
        // console.log('listen-sequence-start-page-miss', { page });
        return;
      }
      // console.log('listen-sequence-start-page', { page, startIndex });
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
    setActiveAudioPlaybackBid(null);
    setActiveAudioBlockBidRaw(null);
    setSequenceInteraction(null);
    setIsAudioSequenceActive(false);
  }, [audioAndInteractionList.length, clearAudioSequenceTimer]);

  useEffect(() => {
    if (!shouldStartSequenceRef.current) {
      return;
    }
    if (!audioAndInteractionList.length) {
      // console.log('listen-sequence-auto-start-skip-empty');
      return;
    }
    if (isSequencePausedRef.current) {
      // console.log('listen-sequence-auto-start-skip-paused');
      return;
    }
    shouldStartSequenceRef.current = false;

    // Check if we can resume from the last played block (e.g. after a list flash/refresh)
    if (lastPlayedPlaybackBidRef.current) {
      const resumeIndex = audioAndInteractionList.findIndex(
        item =>
          resolveAudioPlaybackBid(item) === lastPlayedPlaybackBidRef.current,
      );
      if (resumeIndex >= 0) {
        // We found the last played item, so we are likely just recovering from a refresh.
        // Resume from there instead of restarting.
        // console.log('listen-sequence-auto-resume', {
        //   resumeIndex,
        //   blockBid: lastPlayedPlaybackBidRef.current,
        // });
        playAudioSequenceFromIndex(resumeIndex);
        return;
      }
    }

    // Otherwise, truly start from the beginning
    // console.log('listen-sequence-auto-start');
    playAudioSequenceFromIndex(0);
  }, [
    audioAndInteractionList,
    playAudioSequenceFromIndex,
    shouldStartSequenceRef,
    resolveAudioPlaybackBid,
  ]);

  const activeAudioBlockBid = useMemo(() => {
    if (!activeAudioBlockBidRaw) {
      return null;
    }
    return resolveContentBid(activeAudioBlockBidRaw);
  }, [activeAudioBlockBidRaw, resolveContentBid]);

  const activeContentItem = useMemo(() => {
    if (!activeAudioBlockBid) {
      return undefined;
    }
    return (
      audioContentByBid.get(activeAudioBlockBid) ??
      contentByBid.get(activeAudioBlockBid)
    );
  }, [activeAudioBlockBid, audioContentByBid, contentByBid]);

  const tryAdvanceToNextBlock = useCallback(() => {
    const currentBid = resolveContentBid(activeBlockBidRef.current);
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      // console.log('listen-sequence-advance-miss', { currentBid });
      return false;
    }

    const moved = goToBlock(nextBid);
    if (moved) {
      // console.log('listen-sequence-advance-success', {
      //   currentBid,
      //   nextBid,
      // });
      return true;
    }

    if (shouldRenderEmptyPpt) {
      activeBlockBidRef.current = `empty-ppt-${nextBid}`;
      // console.log('listen-sequence-advance-empty-ppt', { nextBid });
      return true;
    }

    pendingAutoNextRef.current = true;
    // console.log('listen-sequence-advance-pending', { nextBid });
    return true;
  }, [
    activeBlockBidRef,
    getNextContentBid,
    goToBlock,
    pendingAutoNextRef,
    resolveContentBid,
    shouldRenderEmptyPpt,
  ]);

  useEffect(() => {
    if (!activeAudioBlockBid) {
      return;
    }
    const item = contentByBid.get(activeAudioBlockBid);
    if (!item) {
      return;
    }

    const isBlockReadyForTts =
      Boolean(item.isHistory) || ttsReadyBlockBids.has(activeAudioBlockBid);
    if (!isBlockReadyForTts) {
      return;
    }

    const hasAudio = Boolean(
      item.audioUrl ||
      item.isAudioStreaming ||
      (item.audioSegments && item.audioSegments.length > 0),
    );

    if (
      !hasAudio &&
      onRequestAudioForBlock &&
      !previewMode &&
      !requestedAudioBlockBidsRef.current.has(activeAudioBlockBid)
    ) {
      requestedAudioBlockBidsRef.current.add(activeAudioBlockBid);
      onRequestAudioForBlock(activeAudioBlockBid).catch(() => {
        // errors handled by request layer toast; ignore here
      });
    }
  }, [
    activeAudioBlockBid,
    contentByBid,
    onRequestAudioForBlock,
    previewMode,
    ttsReadyBlockBids,
  ]);

  const handleAudioEnded = useCallback(() => {
    if (isSequencePausedRef.current) {
      // console.log('listen-sequence-ended-skip-paused');
      return;
    }
    const list = audioSequenceListRef.current;
    if (list.length) {
      const nextIndex = audioSequenceIndexRef.current + 1;
      if (nextIndex >= list.length) {
        // console.log('listen-sequence-ended-last', {
        //   nextIndex,
        //   listLength: list.length,
        // });
        setActiveAudioPlaybackBid(null);
        setActiveAudioBlockBidRaw(null);
        setIsAudioSequenceActive(false);
        tryAdvanceToNextBlock();
        return;
      }
      // console.log('listen-sequence-ended-next', { nextIndex });
      playAudioSequenceFromIndex(nextIndex);
      return;
    }
    // console.log('listen-sequence-ended-empty-list');
    tryAdvanceToNextBlock();
  }, [playAudioSequenceFromIndex, tryAdvanceToNextBlock]);

  const logAudioAction = useCallback(
    (action: 'play' | 'pause') => {
      // console.log(`listen-audio-${action}`, {
      //   activeAudioPlaybackBid,
      //   activeAudioBlockBid,
      //   audioUrl: activeContentItem?.audioUrl,
      //   content: activeContentItem?.content,
      //   listLength: audioSequenceListRef.current.length,
      //   sequenceIndex: audioSequenceIndexRef.current,
      //   isAudioSequenceActive,
      // });
    },
    [
      activeAudioPlaybackBid,
      activeAudioBlockBid,
      activeContentItem?.audioUrl,
      activeContentItem?.content,
      isAudioSequenceActive,
    ],
  );

  const handlePlay = useCallback(() => {
    if (previewMode) {
      return;
    }
    isSequencePausedRef.current = false;
    // console.log('listen-sequence-handle-play', {
    //   activeAudioPlaybackBid,
    //   listLength: audioSequenceListRef.current.length,
    // });
    // console.log('listen-toggle-play', {
    //   activeAudioPlaybackBid,
    //   hasAudioRef: Boolean(audioPlayerRef.current),
    //   listLength: audioSequenceListRef.current.length,
    //   sequenceIndex: audioSequenceIndexRef.current,
    //   isAudioSequenceActive,
    // });
    logAudioAction('play');
    if (!activeAudioPlaybackBid && audioSequenceListRef.current.length) {
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
      startSequenceFromPage(currentPage);
      return;
    }
    audioPlayerRef.current?.play();
  }, [
    previewMode,
    activeAudioPlaybackBid,
    isAudioSequenceActive,
    logAudioAction,
    startSequenceFromPage,
    deckRef,
    currentPptPageRef,
  ]);

  const handlePause = useCallback(
    (traceId?: string) => {
      if (previewMode) {
        return;
      }
      // console.log('listen-mode-handle-pause', {
      //   traceId,
      //   activeAudioPlaybackBid,
      //   activeAudioBlockBid,
      //   audioUrl: activeContentItem?.audioUrl,
      //   content: activeContentItem?.content,
      //   isAudioSequenceActive,
      //   sequenceIndex: audioSequenceIndexRef.current,
      // });
      logAudioAction('pause');
      isSequencePausedRef.current = true;
      // console.log('listen-sequence-handle-pause', { traceId });
      clearAudioSequenceTimer();
      audioPlayerRef.current?.pause({ traceId });
      // console.log('listen-mode-handle-pause-end', {
      //   traceId,
      //   activeAudioPlaybackBid,
      //   activeAudioBlockBid,
      // });
    },
    [
      previewMode,
      activeAudioPlaybackBid,
      activeAudioBlockBid,
      activeContentItem?.audioUrl,
      activeContentItem?.content,
      isAudioSequenceActive,
      logAudioAction,
      clearAudioSequenceTimer,
    ],
  );

  useEffect(() => {
    setIsAudioPlaying(false);
  }, [activeAudioPlaybackBid, setIsAudioPlaying]);

  return {
    audioPlayerRef,
    activeContentItem,
    activeAudioBlockBid,
    activeAudioPlaybackBid,
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

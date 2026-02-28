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
import {
  hasAudioContentInTracks,
  type AudioSegment,
  type AudioTrack,
} from '@/c-utils/audio-utils';

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

export const buildListenAudioSequenceBid = (
  generatedBlockBid: string,
  position: number,
) => `${generatedBlockBid}${LISTEN_AUDIO_BID_DELIMITER}${position}`;

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

const sortByPosition = <T extends { position?: number }>(list: T[] = []) =>
  [...list].sort((a, b) => Number(a.position ?? 0) - Number(b.position ?? 0));

const sortSegmentsByIndex = (segments: AudioSegment[] = []) =>
  [...segments].sort(
    (a, b) => Number(a.segmentIndex ?? 0) - Number(b.segmentIndex ?? 0),
  );

const normalizeAudioTracks = (item: ChatContentItem): AudioTrack[] => {
  const trackByPosition = new Map<number, AudioTrack>();

  (item.audioTracks ?? []).forEach(track => {
    const position = Number(track.position ?? 0);
    trackByPosition.set(position, {
      ...track,
      position,
      audioSegments: sortSegmentsByIndex(track.audioSegments ?? []),
    });
  });

  return sortByPosition(Array.from(trackByPosition.values()));
};

const buildSlidePageMapping = (
  item: ChatContentItem,
  pageIndices: number[],
  fallbackPage: number,
) => {
  const blockSlides = [...(item.listenSlides ?? [])]
    .filter(slide => slide.generated_block_bid === item.generated_block_bid)
    .sort(
      (a, b) =>
        Number(a.slide_index ?? 0) - Number(b.slide_index ?? 0) ||
        Number(a.audio_position ?? 0) - Number(b.audio_position ?? 0),
    );
  const pageBySlideId = new Map<string, number>();
  const pageByAudioPosition = new Map<number, number>();
  const realSlides = blockSlides.filter(slide => !slide.is_placeholder);

  if (pageIndices.length > 0 && realSlides.length > 0) {
    realSlides.forEach((slide, index) => {
      const page = pageIndices[Math.min(index, pageIndices.length - 1)];
      pageBySlideId.set(slide.slide_id, page);
    });
  }

  blockSlides.forEach((slide, index) => {
    if (pageBySlideId.has(slide.slide_id)) {
      return;
    }

    const samePositionSlide = realSlides.find(
      candidate =>
        Number(candidate.audio_position ?? 0) ===
          Number(slide.audio_position ?? 0) &&
        pageBySlideId.has(candidate.slide_id),
    );
    if (samePositionSlide) {
      pageBySlideId.set(
        slide.slide_id,
        pageBySlideId.get(samePositionSlide.slide_id)!,
      );
      return;
    }

    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const previous = blockSlides[cursor];
      const previousPage = pageBySlideId.get(previous.slide_id);
      if (previousPage !== undefined) {
        pageBySlideId.set(slide.slide_id, previousPage);
        return;
      }
    }

    const firstPage = pageIndices[0];
    if (firstPage !== undefined) {
      pageBySlideId.set(slide.slide_id, firstPage);
      return;
    }

    pageBySlideId.set(slide.slide_id, fallbackPage);
  });

  blockSlides.forEach(slide => {
    const page = pageBySlideId.get(slide.slide_id);
    if (page === undefined) {
      return;
    }
    const position = Number(slide.audio_position ?? 0);
    const hasCurrent = pageByAudioPosition.has(position);
    if (!hasCurrent || !slide.is_placeholder) {
      pageByAudioPosition.set(position, page);
    }
  });

  const resolvePageByPosition = (position: number) => {
    if (pageByAudioPosition.has(position)) {
      return pageByAudioPosition.get(position)!;
    }
    const orderedPositions = [...pageByAudioPosition.keys()].sort(
      (a, b) => a - b,
    );
    let nearestLower: number | null = null;
    orderedPositions.forEach(candidate => {
      if (candidate <= position) {
        nearestLower = candidate;
      }
    });
    if (nearestLower !== null) {
      return pageByAudioPosition.get(nearestLower)!;
    }
    if (pageIndices.length > 0) {
      return pageIndices[0];
    }
    return fallbackPage;
  };

  return {
    blockSlides,
    pageBySlideId,
    resolvePageByPosition,
  };
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

          tracks.forEach(track => {
            const position = Number(track.position ?? 0);
            const page =
              (track.slideId ? pageBySlideId.get(track.slideId) : undefined) ??
              resolvePageByPosition(position);
            const sequenceBid = buildListenAudioSequenceBid(
              item.generated_block_bid,
              position,
            );

            nextAudioAndInteractionList.push({
              ...item,
              generated_block_bid: sequenceBid,
              sourceGeneratedBlockBid: item.generated_block_bid,
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
  activeBlockBidRef,
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
    () => slideItems[0]?.item.generated_block_bid ?? null,
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
    isSlideNavigationLocked,
    allowAutoPlayback,
    isLoading,
    goToNextBlock,
    goToBlock,
    chatRef,
    updateNavState,
    activeContentItem?.generated_block_bid,
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
  activeBlockBidRef: React.MutableRefObject<string | null>;
  pendingAutoNextRef: React.MutableRefObject<boolean>;
  shouldStartSequenceRef: React.MutableRefObject<boolean>;
  sequenceStartSignal: number;
  contentByBid: Map<string, ChatContentItem>;
  audioContentByBid: Map<string, ChatContentItem>;
  ttsReadyBlockBids: Set<string>;
  onRequestAudioForBlock?: (generatedBlockBid: string) => Promise<any>;
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
  activeBlockBidRef,
  pendingAutoNextRef,
  shouldStartSequenceRef,
  sequenceStartSignal,
  contentByBid,
  audioContentByBid,
  ttsReadyBlockBids,
  onRequestAudioForBlock,
  previewMode,
  shouldRenderEmptyPpt,
  getNextContentBid,
  goToBlock,
  resolveContentBid,
  allowAutoPlayback,
  isAudioPlaying,
  setIsAudioPlaying,
}: UseListenAudioSequenceParams) => {
  const isAudioDebugEnabled = process.env.NODE_ENV !== 'production';
  const logAudioDebug = useCallback(
    (event: string, payload?: Record<string, any>) => {
      // if (!isAudioDebugEnabled) {
      return;
      // }
      console.log(`[listen-audio-debug] ${event}`, payload ?? {});
    },
    [isAudioDebugEnabled],
  );
  const logAudioInterrupt = useCallback(
    (event: string, payload?: Record<string, any>) => {
      if (!isAudioDebugEnabled) {
        return;
      }
      console.log(`[音频中断排查][ListenSequence] ${event}`, payload ?? {});
    },
    [isAudioDebugEnabled],
  );
  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);
  const requestedAudioBlockBidsRef = useRef<Set<string>>(new Set());
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
      if (
        audioSequenceIndexRef.current === index &&
        isAudioSequenceActiveRef.current
      ) {
        logAudioDebug('listen-sequence-play-skip-same-index', {
          index,
          activeIndex: audioSequenceIndexRef.current,
          isAudioSequenceActive: isAudioSequenceActiveRef.current,
        });
        logAudioInterrupt('跳过重复播放同一序号', {
          index,
          activeIndex: audioSequenceIndexRef.current,
          isAudioSequenceActive: isAudioSequenceActiveRef.current,
        });
        return;
      }
      if (isSequencePausedRef.current) {
        logAudioInterrupt('当前序列处于暂停态，忽略播放请求', {
          targetIndex: index,
        });
        // console.log('listen-sequence-skip-play-paused', { index });
        return;
      }

      clearAudioSequenceTimer();
      const list = audioSequenceListRef.current;
      const nextItem = list[index];

      if (!nextItem) {
        logAudioDebug('listen-sequence-play-end', {
          index,
          listLength: list.length,
        });
        logAudioInterrupt('序列已到末尾，清空 activeAudioBid', {
          index,
          listLength: list.length,
        });
        // console.log('listen-sequence-end', { index, listLength: list.length });
        setSequenceInteraction(null);
        setActiveAudioBid(null);
        activeAudioBidRef.current = null;
        setIsAudioSequenceActive(false);
        isAudioSequenceActiveRef.current = false;
        return;
      }
      logAudioDebug('listen-sequence-play-item', {
        index,
        page: nextItem.page,
        type: nextItem.type,
        generatedBlockBid: nextItem.generated_block_bid ?? null,
        sequenceKind: nextItem.sequenceKind,
        audioPosition: nextItem.audioPosition ?? null,
      });
      // console.log('listen-sequence-play', {
      //   index,
      //   page: nextItem.page,
      //   type: nextItem.type,
      //   blockBid: nextItem.generated_block_bid ?? null,
      // });
      syncToSequencePage(nextItem.page);
      audioSequenceIndexRef.current = index;
      setIsAudioSequenceActive(true);
      isAudioSequenceActiveRef.current = true;
      logAudioInterrupt('切换到新的序列项，可能触发当前音频切换', {
        index,
        sequenceKind: nextItem.sequenceKind,
        blockBid: nextItem.generated_block_bid ?? null,
        page: nextItem.page,
      });
      if (nextItem.generated_block_bid) {
        lastPlayedAudioBidRef.current = nextItem.generated_block_bid;
      }

      if (nextItem.type === ChatContentItemType.INTERACTION) {
        logAudioInterrupt(
          '进入交互项，主动清空 activeAudioBid（可能导致当前音频暂停）',
          {
            index,
            interactionBid: nextItem.generated_block_bid ?? null,
            previousActiveAudioBid: activeAudioBidRef.current,
            isAudioPlaying: isAudioPlayingRef.current,
          },
        );
        setSequenceInteraction(nextItem);
        setActiveAudioBid(null);
        activeAudioBidRef.current = null;
        if (index >= list.length - 1) {
          return;
        }
        logAudioInterrupt('当前项为交互项，2秒后自动推进下一项', {
          currentIndex: index,
          nextIndex: index + 1,
        });
        audioSequenceTimerRef.current = setTimeout(() => {
          playAudioSequenceFromIndex(index + 1);
        }, 2000);
        return;
      }
      setSequenceInteraction(null);
      setActiveAudioBid(nextItem.generated_block_bid);
      activeAudioBidRef.current = nextItem.generated_block_bid;
      logAudioInterrupt('设置 activeAudioBid，AudioPlayerList 将切换到该音频', {
        index,
        activeAudioBid: nextItem.generated_block_bid ?? null,
      });
      setAudioSequenceToken(prev => prev + 1);
    },
    [
      clearAudioSequenceTimer,
      logAudioInterrupt,
      logAudioDebug,
      syncToSequencePage,
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
    if (!allowAutoPlayback) {
      return;
    }
    if (isSequencePausedRef.current) {
      // console.log('listen-sequence-skip-length-change-paused', {
      //   nextLength,
      // });
      return;
    }
    const isSequenceActive = isAudioSequenceActiveRef.current;
    const hasActiveAudioBid = Boolean(activeAudioBidRef.current);
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
      logAudioInterrupt('列表增长触发：交互项后自动继续播放下一项', {
        prevLength,
        nextLength,
        currentIndex,
        nextIndex: currentIndex + 1,
      });
      playAudioSequenceFromIndex(currentIndex + 1);
      return;
    }

    // Auto-play new content if it matches the current page (e.g. Retake, or streaming new content)
    if (nextLength > prevLength) {
      const newItemIndex = nextLength - 1;
      const newItem = audioAndInteractionList[newItemIndex];
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
      const newItemSourceBid = resolveContentBid(
        newItem?.generated_block_bid ?? null,
      );
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
                item => item.generated_block_bid === lastBid,
              )
            : -1;

          if (resumeIndex >= 0) {
            // Resume playback from the last known block to maintain continuity
            logAudioInterrupt('列表从空恢复，按上次播放位置恢复', {
              resumeIndex,
              lastBid,
              currentPage,
            });
            playAudioSequenceFromIndex(resumeIndex);
          } else {
            const startIndex = resolveSequenceStartIndex(currentPage);
            if (startIndex >= 0) {
              logAudioInterrupt('列表从空恢复，从当前页起始项启动播放', {
                startIndex,
                currentPage,
              });
              playAudioSequenceFromIndex(startIndex);
            }
          }
        } else {
          // Appending new item
          // Guard against interruption: only block when audio is actively playing.
          // If sequence is idle at tail, allow continuing with appended item.
          const currentSequenceItem =
            currentIndex >= 0 ? audioAndInteractionList[currentIndex] : null;
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
            logAudioInterrupt(
              '列表追加触发自动播放被拦截（避免中断当前音频）',
              {
                prevLength,
                nextLength,
                currentIndex,
                newItemIndex,
                isAudioPlaying: isAudioPlayingNow,
                hasActiveAudioBid,
                isSequenceActive,
                currentSequenceKind: currentSequenceItem?.sequenceKind ?? null,
                currentSequenceBid:
                  currentSequenceItem?.generated_block_bid ?? null,
              },
            );
            return;
          }
          if (
            !isSequenceActive ||
            audioSequenceIndexRef.current === newItemIndex ||
            isIdleAtTail
          ) {
            logAudioInterrupt('列表追加触发自动播放新项（重点排查点）', {
              prevLength,
              nextLength,
              currentIndex,
              newItemIndex,
              isAudioSequenceActive: isSequenceActive,
              isAudioPlaying: isAudioPlayingNow,
              hasActiveAudioBid,
              isIdleAtTail,
              currentPage,
              newItemPage: newItem?.page ?? null,
              newItemBid: newItem?.generated_block_bid ?? null,
            });
            playAudioSequenceFromIndex(newItemIndex);
          } else {
            logAudioInterrupt('列表追加但当前序列活跃，未触发自动播放', {
              prevLength,
              nextLength,
              currentIndex,
              newItemIndex,
              isAudioSequenceActive: isSequenceActive,
              isAudioPlaying: isAudioPlayingNow,
              hasActiveAudioBid,
              isIdleAtTail,
            });
          }
        }
      } else if (shouldResumeLateAudioFromSameBlock) {
        logAudioInterrupt(
          '列表追加命中同 block 迟到音频兜底，忽略 page 不一致并自动续播',
          {
            prevLength,
            nextLength,
            currentIndex,
            newItemIndex,
            currentPage,
            newItemPage: newItem?.page ?? null,
            newItemBid: newItem?.generated_block_bid ?? null,
            newItemSourceBid,
            lastPlayedSourceBid,
            isAudioSequenceActive: isSequenceActive,
            isAudioPlaying: isAudioPlayingNow,
          },
        );
        playAudioSequenceFromIndex(newItemIndex);
      } else {
        // Keep silent for this high-frequency non-action branch.
      }
    }
  }, [
    audioAndInteractionList,
    logAudioInterrupt,
    playAudioSequenceFromIndex,
    previewMode,
    allowAutoPlayback,
    sequenceInteraction,
    deckRef,
    currentPptPageRef,
    resolveContentBid,
    resolveSequenceStartIndex,
  ]);

  const resetSequenceState = useCallback(() => {
    logAudioInterrupt('调用 resetSequenceState，将主动 pause 当前音频', {
      reason: 'sequence-reset',
      currentIndex: audioSequenceIndexRef.current,
      activeAudioBid,
    });
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
    // console.log('listen-sequence-reset');
  }, [activeAudioBid, clearAudioSequenceTimer, logAudioInterrupt]);

  const startSequenceFromIndex = useCallback(
    (index: number) => {
      const listLength = audioSequenceListRef.current.length;
      if (!listLength) {
        // console.log('listen-sequence-start-empty', { index });
        return;
      }
      const maxIndex = Math.max(listLength - 1, 0);
      const nextIndex = Math.min(Math.max(index, 0), maxIndex);
      logAudioInterrupt('调用 startSequenceFromIndex，准备重置并跳到指定项', {
        requestIndex: index,
        nextIndex,
        listLength,
      });
      resetSequenceState();
      // console.log('listen-sequence-start-index', { index, nextIndex });
      playAudioSequenceFromIndex(nextIndex);
    },
    [logAudioInterrupt, playAudioSequenceFromIndex, resetSequenceState],
  );

  const startSequenceFromPage = useCallback(
    (page: number) => {
      const startIndex = resolveSequenceStartIndex(page);
      if (startIndex < 0) {
        // console.log('listen-sequence-start-page-miss', { page });
        return;
      }
      // console.log('listen-sequence-start-page', { page, startIndex });
      logAudioInterrupt('调用 startSequenceFromPage，准备切换页面序列', {
        page,
        startIndex,
      });
      startSequenceFromIndex(startIndex);
    },
    [logAudioInterrupt, resolveSequenceStartIndex, startSequenceFromIndex],
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
    logAudioInterrupt('audioAndInteractionList 变空，重置序列状态', {
      reason: 'empty-audio-list',
    });
    clearAudioSequenceTimer();
    audioSequenceIndexRef.current = -1;
    setActiveAudioBid(null);
    activeAudioBidRef.current = null;
    setSequenceInteraction(null);
    setIsAudioSequenceActive(false);
    isAudioSequenceActiveRef.current = false;
  }, [
    audioAndInteractionList.length,
    clearAudioSequenceTimer,
    logAudioInterrupt,
  ]);

  useEffect(() => {
    if (!allowAutoPlayback) {
      return;
    }
    if (!shouldStartSequenceRef.current) {
      return;
    }
    if (!audioAndInteractionList.length) {
      // console.log('listen-sequence-auto-start-skip-empty');
      return;
    }
    if (isSequencePausedRef.current) {
      logAudioDebug('listen-sequence-auto-start-reset-paused', {
        listLength: audioAndInteractionList.length,
      });
      isSequencePausedRef.current = false;
    }
    shouldStartSequenceRef.current = false;

    // Check if we can resume from the last played block (e.g. after a list flash/refresh)
    if (lastPlayedAudioBidRef.current) {
      const resumeIndex = audioAndInteractionList.findIndex(
        item => item.generated_block_bid === lastPlayedAudioBidRef.current,
      );
      if (resumeIndex >= 0) {
        // We found the last played item, so we are likely just recovering from a refresh.
        // Resume from there instead of restarting.
        // console.log('listen-sequence-auto-resume', {
        //   resumeIndex,
        //   blockBid: lastPlayedAudioBidRef.current,
        // });
        logAudioInterrupt('onResetSequence 后按上次播放位置恢复', {
          resumeIndex,
          lastPlayedAudioBid: lastPlayedAudioBidRef.current,
        });
        playAudioSequenceFromIndex(resumeIndex);
        return;
      }
    }

    // Otherwise, truly start from the beginning
    // console.log('listen-sequence-auto-start');
    logAudioInterrupt('onResetSequence 后从头开始播放序列', {
      startIndex: 0,
      listLength: audioAndInteractionList.length,
    });
    playAudioSequenceFromIndex(0);
  }, [
    audioAndInteractionList,
    logAudioInterrupt,
    sequenceStartSignal,
    logAudioDebug,
    playAudioSequenceFromIndex,
    shouldStartSequenceRef,
    allowAutoPlayback,
  ]);

  const activeSequenceBlockBid = useMemo(() => {
    if (!activeAudioBid) {
      return null;
    }
    return activeAudioBid;
  }, [activeAudioBid]);

  const activeAudioBlockBid = useMemo(() => {
    if (!activeAudioBid) {
      return null;
    }
    return resolveContentBid(activeAudioBid);
  }, [activeAudioBid, resolveContentBid]);

  useEffect(() => {
    logAudioDebug('listen-sequence-active-bid-change', {
      activeAudioBid,
      activeSequenceBlockBid,
      activeAudioBlockBid,
      audioSequenceToken,
      isAudioSequenceActive,
    });
  }, [
    activeAudioBid,
    activeAudioBlockBid,
    activeSequenceBlockBid,
    audioSequenceToken,
    isAudioSequenceActive,
    logAudioDebug,
  ]);

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
      logAudioInterrupt('sequence-advance-next-bid-missing', {
        currentBid,
        activeBlockBid: activeBlockBidRef.current,
      });
      // console.log('listen-sequence-advance-miss', { currentBid });
      return false;
    }

    const moved = goToBlock(nextBid);
    if (moved) {
      logAudioInterrupt('sequence-advance-go-to-next-block-success', {
        currentBid,
        nextBid,
      });
      // console.log('listen-sequence-advance-success', {
      //   currentBid,
      //   nextBid,
      // });
      return true;
    }

    if (shouldRenderEmptyPpt) {
      activeBlockBidRef.current = `empty-ppt-${nextBid}`;
      logAudioInterrupt('sequence-advance-empty-ppt-fallback', {
        currentBid,
        nextBid,
        activeBlockBid: activeBlockBidRef.current,
      });
      // console.log('listen-sequence-advance-empty-ppt', { nextBid });
      return true;
    }

    pendingAutoNextRef.current = true;
    logAudioInterrupt('sequence-advance-defer-until-next-render', {
      currentBid,
      nextBid,
      pendingAutoNext: pendingAutoNextRef.current,
    });
    // console.log('listen-sequence-advance-pending', { nextBid });
    return true;
  }, [
    activeBlockBidRef,
    getNextContentBid,
    goToBlock,
    logAudioInterrupt,
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

    const hasAudio = Boolean(hasAudioContentInTracks(item.audioTracks ?? []));

    if (
      !hasAudio &&
      onRequestAudioForBlock &&
      !previewMode &&
      !requestedAudioBlockBidsRef.current.has(activeAudioBlockBid)
    ) {
      requestedAudioBlockBidsRef.current.add(activeAudioBlockBid);
      logAudioDebug('listen-sequence-request-audio', {
        activeAudioBlockBid,
        hasAudio,
        isBlockReadyForTts,
        isHistory: Boolean(item.isHistory),
        hasTracks: item.audioTracks?.length ?? 0,
      });
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
    logAudioDebug,
  ]);

  const handleAudioEnded = useCallback(() => {
    logAudioInterrupt('sequence-handle-audio-ended-enter', {
      isPaused: isSequencePausedRef.current,
      listLength: audioSequenceListRef.current.length,
      currentIndex: audioSequenceIndexRef.current,
      activeAudioBid: activeAudioBidRef.current,
      activeBlockBid: activeBlockBidRef.current,
      currentPptPage: currentPptPageRef.current,
    });
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
        setActiveAudioBid(null);
        activeAudioBidRef.current = null;
        setIsAudioSequenceActive(false);
        isAudioSequenceActiveRef.current = false;
        logAudioInterrupt(
          '当前音频结束且已是最后一项，尝试推进到下一个 block',
          {
            nextIndex,
            listLength: list.length,
          },
        );
        const advanced = tryAdvanceToNextBlock();
        logAudioInterrupt('sequence-handle-audio-ended-tail-advance-result', {
          nextIndex,
          listLength: list.length,
          advanced,
        });
        return;
      }
      // console.log('listen-sequence-ended-next', { nextIndex });
      logAudioInterrupt('当前音频结束，推进到序列下一项', {
        currentIndex: audioSequenceIndexRef.current,
        nextIndex,
      });
      playAudioSequenceFromIndex(nextIndex);
      return;
    }
    // console.log('listen-sequence-ended-empty-list');
    logAudioInterrupt('当前音频结束但序列为空，尝试推进到下一个 block', {
      reason: 'empty-sequence-on-ended',
    });
    const advanced = tryAdvanceToNextBlock();
    logAudioInterrupt('sequence-handle-audio-ended-empty-advance-result', {
      advanced,
    });
  }, [logAudioInterrupt, playAudioSequenceFromIndex, tryAdvanceToNextBlock]);

  const logAudioAction = useCallback(
    (action: 'play' | 'pause') => {
      // console.log(`listen-audio-${action}`, {
      //   activeAudioBid,
      //   activeAudioBlockBid,
      //   audioUrl: activeContentItem?.audioUrl,
      //   content: activeContentItem?.content,
      //   listLength: audioSequenceListRef.current.length,
      //   sequenceIndex: audioSequenceIndexRef.current,
      //   isAudioSequenceActive,
      // });
    },
    [
      activeAudioBid,
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
    logAudioInterrupt('用户或系统触发播放动作 handlePlay', {
      activeAudioBid,
      currentIndex: audioSequenceIndexRef.current,
      listLength: audioSequenceListRef.current.length,
    });
    isSequencePausedRef.current = false;
    // console.log('listen-sequence-handle-play', {
    //   activeAudioBid,
    //   listLength: audioSequenceListRef.current.length,
    // });
    // console.log('listen-toggle-play', {
    //   activeAudioBid,
    //   hasAudioRef: Boolean(audioPlayerRef.current),
    //   listLength: audioSequenceListRef.current.length,
    //   sequenceIndex: audioSequenceIndexRef.current,
    //   isAudioSequenceActive,
    // });
    logAudioAction('play');
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
    isAudioSequenceActive,
    logAudioInterrupt,
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
      logAudioInterrupt('用户或系统触发暂停动作 handlePause', {
        traceId: traceId ?? null,
        activeAudioBid,
        currentIndex: audioSequenceIndexRef.current,
      });
      // console.log('listen-mode-handle-pause', {
      //   traceId,
      //   activeAudioBid,
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
      //   activeAudioBid,
      //   activeAudioBlockBid,
      // });
    },
    [
      previewMode,
      activeAudioBid,
      activeAudioBlockBid,
      activeContentItem?.audioUrl,
      activeContentItem?.content,
      isAudioSequenceActive,
      logAudioInterrupt,
      logAudioAction,
      clearAudioSequenceTimer,
    ],
  );

  useEffect(() => {
    logAudioInterrupt('activeAudioBid 变化，重置 isAudioPlaying=false', {
      activeAudioBid,
    });
    setIsAudioPlaying(false);
  }, [activeAudioBid, logAudioInterrupt, setIsAudioPlaying]);

  return {
    audioPlayerRef,
    activeContentItem,
    activeSequenceBlockBid,
    activeAudioBlockBid,
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

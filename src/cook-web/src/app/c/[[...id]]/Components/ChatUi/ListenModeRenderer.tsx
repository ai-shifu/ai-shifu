import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ListenPlayer from './ListenPlayer';
import { cn } from '@/lib/utils';
import Reveal from 'reveal.js';
import 'reveal.js/dist/reveal.css';
import 'reveal.js/dist/theme/white.css';
import ContentIframe from './ContentIframe';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import './ListenModeRenderer.scss';
import {
  AudioPlayer,
  type AudioPlayerHandle,
} from '@/components/audio/AudioPlayer';
import {
  splitContentSegments,
  type RenderSegment,
  type OnSendContentParams,
} from 'markdown-flow-ui/renderer';

type RevealOptionsWithScrollMode = Reveal.Options & {
  scrollMode?: 'classic' | 'scroll';
};

interface ListenModeRendererProps {
  items: ChatContentItem[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  containerClassName?: string;
  isLoading?: boolean;
  sectionTitle?: string;
  previewMode?: boolean;
  onRequestAudioForBlock?: (generatedBlockBid: string) => Promise<any>;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
}

const ListenModeRenderer = ({
  items,
  mobileStyle,
  chatRef,
  containerClassName,
  isLoading = false,
  sectionTitle,
  previewMode = false,
  onRequestAudioForBlock,
  onSend,
}: ListenModeRendererProps) => {
  const deckRef = useRef<Reveal.Api | null>(null);
  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);
  const pendingAutoNextRef = useRef(false);
  const hasAutoSlidToLatestRef = useRef(false);
  const requestedAudioBlockBidsRef = useRef<Set<string>>(new Set());
  const currentPptPageRef = useRef<number>(0);
  const prevSlidesLengthRef = useRef(0);
  const [activeBlockBid, setActiveBlockBid] = useState<string | null>(null);
  const [currentInteraction, setCurrentInteraction] =
    useState<ChatContentItem | null>(null);
  const activeBlockBidRef = useRef<string | null>(null);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [isPrevDisabled, setIsPrevDisabled] = useState(true);
  const [isNextDisabled, setIsNextDisabled] = useState(true);

  useEffect(() => {
    activeBlockBidRef.current = activeBlockBid;
  }, [activeBlockBid]);

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

  const resolveContentBid = useCallback((blockBid: string | null) => {
    if (!blockBid) {
      return null;
    }
    const emptyPrefix = 'empty-ppt-';
    if (!blockBid.startsWith(emptyPrefix)) {
      return blockBid;
    }
    const resolved = blockBid.slice(emptyPrefix.length);
    return resolved || null;
  }, []);

  const activeAudioBlockBid = useMemo(
    () => resolveContentBid(activeBlockBid),
    [activeBlockBid, resolveContentBid],
  );

  const activeContentItem = useMemo(() => {
    if (!activeAudioBlockBid) {
      return undefined;
    }
    return contentByBid.get(activeAudioBlockBid);
  }, [activeAudioBlockBid, contentByBid]);

  const getBlockBidFromSlide = useCallback((slide: HTMLElement | null) => {
    if (!slide) {
      return null;
    }
    return slide.getAttribute('data-generated-block-bid') || null;
  }, []);

  const { contentItems, interactionByPage } = useMemo(() => {
    let pageCursor = 0;
    const mapping = new Map<number, ChatContentItem>();
    const nextContentItems = items.map(item => {
      const segments =
        item.type === ChatContentItemType.CONTENT && !!item.content
          ? splitContentSegments(item.content || '', true)
          : [];
      const currentPage =
        segments.length > 0 && pageCursor === 0 ? 1 : pageCursor;
      const entry = {
        item,
        segments,
        currentPage,
      };
      if (item.type === ChatContentItemType.INTERACTION) {
        mapping.set(entry.currentPage - 1, item);
      }
      pageCursor += segments.length;
      return entry;
    });
    // console.log('interactionByPage', mapping);
    return { contentItems: nextContentItems, interactionByPage: mapping };
  }, [items]);

  const shouldRenderEmptyPpt = useMemo(() => {
    if (isLoading) {
      return false;
    }
    if (!contentItems.length) {
      return true;
    }
    const allSegmentsEmpty = contentItems.every(
      ({ segments }) => segments.length === 0,
    );
    const lastPage = contentItems[contentItems.length - 1]?.currentPage ?? 0;
    return allSegmentsEmpty || lastPage === 0;
  }, [contentItems, isLoading]);

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
        setActiveBlockBid(nextBid);
      }
      return;
    }
    activeBlockBidRef.current = nextBid;
    setActiveBlockBid(nextBid);
  }, [getBlockBidFromSlide, shouldRenderEmptyPpt]);

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
  }, []);

  const goToBlock = useCallback(
    (blockBid: string) => {
      const deck = deckRef.current;
      if (!deck || !chatRef.current) {
        return false;
      }

      const section =
        (chatRef.current.querySelector(
          `section[data-generated-block-bid="${blockBid}"]`,
        ) as HTMLElement | null) ||
        (chatRef.current.querySelector(
          `section[data-generated-block-bid="empty-ppt-${blockBid}"]`,
        ) as HTMLElement | null);
      if (!section) {
        return false;
      }

      const indices = deck.getIndices(section);
      deck.slide(indices.h, indices.v, indices.f);
      return true;
    },
    [chatRef],
  );

  const getNextContentBid = useCallback(
    (currentBid: string | null) => {
      if (!currentBid) {
        return null;
      }
      const currentIndex = orderedContentBlockBids.indexOf(currentBid);
      if (currentIndex < 0) {
        return null;
      }

      for (
        let i = currentIndex + 1;
        i < orderedContentBlockBids.length;
        i += 1
      ) {
        const nextBid = orderedContentBlockBids[i];
        if (!nextBid || nextBid === 'loading') {
          continue;
        }
        return nextBid;
      }
      return null;
    },
    [orderedContentBlockBids],
  );

  const goToNextBlock = useCallback(() => {
    const currentBid = resolveContentBid(activeBlockBidRef.current);
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      return false;
    }
    return goToBlock(nextBid);
  }, [getNextContentBid, goToBlock, resolveContentBid]);

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

  const emptySlideBlockBid = firstContentItem?.generated_block_bid
    ? `empty-ppt-${firstContentItem.generated_block_bid}`
    : 'empty-ppt';

  const syncInteractionForCurrentPage = useCallback(
    (pageIndex?: number) => {
      const targetPage =
        typeof pageIndex === 'number' ? pageIndex : currentPptPageRef.current;
      setCurrentInteraction(interactionByPage.get(targetPage) ?? null);
    },
    [interactionByPage],
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
  }, [syncInteractionForCurrentPage]);

  useEffect(() => {
    syncInteractionForCurrentPage();
  }, [syncInteractionForCurrentPage]);

  useEffect(() => {
    if (!chatRef.current || deckRef.current || isLoading) {
      return;
    }

    if (!contentItems.length) {
      return;
    }

    const slideNodes = chatRef.current.querySelectorAll('.slides > section');
    if (!slideNodes.length) {
      return;
    }

    const revealOptions: RevealOptionsWithScrollMode = {
      transition: 'slide',
      // margin: 0,
      // minScale: 1,
      // maxScale: 1,
      slideNumber: true,
      progress: false,
      controls: false,
    };

    deckRef.current = new Reveal(chatRef.current, revealOptions);

    deckRef.current.initialize().then(() => {
      syncActiveBlockFromDeck();
      syncPptPageFromDeck();
      updateNavState();
    });
  }, [
    chatRef,
    contentItems.length,
    isLoading,
    syncActiveBlockFromDeck,
    syncPptPageFromDeck,
    updateNavState,
  ]);

  useEffect(() => {
    if (!contentItems.length && deckRef.current) {
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
  }, [chatRef, contentItems.length, isLoading, syncActiveBlockFromDeck]);

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
  }, []);

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
  }, [syncActiveBlockFromDeck, syncPptPageFromDeck, updateNavState]);

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
    // Ensure Reveal picks up newly rendered slides
    try {
      deckRef.current.sync();
      deckRef.current.layout();
      const indices = deckRef.current.getIndices?.();
      const prevSlidesLength = prevSlidesLengthRef.current;
      const nextSlidesLength = slides.length;
      const lastIndex = Math.max(nextSlidesLength - 1, 0);
      const currentIndex = indices?.h ?? 0;
      const prevLastIndex = Math.max(prevSlidesLength - 1, 0);
      const shouldAutoFollowOnAppend =
        prevSlidesLength > 0 &&
        nextSlidesLength > prevSlidesLength &&
        currentIndex >= prevLastIndex;
      if (pendingAutoNextRef.current) {
        const moved = goToNextBlock();
        pendingAutoNextRef.current = !moved;
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
    contentItems,
    isAudioPlaying,
    isLoading,
    goToNextBlock,
    chatRef,
    updateNavState,
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
    const currentBid = resolveContentBid(activeBlockBidRef.current);
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      return;
    }
    const moved = goToBlock(nextBid);
    if (moved) {
      return;
    }
    if (shouldRenderEmptyPpt) {
      const nextSlideBid = `empty-ppt-${nextBid}`;
      activeBlockBidRef.current = nextSlideBid;
      setActiveBlockBid(nextSlideBid);
      return;
    }
    pendingAutoNextRef.current = true;
  }, [getNextContentBid, goToBlock, resolveContentBid, shouldRenderEmptyPpt]);

  const handleTogglePlay = useCallback(() => {
    if (previewMode) {
      return;
    }
    audioPlayerRef.current?.togglePlay();
  }, [previewMode]);

  useEffect(() => {
    if (!activeBlockBid) {
      return;
    }
    setIsAudioPlaying(false);
  }, [activeBlockBid]);

  const onPrev = useCallback(() => {
    const deck = deckRef.current;
    if (!deck || isPrevDisabled) {
      return;
    }
    deck.prev();
    currentPptPageRef.current = deck.getIndices().h;
    console.log('onPrev', currentPptPageRef.current);
    syncInteractionForCurrentPage(currentPptPageRef.current);
    updateNavState();
  }, [isPrevDisabled, syncInteractionForCurrentPage, updateNavState]);

  const onNext = useCallback(() => {
    const deck = deckRef.current;
    if (!deck || isNextDisabled) {
      return;
    }
    deck.next();
    currentPptPageRef.current = deck.getIndices().h;
    console.log('onNext', currentPptPageRef.current);
    syncInteractionForCurrentPage(currentPptPageRef.current);
    updateNavState();
  }, [isNextDisabled, syncInteractionForCurrentPage, updateNavState]);
  // console.log('listenmoderenderer',contentItems)
  return (
    <div
      className={cn(containerClassName, 'listen-reveal-wrapper')}
      style={{ background: '#F7F9FF', position: 'relative' }}
    >
      <div
        className={cn('reveal', 'listen-reveal')}
        ref={chatRef}
      >
        <div className='slides'>
          {!isLoading &&
            contentItems.map(({ item, segments }, idx) => {
              const baseKey = item.generated_block_bid || `${item.type}-${idx}`;
              console.log('segments', segments);
              return (
                <ContentIframe
                  key={baseKey}
                  // item={item}
                  segments={segments}
                  mobileStyle={mobileStyle}
                  blockBid={item.generated_block_bid}
                  sectionTitle={sectionTitle}
                />
              );
            })}
          {shouldRenderEmptyPpt ? (
            <section
              data-auto-animate
              data-generated-block-bid={emptySlideBlockBid}
            >
              <div className='w-full h-full font-bold flex items-center justify-center text-primary'>
                {sectionTitle}
              </div>
            </section>
          ) : null}
        </div>
      </div>
      {activeContentItem ? (
        <div className={cn('listen-audio-controls', 'hidden')}>
          <AudioPlayer
            ref={audioPlayerRef}
            key={activeBlockBid ?? 'listen-audio'}
            audioUrl={activeContentItem.audioUrl}
            streamingSegments={activeContentItem.audioSegments}
            isStreaming={Boolean(activeContentItem.isAudioStreaming)}
            alwaysVisible={true}
            disabled={previewMode}
            onRequestAudio={
              !previewMode && onRequestAudioForBlock && activeAudioBlockBid
                ? () => onRequestAudioForBlock(activeAudioBlockBid)
                : undefined
            }
            autoPlay={!previewMode}
            onPlayStateChange={setIsAudioPlaying}
            onEnded={handleAudioEnded}
            size={18}
          />
        </div>
      ) : null}
      <ListenPlayer
        onPrev={onPrev}
        onPlay={handleTogglePlay}
        onNext={onNext}
        prevDisabled={isPrevDisabled}
        nextDisabled={isNextDisabled}
        isAudioPlaying={isAudioPlaying}
        interaction={currentInteraction}
        onSend={onSend}
      />
    </div>
  );
};

ListenModeRenderer.displayName = 'ListenModeRenderer';

export default memo(ListenModeRenderer);

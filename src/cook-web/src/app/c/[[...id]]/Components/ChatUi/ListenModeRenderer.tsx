import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ListenPlayer from './ListenPlayer';
import { cn } from '@/lib/utils';
import Reveal from 'reveal.js';
import 'reveal.js/dist/reveal.css';
import 'reveal.js/dist/theme/white.css';
import ContentIframe from './ContentIframe';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import './ListenModeRenderer.scss';
import { AudioPlayer } from '@/components/audio/AudioPlayer';

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
}: ListenModeRendererProps) => {
  const deckRef = useRef<Reveal.Api | null>(null);
  const pendingAutoNextRef = useRef(false);
  const requestedAudioBlockBidsRef = useRef<Set<string>>(new Set());

  const [activeBlockBid, setActiveBlockBid] = useState<string | null>(null);
  const activeBlockBidRef = useRef<string | null>(null);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);

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

  const activeContentItem = useMemo(() => {
    if (!activeBlockBid) {
      return undefined;
    }
    return contentByBid.get(activeBlockBid);
  }, [activeBlockBid, contentByBid]);

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
    activeBlockBidRef.current = nextBid;
    setActiveBlockBid(nextBid);
  }, [getBlockBidFromSlide]);

  const goToBlock = useCallback(
    (blockBid: string) => {
      const deck = deckRef.current;
      if (!deck || !chatRef.current) {
        return false;
      }

      const section = chatRef.current.querySelector(
        `section[data-generated-block-bid="${blockBid}"]`,
      ) as HTMLElement | null;
      if (!section) {
        return false;
      }

      const indices = deck.getIndices(section);
      deck.slide(indices.h, indices.v, indices.f);
      return true;
    },
    [chatRef],
  );

  const goToNextBlock = useCallback(() => {
    const currentBid = activeBlockBidRef.current;
    if (!currentBid) {
      return false;
    }
    const currentIndex = orderedContentBlockBids.indexOf(currentBid);
    if (currentIndex < 0) {
      return false;
    }

    for (let i = currentIndex + 1; i < orderedContentBlockBids.length; i += 1) {
      const nextBid = orderedContentBlockBids[i];
      if (!nextBid || nextBid === 'loading') {
        continue;
      }
      if (goToBlock(nextBid)) {
        return true;
      }
    }
    return false;
  }, [goToBlock, orderedContentBlockBids]);

  const contentItems = useMemo(
    () =>
      items.filter(
        item => item.type === ChatContentItemType.CONTENT && !!item.content,
      ),
    [items],
  );

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
      progress: false,
      controls: true,
    };

    deckRef.current = new Reveal(chatRef.current, revealOptions);

    deckRef.current.initialize().then(() => {
      syncActiveBlockFromDeck();
    });

    return () => {
      try {
        deckRef.current?.destroy();
        deckRef.current = null;
      } catch (e) {
        console.warn('Reveal.js destroy 調用失敗。');
      }
    };
  }, [chatRef, contentItems.length, isLoading, syncActiveBlockFromDeck]);

  useEffect(() => {
    if (!contentItems.length && deckRef.current) {
      try {
        console.log('销毁reveal实例 (no content)');
        deckRef.current?.destroy();
      } catch (e) {
        console.warn('Reveal.js destroy 調用失敗。');
      } finally {
        deckRef.current = null;
      }
    }
  }, [chatRef, contentItems.length, isLoading, syncActiveBlockFromDeck]);

  useEffect(() => {
    if (contentItems.length > 0 || !deckRef.current) {
      return;
    }
    try {
      deckRef.current?.destroy();
    } catch {
      // Ignore errors when destroying reveal instance
    } finally {
      deckRef.current = null;
    }
  }, [contentItems.length]);

  useEffect(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }

    const handleSlideChanged = () => {
      syncActiveBlockFromDeck();
    };

    deck.on('slidechanged', handleSlideChanged as unknown as EventListener);
    deck.on('ready', handleSlideChanged as unknown as EventListener);

    return () => {
      deck.off('slidechanged', handleSlideChanged as unknown as EventListener);
      deck.off('ready', handleSlideChanged as unknown as EventListener);
    };
  }, [syncActiveBlockFromDeck]);

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
      if (pendingAutoNextRef.current) {
        const moved = goToNextBlock();
        pendingAutoNextRef.current = !moved;
      }

      if (isAudioPlaying) {
        return;
      }

      const targetIndex = Math.max(slides.length - 1, 0);
      deckRef.current.slide(targetIndex);
    } catch {
      // Ignore reveal sync errors
    }
  }, [contentItems, isAudioPlaying, isLoading, goToNextBlock, chatRef]);

  useEffect(() => {
    if (!activeBlockBid) {
      return;
    }
    const item = contentByBid.get(activeBlockBid);
    if (!item) {
      return;
    }
    // Avoid auto-requesting TTS for live blocks that may not be persisted yet.
    // History blocks are loaded from DB and safe to request.
    if (!item.isHistory) {
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
      !requestedAudioBlockBidsRef.current.has(activeBlockBid)
    ) {
      requestedAudioBlockBidsRef.current.add(activeBlockBid);
      onRequestAudioForBlock(activeBlockBid).catch(() => {
        // errors handled by request layer toast; ignore here
      });
    }
  }, [activeBlockBid, contentByBid, onRequestAudioForBlock, previewMode]);

  const handleAudioEnded = useCallback(() => {
    const moved = goToNextBlock();
    if (!moved) {
      pendingAutoNextRef.current = true;
    }
  }, [goToNextBlock]);

  useEffect(() => {
    if (!activeBlockBid) {
      return;
    }
    setIsAudioPlaying(false);
  }, [activeBlockBid]);

  const onPrev = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    deck.prev();
  }, []);

  const onNext = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    deck.next();
  }, []);

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
            contentItems.map((item, idx) => {
              const baseKey = item.generated_block_bid || `${item.type}-${idx}`;
              return (
                <ContentIframe
                  key={baseKey}
                  item={item}
                  mobileStyle={mobileStyle}
                  blockBid={item.generated_block_bid}
                  sectionTitle={sectionTitle}
                />
              );
            })}
        </div>
      </div>
      {activeContentItem ? (
        <div className='listen-audio-controls'>
          <AudioPlayer
            key={activeBlockBid ?? 'listen-audio'}
            audioUrl={activeContentItem.audioUrl}
            streamingSegments={activeContentItem.audioSegments}
            isStreaming={Boolean(activeContentItem.isAudioStreaming)}
            alwaysVisible={true}
            disabled={previewMode}
            onRequestAudio={
              !previewMode && onRequestAudioForBlock && activeBlockBid
                ? () => onRequestAudioForBlock(activeBlockBid)
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
        onNext={onNext}
      />
    </div>
  );
};

ListenModeRenderer.displayName = 'ListenModeRenderer';

export default memo(ListenModeRenderer);

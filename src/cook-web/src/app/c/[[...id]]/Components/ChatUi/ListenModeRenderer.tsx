import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ListenPlayer from './ListenPlayer';
import { cn } from '@/lib/utils';
import type Reveal from 'reveal.js';
import 'reveal.js/dist/reveal.css';
import 'reveal.js/dist/theme/white.css';
import ContentIframe from './ContentIframe';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import './ListenModeRenderer.scss';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import type { ListenSlideData } from '@/c-api/studyV2';
import {
  useListenAudioSequence,
  useListenContentData,
  useListenPpt,
} from './useListenMode';

interface ListenModeRendererProps {
  items: ChatContentItem[];
  backendSlides?: ListenSlideData[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  containerClassName?: string;
  isLoading?: boolean;
  sectionTitle?: string;
  previewMode?: boolean;
  onRequestAudioForBlock?: (
    blockBid: string,
    audioPosition?: number,
  ) => Promise<any>;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
}

const hasInteractionResponse = (
  interaction: ChatContentItem | null | undefined,
) => {
  if (!interaction) {
    return false;
  }
  const hasSelectedValues = Array.isArray(interaction.defaultSelectedValues)
    ? interaction.defaultSelectedValues.some(value => String(value).trim())
    : false;
  if (hasSelectedValues) {
    return true;
  }
  if ((interaction.defaultButtonText || '').trim()) {
    return true;
  }
  if ((interaction.defaultInputText || '').trim()) {
    return true;
  }
  return false;
};

const ListenModeRenderer = ({
  items,
  backendSlides,
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
  const currentPptPageRef = useRef<number>(0);
  const activeBlockBidRef = useRef<string | null>(null);
  const pendingAutoNextRef = useRef(false);
  const shouldStartSequenceRef = useRef(false);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [dismissedInteractionBids, setDismissedInteractionBids] = useState<
    Set<string>
  >(() => new Set());

  const {
    orderedContentBlockBids,
    slideItems,
    interactionByPage,
    audioAndInteractionList,
    contentByBid,
    audioContentByBid,
    firstContentItem,
  } = useListenContentData(items, backendSlides);
  const hasAnyTimelineItem = useMemo(
    () =>
      slideItems.length > 0 ||
      items.some(item => item.type === ChatContentItemType.INTERACTION),
    [items, slideItems],
  );

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

  const emptySlideBlockBid = useMemo(
    () =>
      firstContentItem?.generated_block_bid
        ? `empty-ppt-${firstContentItem.generated_block_bid}`
        : 'empty-ppt',
    [firstContentItem],
  );

  const shouldRenderEmptyPpt = useMemo(() => {
    if (isLoading) {
      return false;
    }
    return !hasAnyTimelineItem;
  }, [hasAnyTimelineItem, isLoading]);

  const handleResetSequence = useCallback(() => {
    shouldStartSequenceRef.current = true;
  }, []);

  const {
    audioPlayerRef,
    activeContentItem,
    activeAudioBlockBid,
    activeAudioPosition,
    activeSequencePage,
    sequenceInteraction,
    isAudioSequenceActive,
    isAudioPlayerBusy,
    audioSequenceToken,
    handleAudioEnded,
    handleAudioError,
    handlePlay,
    handlePause,
    continueAfterInteraction,
    startSequenceFromIndex,
    startSequenceFromPage,
  } = useListenAudioSequence({
    audioAndInteractionList,
    deckRef,
    currentPptPageRef,
    activeBlockBidRef,
    pendingAutoNextRef,
    shouldStartSequenceRef,
    contentByBid,
    audioContentByBid,
    previewMode,
    shouldRenderEmptyPpt,
    getNextContentBid,
    goToBlock,
    resolveContentBid,
    isAudioPlaying,
    setIsAudioPlaying,
  });

  const activeAudioTrack = useMemo(() => {
    if (!activeContentItem) {
      return null;
    }
    const track =
      activeContentItem.audioTracksByPosition?.[activeAudioPosition];
    const persistedMatches = (activeContentItem.audios || []).filter(
      audio => (audio.position ?? 0) === activeAudioPosition,
    );
    const persisted = persistedMatches[persistedMatches.length - 1];
    return {
      audioUrl:
        track?.audioUrl ??
        persisted?.audio_url ??
        (activeAudioPosition === 0 ? activeContentItem.audioUrl : undefined),
      streamingSegments:
        track?.audioSegments ??
        (activeAudioPosition === 0 ? activeContentItem.audioSegments : []),
      isStreaming:
        track?.isAudioStreaming ??
        (activeAudioPosition === 0
          ? Boolean(activeContentItem.isAudioStreaming)
          : false),
    };
  }, [activeAudioPosition, activeContentItem]);

  const latestAudioSequenceTokenRef = useRef(audioSequenceToken);
  useEffect(() => {
    latestAudioSequenceTokenRef.current = audioSequenceToken;
  }, [audioSequenceToken]);

  const handleAudioPlayStateChange = useCallback(
    (token: number, nextIsPlaying: boolean) => {
      if (token !== latestAudioSequenceTokenRef.current) {
        return;
      }
      setIsAudioPlaying(nextIsPlaying);
    },
    [],
  );

  const handleAudioEndedWithToken = useCallback(
    (token: number) => {
      handleAudioEnded(token);
    },
    [handleAudioEnded],
  );

  const handleAudioErrorWithToken = useCallback(
    (token: number) => {
      handleAudioError(token);
    },
    [handleAudioError],
  );

  const { currentInteraction, isPrevDisabled, isNextDisabled, goPrev, goNext } =
    useListenPpt({
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
      isAudioSequenceActive,
      isAudioPlayerBusy,
      shouldRenderEmptyPpt,
      onResetSequence: handleResetSequence,
      getNextContentBid,
      goToBlock,
      resolveContentBid,
    });

  useEffect(() => {
    setDismissedInteractionBids(prev => {
      if (!prev.size) {
        return prev;
      }
      const existingInteractionBids = new Set(
        items
          .filter(
            item =>
              item.type === ChatContentItemType.INTERACTION &&
              Boolean(item.generated_block_bid),
          )
          .map(item => item.generated_block_bid),
      );
      const next = new Set(
        Array.from(prev).filter(bid => existingInteractionBids.has(bid)),
      );
      if (next.size === prev.size) {
        return prev;
      }
      return next;
    });
  }, [items]);

  const audioList = useMemo(
    () =>
      audioAndInteractionList.flatMap(item =>
        item.type === ChatContentItemType.CONTENT ? [item] : [],
      ),
    [audioAndInteractionList],
  );

  const audioContentSequence = useMemo(
    () =>
      audioAndInteractionList.flatMap((item, index) =>
        item.type === ChatContentItemType.CONTENT ? [{ item, index }] : [],
      ),
    [audioAndInteractionList],
  );

  const pagesWithAudio = useMemo(() => {
    const pages = new Set<number>();
    audioAndInteractionList.forEach(item => {
      if (item.type !== ChatContentItemType.CONTENT) {
        return;
      }
      pages.add(item.page);
    });
    return pages;
  }, [audioAndInteractionList]);

  const resolveAudioSequenceIndexByDirection = useCallback(
    (page: number, direction: -1 | 1) => {
      if (!audioContentSequence.length) {
        return null;
      }
      let currentIndex = -1;
      if (activeAudioBlockBid) {
        currentIndex = audioContentSequence.findIndex(
          entry =>
            entry.item.generated_block_bid === activeAudioBlockBid &&
            (entry.item.audioPosition ?? 0) === activeAudioPosition,
        );
      }
      if (currentIndex < 0) {
        for (let i = audioContentSequence.length - 1; i >= 0; i -= 1) {
          if (audioContentSequence[i].item.page <= page) {
            currentIndex = i;
            break;
          }
        }
      }
      if (direction === -1) {
        const targetIndex = currentIndex - 1;
        if (targetIndex < 0) {
          return null;
        }
        return audioContentSequence[targetIndex].index;
      }
      const targetIndex = currentIndex < 0 ? 0 : currentIndex + 1;
      if (targetIndex >= audioContentSequence.length) {
        return null;
      }
      return audioContentSequence[targetIndex].index;
    },
    [audioContentSequence, activeAudioBlockBid, activeAudioPosition],
  );

  const onPrev = useCallback(() => {
    if (!isAudioSequenceActive) {
      const prevPage = goPrev();
      if (typeof prevPage === 'number' && pagesWithAudio.has(prevPage)) {
        startSequenceFromPage(prevPage);
      }
      return;
    }
    const currentPage =
      deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
    const targetSequenceIndex = resolveAudioSequenceIndexByDirection(
      currentPage,
      -1,
    );
    if (typeof targetSequenceIndex === 'number') {
      startSequenceFromIndex(targetSequenceIndex);
      return;
    }
    const nextPage = goPrev();
    if (typeof nextPage === 'number') {
      startSequenceFromPage(nextPage);
    }
  }, [
    deckRef,
    currentPptPageRef,
    isAudioSequenceActive,
    goPrev,
    pagesWithAudio,
    startSequenceFromPage,
    resolveAudioSequenceIndexByDirection,
    startSequenceFromIndex,
  ]);

  const currentSequencePage =
    deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
  const prevSequenceIndex = resolveAudioSequenceIndexByDirection(
    currentSequencePage,
    -1,
  );
  const nextSequenceIndex = resolveAudioSequenceIndexByDirection(
    currentSequencePage,
    1,
  );
  const prevControlDisabled =
    isPrevDisabled && typeof prevSequenceIndex !== 'number';
  const nextControlDisabled =
    Boolean(sequenceInteraction) ||
    (isNextDisabled && typeof nextSequenceIndex !== 'number');

  const onNext = useCallback(() => {
    if (sequenceInteraction) {
      // Interaction blocks progression until learner submits.
      return;
    }
    if (!isAudioSequenceActive) {
      const nextPage = goNext();
      if (typeof nextPage === 'number' && pagesWithAudio.has(nextPage)) {
        startSequenceFromPage(nextPage);
      }
      return;
    }
    const currentPage =
      deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
    const targetSequenceIndex = resolveAudioSequenceIndexByDirection(
      currentPage,
      1,
    );
    if (typeof targetSequenceIndex === 'number') {
      startSequenceFromIndex(targetSequenceIndex);
      return;
    }
    const nextPage = goNext();
    if (typeof nextPage === 'number') {
      startSequenceFromPage(nextPage);
    }
  }, [
    deckRef,
    currentPptPageRef,
    isAudioSequenceActive,
    goNext,
    pagesWithAudio,
    startSequenceFromPage,
    resolveAudioSequenceIndexByDirection,
    sequenceInteraction,
    startSequenceFromIndex,
  ]);

  const currentInteractionPage = useMemo(() => {
    if (!currentInteraction) {
      return -1;
    }
    for (const [page, queue] of interactionByPage.entries()) {
      if (queue.includes(currentInteraction)) {
        return page;
      }
    }
    return -1;
  }, [currentInteraction, interactionByPage]);

  const hasAudioForCurrentPage = useMemo(() => {
    if (currentInteractionPage === -1) {
      return false;
    }
    return audioAndInteractionList.some(
      item =>
        item.page === currentInteractionPage &&
        item.type === ChatContentItemType.CONTENT,
    );
  }, [currentInteractionPage, audioAndInteractionList]);

  const shouldHideFallbackInteraction =
    hasAudioForCurrentPage && !isAudioSequenceActive;

  const visibleSequenceInteraction = useMemo(() => {
    if (!sequenceInteraction) {
      return null;
    }
    if (
      sequenceInteraction.generated_block_bid &&
      dismissedInteractionBids.has(sequenceInteraction.generated_block_bid)
    ) {
      return null;
    }
    if (hasInteractionResponse(sequenceInteraction)) {
      return null;
    }
    return sequenceInteraction;
  }, [dismissedInteractionBids, sequenceInteraction]);

  const latestPendingInteraction = useMemo(() => {
    for (let i = items.length - 1; i >= 0; i -= 1) {
      const item = items[i];
      if (item.type !== ChatContentItemType.INTERACTION) {
        continue;
      }
      if (
        item.generated_block_bid &&
        dismissedInteractionBids.has(item.generated_block_bid)
      ) {
        continue;
      }
      if (hasInteractionResponse(item)) {
        continue;
      }
      return item;
    }
    return null;
  }, [dismissedInteractionBids, items]);

  const listenPlayerInteraction = isAudioSequenceActive
    ? visibleSequenceInteraction
    : latestPendingInteraction;
  const latestPendingInteractionBid =
    latestPendingInteraction?.generated_block_bid ?? null;
  const isLatestInteractionEditable = Boolean(
    listenPlayerInteraction &&
    (latestPendingInteractionBid
      ? listenPlayerInteraction.generated_block_bid ===
        latestPendingInteractionBid
      : listenPlayerInteraction === latestPendingInteraction),
  );
  const interactionReadonly = listenPlayerInteraction
    ? !isLatestInteractionEditable
    : true;
  const handleListenInteractionSend = useCallback(
    (content: OnSendContentParams, blockBid: string) => {
      if (blockBid) {
        setDismissedInteractionBids(prev => {
          if (prev.has(blockBid)) {
            return prev;
          }
          const next = new Set(prev);
          next.add(blockBid);
          return next;
        });
      }
      if (sequenceInteraction) {
        continueAfterInteraction();
      }
      onSend?.(content, blockBid);
    },
    [onSend, sequenceInteraction, continueAfterInteraction],
  );

  useEffect(() => {
    // console.log('listen-render-state', {
    //   isLoading,
    //   audioSequenceToken,
    //   isAudioSequenceActive,
    //   currentInteractionBid: currentInteraction?.generated_block_bid ?? null,
    //   sequenceInteractionBid: sequenceInteraction?.generated_block_bid ?? null,
    //   listenInteractionBid:
    //     listenPlayerInteraction?.generated_block_bid ?? null,
    //   hasAudioForCurrentPage,
    //   shouldHideFallbackInteraction,
    // });
  }, [
    isLoading,
    audioSequenceToken,
    isAudioSequenceActive,
    currentInteraction?.generated_block_bid,
    sequenceInteraction?.generated_block_bid,
    listenPlayerInteraction?.generated_block_bid,
    activeSequencePage,
    hasAudioForCurrentPage,
    shouldHideFallbackInteraction,
  ]);

  return (
    <div
      className={cn(
        containerClassName,
        'listen-reveal-wrapper',
        mobileStyle ? 'mobile' : '',
      )}
      style={{ background: '#F7F9FF', position: 'relative' }}
    >
      <div
        className={cn('reveal', 'listen-reveal')}
        ref={chatRef}
      >
        <div className='slides'>
          {!isLoading &&
            slideItems.map(({ item, segments }, idx) => {
              const baseKey = `${item.generated_block_bid || item.type}-${idx}`;
              // console.log('segments', baseKey, segments);
              return (
                <ContentIframe
                  key={baseKey}
                  // item={item}
                  segments={segments}
                  mobileStyle={mobileStyle}
                  blockBid={item.generated_block_bid}
                />
              );
            })}
          {shouldRenderEmptyPpt ? (
            <section
              className={cn(
                'present text-center',
                mobileStyle ? 'mobile-empty-slide' : '',
              )}
              data-generated-block-bid={emptySlideBlockBid}
            >
              <div className='w-full h-full font-bold flex items-center justify-center text-primary '>
                {sectionTitle}
              </div>
            </section>
          ) : null}
        </div>
      </div>
      {audioList.length ? (
        <div className={cn('listen-audio-controls', 'hidden')}>
          <AudioPlayer
            ref={audioPlayerRef}
            key={`${activeAudioBlockBid ?? 'listen-audio'}-${audioSequenceToken}`}
            audioUrl={activeAudioTrack?.audioUrl}
            streamingSegments={activeAudioTrack?.streamingSegments}
            isStreaming={activeAudioTrack?.isStreaming}
            alwaysVisible={true}
            onRequestAudio={
              onRequestAudioForBlock && activeAudioBlockBid
                ? () =>
                    onRequestAudioForBlock(
                      activeAudioBlockBid,
                      activeAudioPosition,
                    )
                : undefined
            }
            disabled={previewMode}
            autoPlay={!previewMode}
            onPlayStateChange={nextIsPlaying =>
              handleAudioPlayStateChange(audioSequenceToken, nextIsPlaying)
            }
            onEnded={() => handleAudioEndedWithToken(audioSequenceToken)}
            onError={() => handleAudioErrorWithToken(audioSequenceToken)}
            className='hidden'
          />
        </div>
      ) : null}
      <ListenPlayer
        onPrev={onPrev}
        onPlay={handlePlay}
        onPause={handlePause}
        onNext={onNext}
        prevDisabled={prevControlDisabled}
        nextDisabled={nextControlDisabled}
        isAudioPlaying={isAudioPlaying}
        interaction={listenPlayerInteraction}
        interactionReadonly={interactionReadonly}
        onSend={handleListenInteractionSend}
        mobileStyle={mobileStyle}
      />
    </div>
  );
};

ListenModeRenderer.displayName = 'ListenModeRenderer';

export default memo(ListenModeRenderer);

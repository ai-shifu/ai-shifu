import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ListenPlayer from './ListenPlayer';
import { cn } from '@/lib/utils';
import type Reveal from 'reveal.js';
import 'reveal.js/dist/reveal.css';
import 'reveal.js/dist/theme/white.css';
import ContentIframe from './ContentIframe';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import './ListenModeRenderer.scss';
import { AudioPlayerList } from '@/components/audio/AudioPlayerList';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import {
  resolveListenAudioSourceBid,
  useListenAudioSequence,
  useListenContentData,
  useListenPpt,
} from './useListenMode';

interface ListenModeRendererProps {
  items: ChatContentItem[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
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
  isLoading = false,
  sectionTitle,
  previewMode = false,
  onRequestAudioForBlock,
  onSend,
}: ListenModeRendererProps) => {
  const isAudioDebugEnabled = process.env.NODE_ENV !== 'production';
  const deckRef = useRef<Reveal.Api | null>(null);
  const currentPptPageRef = useRef<number>(0);
  const activeBlockBidRef = useRef<string | null>(null);
  const pendingAutoNextRef = useRef(false);
  const shouldStartSequenceRef = useRef(false);
  const [sequenceStartSignal, setSequenceStartSignal] = useState(0);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);

  const {
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
  } = useListenContentData(items);

  const resolveContentBid = useCallback((blockBid: string | null) => {
    if (!blockBid) {
      return null;
    }
    const sourceBid = resolveListenAudioSourceBid(blockBid);
    if (!sourceBid) {
      return null;
    }
    const emptyPrefix = 'empty-ppt-';
    if (!sourceBid.startsWith(emptyPrefix)) {
      return sourceBid;
    }
    const resolved = sourceBid.slice(emptyPrefix.length);
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
    return slideItems.length === 0;
  }, [isLoading, slideItems.length]);

  const handleResetSequence = useCallback(() => {
    shouldStartSequenceRef.current = true;
    setSequenceStartSignal(prev => prev + 1);
  }, []);

  const {
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
    startSequenceFromPage,
  } = useListenAudioSequence({
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
    setIsAudioPlaying,
  });

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
      activeContentItem,
      shouldRenderEmptyPpt,
      onResetSequence: handleResetSequence,
      getNextContentBid,
      goToBlock,
      resolveContentBid,
    });

  const audioList = useMemo(
    () =>
      audioAndInteractionList.flatMap(item =>
        item.type === ChatContentItemType.CONTENT ? [item] : [],
      ),
    [audioAndInteractionList],
  );

  const rendererAudioListDebug = useMemo(
    () =>
      audioList.map((item, index) => ({
        index,
        page: item.page,
        generatedBlockBid: item.generated_block_bid ?? null,
        sourceGeneratedBlockBid: item.sourceGeneratedBlockBid ?? null,
        sequenceKind: item.sequenceKind,
        audioPosition: item.audioPosition ?? null,
        listenSlideId: item.listenSlideId ?? null,
        hasAudioUrl: Boolean(item.audioUrl),
        isAudioStreaming: Boolean(item.isAudioStreaming),
        audioSegments: item.audioSegments?.length ?? 0,
        audioTracks: item.audioTracks?.length ?? 0,
      })),
    [audioList],
  );

  const rendererSlideListDebug = useMemo(() => {
    let pageCursor = 0;
    const slideList: Array<Record<string, any>> = [];

    slideItems.forEach((slideItem, slideIndex) => {
      slideItem.segments.forEach((segment, segmentIndex) => {
        const page = pageCursor + segmentIndex;
        const interaction = interactionByPage.get(page);
        slideList.push({
          page,
          slideIndex,
          segmentIndex,
          segmentType: segment.type,
          blockBid: slideItem.item.generated_block_bid ?? null,
          interactionBid: interaction?.generated_block_bid ?? null,
          interactionType: interaction?.type ?? null,
          interactionParentBid: interaction?.parent_block_bid ?? null,
        });
      });
      pageCursor += slideItem.segments.length;
    });

    return slideList;
  }, [interactionByPage, slideItems]);

  const onPrev = useCallback(() => {
    const nextPage = goPrev();
    if (typeof nextPage === 'number') {
      startSequenceFromPage(nextPage);
    }
  }, [goPrev, startSequenceFromPage]);
  const prevControlDisabled = isPrevDisabled;
  const nextControlDisabled = isNextDisabled;

  const onNext = useCallback(() => {
    const nextPage = goNext();
    if (typeof nextPage === 'number') {
      startSequenceFromPage(nextPage);
    }
  }, [goNext, startSequenceFromPage]);

  const currentInteractionPage = useMemo(() => {
    if (!currentInteraction) {
      return -1;
    }
    for (const [page, item] of interactionByPage.entries()) {
      if (item === currentInteraction) {
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
    hasAudioForCurrentPage &&
    audioSequenceToken === 0 &&
    !isAudioSequenceActive;

  const listenPlayerInteraction = isAudioSequenceActive
    ? sequenceInteraction
    : shouldHideFallbackInteraction
      ? null
      : currentInteraction;
  const isLatestInteractionEditable = Boolean(
    listenPlayerInteraction?.generated_block_bid &&
    lastItemIsInteraction &&
    lastInteractionBid &&
    listenPlayerInteraction.generated_block_bid === lastInteractionBid,
  );
  const interactionReadonly = listenPlayerInteraction
    ? !isLatestInteractionEditable
    : true;

  useEffect(() => {
    if (!isAudioDebugEnabled) {
      return;
    }
    console.log('[listen-audio-debug] listen-renderer-current-audio-list', {
      total: rendererAudioListDebug.length,
      list: rendererAudioListDebug,
      activeSequenceBlockBid,
      activeAudioBlockBid,
      isAudioSequenceActive,
      audioSequenceToken,
    });
    console.log('[listen-audio-debug] listen-renderer-current-slide-list', {
      total: rendererSlideListDebug.length,
      list: rendererSlideListDebug,
    });
  }, [
    activeAudioBlockBid,
    activeSequenceBlockBid,
    audioSequenceToken,
    isAudioDebugEnabled,
    isAudioSequenceActive,
    rendererAudioListDebug,
    rendererSlideListDebug,
  ]);

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
    hasAudioForCurrentPage,
    shouldHideFallbackInteraction,
  ]);

  return (
    <div
      className={cn('listen-reveal-wrapper', mobileStyle ? 'mobile' : '')}
      style={{ background: '#F7F9FF', position: 'relative' }}
    >
      <div
        className={cn('reveal', 'listen-reveal')}
        ref={chatRef}
      >
        <div className='slides'>
          {!isLoading &&
            slideItems.map(({ item, segments }, idx) => {
              const baseKey = item.generated_block_bid || `${item.type}-${idx}`;
              // console.log('segments', baseKey, segments);
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
          <AudioPlayerList
            ref={audioPlayerRef}
            audioList={audioList}
            sequenceBlockBid={activeSequenceBlockBid}
            isSequenceActive={isAudioSequenceActive}
            disabled={previewMode}
            onRequestAudio={
              !previewMode && onRequestAudioForBlock && activeAudioBlockBid
                ? () => onRequestAudioForBlock(activeAudioBlockBid)
                : undefined
            }
            autoPlay={!previewMode}
            onPlayStateChange={setIsAudioPlaying}
            onEnded={handleAudioEnded}
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
        onSend={onSend}
        mobileStyle={mobileStyle}
      />
    </div>
  );
};

ListenModeRenderer.displayName = 'ListenModeRenderer';

export default memo(ListenModeRenderer);

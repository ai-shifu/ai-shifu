import { memo, useCallback, useMemo, useRef, useState } from 'react';
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
  useListenAudioSequence,
  useListenContentData,
  useListenPpt,
} from './useListenMode';

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
  const currentPptPageRef = useRef<number>(0);
  const activeBlockBidRef = useRef<string | null>(null);
  const pendingAutoNextRef = useRef(false);
  const shouldStartSequenceRef = useRef(false);
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
    return slideItems.length === 0;
  }, [isLoading, slideItems.length]);

  const handleResetSequence = useCallback(() => {
    shouldStartSequenceRef.current = true;
  }, []);

  const {
    audioPlayerRef,
    activeContentItem,
    activeAudioBlockBid,
    sequenceInteraction,
    isAudioSequenceActive,
    audioSequenceToken,
    handleAudioEnded,
    handlePlay,
    handlePause,
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

  const audioContentSequence = useMemo(
    () =>
      audioAndInteractionList.flatMap((item, index) =>
        item.type === ChatContentItemType.CONTENT ? [{ item, index }] : [],
      ),
    [audioAndInteractionList],
  );

  const audioList = useMemo(
    () => audioContentSequence.map(entry => entry.item),
    [audioContentSequence],
  );

  const resolveAudioSequenceIndexByDirection = useCallback(
    (page: number, direction: -1 | 1) => {
      if (!audioContentSequence.length) {
        return null;
      }
      let currentIndex = -1;
      if (activeAudioBlockBid) {
        currentIndex = audioContentSequence.findIndex(
          entry => entry.item.generated_block_bid === activeAudioBlockBid,
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
    [audioContentSequence, activeAudioBlockBid],
  );

  const onPrev = useCallback(() => {
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
    resolveAudioSequenceIndexByDirection,
    goPrev,
    startSequenceFromIndex,
    startSequenceFromPage,
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
    isNextDisabled && typeof nextSequenceIndex !== 'number';

  const onNext = useCallback(() => {
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
    resolveAudioSequenceIndexByDirection,
    goNext,
    startSequenceFromIndex,
    startSequenceFromPage,
  ]);

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
            sequenceBlockBid={activeAudioBlockBid}
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

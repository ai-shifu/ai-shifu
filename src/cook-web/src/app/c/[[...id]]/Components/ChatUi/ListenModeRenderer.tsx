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
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import {
  resolveListenAudioSourceBid,
  useListenAudioSequence,
  useListenContentData,
  useListenPpt,
} from './useListenMode';

type UserActivationLike = {
  hasBeenActive?: boolean;
  isActive?: boolean;
};

const hasBrowserUserActivation = () => {
  if (typeof window === 'undefined') {
    return false;
  }
  const navigatorActivation = (
    navigator as Navigator & { userActivation?: UserActivationLike }
  ).userActivation;
  if (navigatorActivation) {
    return Boolean(
      navigatorActivation.hasBeenActive || navigatorActivation.isActive,
    );
  }
  const documentActivation = (
    document as Document & { userActivation?: UserActivationLike }
  ).userActivation;
  return Boolean(
    documentActivation?.hasBeenActive || documentActivation?.isActive,
  );
};

interface ListenModeRendererProps {
  items: ChatContentItem[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  isLoading?: boolean;
  sectionTitle?: string;
  lessonId?: string;
  lessonStatus?: string;
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
  lessonId,
  lessonStatus,
  previewMode = false,
  onRequestAudioForBlock,
  onSend,
}: ListenModeRendererProps) => {
  const deckRef = useRef<Reveal.Api | null>(null);
  const currentPptPageRef = useRef<number>(0);
  const activeBlockBidRef = useRef<string | null>(null);
  const pendingAutoNextRef = useRef(false);
  const shouldStartSequenceRef = useRef(false);
  const [sequenceStartSignal, setSequenceStartSignal] = useState(0);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [isSlideNavigationLocked, setIsSlideNavigationLocked] = useState(false);
  const [hasUserStartedPlayback, setHasUserStartedPlayback] = useState(false);
  const [hasPageInteraction, setHasPageInteraction] = useState(() =>
    hasBrowserUserActivation(),
  );

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

  const allowAutoPlayback = useMemo(
    () => {
      if (lessonStatus !== LESSON_STATUS_VALUE.PREPARE_LEARNING) {
        return true;
      }
      return (
        hasUserStartedPlayback ||
        hasPageInteraction ||
        hasBrowserUserActivation()
      );
    },
    [hasPageInteraction, hasUserStartedPlayback, lessonStatus],
  );

  useEffect(() => {
    if (hasPageInteraction) {
      return;
    }
    // Capture any trusted user gesture to unlock autoplay on restricted browsers.
    const markPageInteracted = () => {
      setHasPageInteraction(true);
    };
    const syncBrowserActivation = () => {
      if (hasBrowserUserActivation()) {
        setHasPageInteraction(true);
      }
    };

    syncBrowserActivation();
    window.addEventListener('pointerdown', markPageInteracted, {
      capture: true,
      passive: true,
    });
    window.addEventListener('touchstart', markPageInteracted, {
      capture: true,
      passive: true,
    });
    window.addEventListener('keydown', markPageInteracted, true);
    document.addEventListener('visibilitychange', syncBrowserActivation);

    return () => {
      window.removeEventListener('pointerdown', markPageInteracted, true);
      window.removeEventListener('touchstart', markPageInteracted, true);
      window.removeEventListener('keydown', markPageInteracted, true);
      document.removeEventListener('visibilitychange', syncBrowserActivation);
    };
  }, [hasPageInteraction]);

  useEffect(() => {
    setHasUserStartedPlayback(false);
    setIsSlideNavigationLocked(false);
  }, [lessonId]);

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
    allowAutoPlayback,
    isAudioPlaying,
    setIsAudioPlaying,
  });

  const { isPrevDisabled, isNextDisabled, goPrev, goNext } = useListenPpt({
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

  const onPlay = useCallback(() => {
    setHasUserStartedPlayback(true);
    setHasPageInteraction(true);
    setIsSlideNavigationLocked(false);
    handlePlay();
  }, [handlePlay]);

  const onPause = useCallback(
    (traceId: string) => {
      setIsSlideNavigationLocked(true);
      handlePause(traceId);
    },
    [handlePause],
  );

  const listenPlayerInteraction = sequenceInteraction;
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
        onPlay={onPlay}
        onPause={onPause}
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

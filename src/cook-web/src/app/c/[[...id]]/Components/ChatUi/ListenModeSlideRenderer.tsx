import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { lessonFeedbackInteractionDefaultValueOptions } from '@/c-utils/lesson-feedback-interaction-defaults';
import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';
import { isLessonFeedbackInteractionContent } from '@/c-utils/lesson-feedback-interaction';
import { SYS_INTERACTION_TYPE } from '@/c-api/studyV2';
import { type OnSendContentParams } from 'markdown-flow-ui/renderer';
import { Slide, type Element as SlideElement } from 'markdown-flow-ui/slide';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import {
  resolveListenSlideAudioSource,
  resolveListenSlideElementType,
} from './listenModeUtils';
import {
  buildListenMarkerSequenceKey,
  getListenMarkerIdentityKey,
  reconcileListenPlaybackStepCount,
  type ListenPlaybackState,
} from './listenPlaybackState';
import './ListenModeRenderer.scss';
import { useListenContentData } from './useListenMode';

type ListenSlideElement = SlideElement & {
  blockBid?: string;
  page?: number;
  is_audio_streaming?: boolean;
  isAudioStreaming?: boolean;
};

interface ListenModeSlideRendererProps {
  items: ChatContentItem[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  isLoading?: boolean;
  sectionTitle?: string;
  lessonId?: string;
  lessonStatus?: string;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
  onPlayerVisibilityChange?: (visible: boolean) => void;
  onPlaybackStateChange?: (state: {
    isAudioPlaying: boolean;
    isAudioSequenceActive: boolean;
  }) => void;
}

type ResolveRenderSequence = (params: {
  item: ChatContentItem;
  itemType: 'content' | 'interaction';
  fallbackSequence: number;
}) => number;

const hasListenStepAudio = (element?: SlideElement) => {
  const listenElement = element as ListenSlideElement | undefined;

  return Boolean(
    listenElement?.audio_url ||
    listenElement?.audio_segments?.length ||
    listenElement?.is_audio_streaming ||
    listenElement?.isAudioStreaming,
  );
};

const hasBlockingListenInteraction = (element?: SlideElement) => {
  if (element?.type !== 'interaction') {
    return false;
  }

  const interactionElement = element as ListenSlideElement | undefined;
  const hasUserInput = Boolean(interactionElement?.user_input?.trim());
  const interactionContent =
    typeof interactionElement?.content === 'string'
      ? interactionElement.content
      : '';
  const isSystemInteraction = Object.values(SYS_INTERACTION_TYPE).some(
    interactionType => interactionContent.includes(interactionType),
  );

  return (
    !Boolean(interactionElement?.readonly) &&
    !hasUserInput &&
    !isLessonFeedbackInteractionContent(interactionContent) &&
    !isSystemInteraction
  );
};

const getListenPlaybackSequenceActive = ({
  currentStepIndex,
  totalStepCount,
  currentStepHasAudio,
  currentStepHasBlockingInteraction,
  hasCompletedCurrentStepAudio,
  isAudioPlaying,
  isAudioWaiting,
}: ListenPlaybackState) => {
  if (totalStepCount > 0 && currentStepIndex < 0) {
    return true;
  }

  const hasFutureSteps =
    currentStepIndex >= 0 && currentStepIndex < totalStepCount - 1;
  const hasPendingCurrentStepAudio =
    currentStepHasAudio && !hasCompletedCurrentStepAudio;

  return (
    hasFutureSteps ||
    hasPendingCurrentStepAudio ||
    currentStepHasBlockingInteraction ||
    isAudioPlaying ||
    isAudioWaiting
  );
};

const createEmptyStateElement = (
  sectionTitle: string | undefined,
): ListenSlideElement => ({
  sequence_number: 1,
  type: 'slot',
  content: (
    <div className='flex h-full w-full items-center justify-center text-center text-[40px] font-bold leading-[1.3] text-primary'>
      {sectionTitle}
    </div>
  ),
  is_marker: true,
  is_renderable: true,
  is_new: true,
  blockBid: 'empty-ppt',
  page: 0,
});

const buildSlideElementList = ({
  items,
  sectionTitle,
  interactionInputMap,
  lastInteractionBid,
  lastItemIsInteraction,
  resolveRenderSequence,
}: {
  items: ChatContentItem[];
  sectionTitle?: string;
  interactionInputMap: Record<string, string>;
  lastInteractionBid: string | null;
  lastItemIsInteraction: boolean;
  resolveRenderSequence: ResolveRenderSequence;
}) => {
  let pageCursor = 0;
  let sequenceNumber = 0;
  let hasResolvedFirstContentType = false;
  let hasLeadingTextContentElement = false;
  const elementList: ListenSlideElement[] = [];

  items.forEach(item => {
    if (item.type === ChatContentItemType.CONTENT) {
      const { audioSegments, audioUrl, isAudioStreaming } =
        resolveListenSlideAudioSource(item);
      const contentType = resolveListenSlideElementType(item);

      if (!hasResolvedFirstContentType) {
        hasResolvedFirstContentType = true;
        hasLeadingTextContentElement = contentType === 'text';
      }

      sequenceNumber += 1;
      elementList.push({
        sequence_number: resolveRenderSequence({
          item,
          itemType: 'content',
          fallbackSequence: sequenceNumber,
        }),
        type: contentType,
        content: item.content || '',
        is_marker: item.is_marker ?? true,
        is_renderable: item.is_renderable ?? true,
        is_new: item.is_new ?? true,
        is_speakable:
          item.is_speakable ?? Boolean(audioUrl || audioSegments?.length),
        audio_url: audioUrl,
        is_audio_streaming: isAudioStreaming,
        isAudioStreaming,
        audio_segments: audioSegments,
        blockBid: item.element_bid,
        page: pageCursor,
      });

      pageCursor += 1;
      return;
    }

    if (item.type !== ChatContentItemType.INTERACTION) {
      return;
    }

    if (isLessonFeedbackInteractionContent(item.content)) {
      return;
    }

    // Prefer in-memory interaction state, then fall back to persisted user_input.
    const currentUserInput =
      interactionInputMap[item.element_bid] ?? item.user_input ?? '';
    const isLatestEditable =
      lastItemIsInteraction && item.element_bid === lastInteractionBid;

    sequenceNumber += 1;
    elementList.push({
      sequence_number: resolveRenderSequence({
        item,
        itemType: 'interaction',
        fallbackSequence: sequenceNumber,
      }),
      type: 'interaction',
      content: item.content || '',
      is_marker: item.is_marker ?? true,
      is_renderable: item.is_renderable ?? true,
      is_new: item.is_new ?? true,
      blockBid: item.element_bid,
      page: Math.max(pageCursor - 1, 0),
      user_input: currentUserInput,
      readonly:
        Boolean(item.readonly) ||
        Boolean(currentUserInput) ||
        !isLatestEditable,
    });
  });

  if (!elementList.length) {
    return [createEmptyStateElement(sectionTitle)];
  }

  // Keep a leading placeholder when the first content payload is text.
  if (hasLeadingTextContentElement) {
    const firstSequenceNumber = Number(elementList[0]?.sequence_number ?? 1);
    elementList.unshift({
      ...createEmptyStateElement(sectionTitle),
      sequence_number: Math.max(firstSequenceNumber - 1, 0),
    });
  }

  return elementList;
};

const ListenModeSlideRenderer = ({
  items,
  mobileStyle,
  chatRef,
  isLoading = false,
  sectionTitle,
  lessonId,
  onSend,
  onPlayerVisibilityChange,
  onPlaybackStateChange,
}: ListenModeSlideRendererProps) => {
  const { t } = useTranslation();
  const renderSequenceByStreamKeyRef = useRef<Map<string, number>>(new Map());
  const audioListenerCleanupMapRef = useRef<Map<HTMLAudioElement, () => void>>(
    new Map(),
  );
  const audioWaitingStateMapRef = useRef<Map<HTMLAudioElement, boolean>>(
    new Map(),
  );
  const [interactionInputMap, setInteractionInputMap] = useState<
    Record<string, string>
  >({});
  const [playbackState, setPlaybackState] = useState<ListenPlaybackState>({
    currentStepIndex: -1,
    totalStepCount: 0,
    currentStepHasAudio: false,
    currentStepHasBlockingInteraction: false,
    hasCompletedCurrentStepAudio: false,
    isAudioPlaying: false,
    isAudioWaiting: false,
  });
  const { lastInteractionBid, lastItemIsInteraction } =
    useListenContentData(items);

  const elementList = useMemo(() => {
    const sequenceMap = renderSequenceByStreamKeyRef.current;
    const activeStreamKeys = new Set<string>();
    const activeSequenceNumbers = new Set<number>();

    const hasOccupiedSequenceNumber = (
      nextSequenceNumber: number,
      currentStreamKey: string,
    ) => {
      if (activeSequenceNumbers.has(nextSequenceNumber)) {
        return true;
      }

      for (const [streamKey, sequenceNumber] of sequenceMap.entries()) {
        if (streamKey === currentStreamKey) {
          continue;
        }
        if (sequenceNumber === nextSequenceNumber) {
          return true;
        }
      }

      return false;
    };

    const resolveRenderSequence: ResolveRenderSequence = ({
      item,
      itemType,
      fallbackSequence,
    }) => {
      const streamBid = item.element_bid || '';
      const streamKey = streamBid
        ? `${itemType}:${streamBid}`
        : `${itemType}:fallback-${fallbackSequence}`;
      activeStreamKeys.add(streamKey);

      const existingSequence = sequenceMap.get(streamKey);
      if (typeof existingSequence === 'number') {
        activeSequenceNumbers.add(existingSequence);
        return existingSequence;
      }

      const incomingSequence = Number(item.sequence_number);
      const hasIncomingSequence =
        Number.isFinite(incomingSequence) && incomingSequence > 0;
      let nextSequence = hasIncomingSequence
        ? incomingSequence
        : fallbackSequence;

      while (hasOccupiedSequenceNumber(nextSequence, streamKey)) {
        nextSequence += 1;
      }

      sequenceMap.set(streamKey, nextSequence);
      activeSequenceNumbers.add(nextSequence);

      return nextSequence;
    };

    const nextElementList = buildSlideElementList({
      items,
      sectionTitle,
      interactionInputMap,
      lastInteractionBid,
      lastItemIsInteraction,
      resolveRenderSequence,
    });

    for (const streamKey of Array.from(sequenceMap.keys())) {
      if (activeStreamKeys.has(streamKey)) {
        continue;
      }
      sequenceMap.delete(streamKey);
    }

    return nextElementList;
  }, [
    interactionInputMap,
    items,
    lastInteractionBid,
    lastItemIsInteraction,
    sectionTitle,
  ]);
  const markerStepCount = useMemo(
    () => elementList.filter(element => Boolean(element.is_marker)).length,
    [elementList],
  );
  const markerStepList = useMemo(
    () => elementList.filter(element => Boolean(element.is_marker)),
    [elementList],
  );
  const markerSequenceKey = useMemo(
    () => buildListenMarkerSequenceKey(markerStepList),
    [markerStepList],
  );
  const currentMarkerStepElement = useMemo(() => {
    if (playbackState.currentStepIndex < 0) {
      return undefined;
    }

    return markerStepList[playbackState.currentStepIndex];
  }, [markerStepList, playbackState.currentStepIndex]);
  const currentMarkerStepKey = useMemo(() => {
    const markerIdentityKey = getListenMarkerIdentityKey(
      currentMarkerStepElement,
    );

    if (!markerIdentityKey) {
      return '';
    }

    return [
      markerIdentityKey,
      typeof currentMarkerStepElement?.content === 'string'
        ? currentMarkerStepElement.content
        : '',
    ].join(':');
  }, [currentMarkerStepElement]);
  const previousMarkerStepKeyRef = useRef('');

  const shouldRenderEmptyPpt =
    !isLoading &&
    elementList.length === 1 &&
    elementList[0]?.blockBid === 'empty-ppt';

  const handleInteractionSend = useCallback(
    (content: OnSendContentParams, element?: SlideElement) => {
      const blockBid = (element as ListenSlideElement | undefined)?.blockBid;
      if (!blockBid) {
        return;
      }

      const submittedValue = resolveInteractionSubmission(content).userInput;
      if (submittedValue) {
        setInteractionInputMap(prev => ({
          ...prev,
          [blockBid]: submittedValue,
        }));
      }

      onSend?.(content, blockBid);
    },
    [onSend],
  );

  const handlePlayerVisibilityChange = useCallback(
    (visible: boolean) => {
      onPlayerVisibilityChange?.(visible);
    },
    [onPlayerVisibilityChange],
  );

  const syncMediaPlaybackState = useCallback(() => {
    const trackedAudioElements = Array.from(
      audioWaitingStateMapRef.current.keys(),
    );
    const nextIsAudioPlaying = trackedAudioElements.some(
      audioElement =>
        Boolean(audioElement.currentSrc) &&
        !audioElement.paused &&
        !audioElement.ended,
    );
    const nextIsAudioWaiting = trackedAudioElements.some(
      audioElement =>
        Boolean(audioElement.currentSrc) &&
        !audioElement.ended &&
        Boolean(audioWaitingStateMapRef.current.get(audioElement)),
    );

    setPlaybackState(prevState => {
      if (
        prevState.isAudioPlaying === nextIsAudioPlaying &&
        prevState.isAudioWaiting === nextIsAudioWaiting
      ) {
        return prevState;
      }

      return {
        ...prevState,
        isAudioPlaying: nextIsAudioPlaying,
        isAudioWaiting: nextIsAudioWaiting,
      };
    });
  }, []);

  useEffect(() => {
    const container = chatRef.current;
    if (!container) {
      return;
    }

    const registerAudioElement = (audioElement: HTMLAudioElement) => {
      if (audioListenerCleanupMapRef.current.has(audioElement)) {
        return;
      }

      const setWaitingState = (isWaiting: boolean) => {
        audioWaitingStateMapRef.current.set(audioElement, isWaiting);
      };
      const handlePlaybackStarted = () => {
        setWaitingState(false);
        setPlaybackState(prevState => ({
          ...prevState,
          hasCompletedCurrentStepAudio: false,
        }));
        syncMediaPlaybackState();
      };
      const handlePlaybackWaiting = () => {
        setWaitingState(true);
        setPlaybackState(prevState => ({
          ...prevState,
          hasCompletedCurrentStepAudio: false,
        }));
        syncMediaPlaybackState();
      };
      const handlePlaybackReady = () => {
        setWaitingState(false);
        syncMediaPlaybackState();
      };
      const handlePlaybackPaused = () => {
        setWaitingState(false);
        syncMediaPlaybackState();
      };
      const handlePlaybackEnded = () => {
        setWaitingState(false);
        setPlaybackState(prevState => ({
          ...prevState,
          hasCompletedCurrentStepAudio: true,
        }));
        syncMediaPlaybackState();
      };

      audioWaitingStateMapRef.current.set(audioElement, false);
      audioElement.addEventListener('play', handlePlaybackStarted);
      audioElement.addEventListener('playing', handlePlaybackStarted);
      audioElement.addEventListener('loadstart', handlePlaybackWaiting);
      audioElement.addEventListener('waiting', handlePlaybackWaiting);
      audioElement.addEventListener('seeking', handlePlaybackWaiting);
      audioElement.addEventListener('canplay', handlePlaybackReady);
      audioElement.addEventListener('canplaythrough', handlePlaybackReady);
      audioElement.addEventListener('seeked', handlePlaybackReady);
      audioElement.addEventListener('pause', handlePlaybackPaused);
      audioElement.addEventListener('ended', handlePlaybackEnded);
      audioListenerCleanupMapRef.current.set(audioElement, () => {
        audioElement.removeEventListener('play', handlePlaybackStarted);
        audioElement.removeEventListener('playing', handlePlaybackStarted);
        audioElement.removeEventListener('loadstart', handlePlaybackWaiting);
        audioElement.removeEventListener('waiting', handlePlaybackWaiting);
        audioElement.removeEventListener('seeking', handlePlaybackWaiting);
        audioElement.removeEventListener('canplay', handlePlaybackReady);
        audioElement.removeEventListener('canplaythrough', handlePlaybackReady);
        audioElement.removeEventListener('seeked', handlePlaybackReady);
        audioElement.removeEventListener('pause', handlePlaybackPaused);
        audioElement.removeEventListener('ended', handlePlaybackEnded);
        audioWaitingStateMapRef.current.delete(audioElement);
      });
      syncMediaPlaybackState();
    };

    const syncAudioElements = () => {
      const nextAudioElements = new Set(
        Array.from(container.querySelectorAll('audio')),
      );

      audioListenerCleanupMapRef.current.forEach((cleanup, audioElement) => {
        if (nextAudioElements.has(audioElement)) {
          return;
        }
        cleanup();
        audioListenerCleanupMapRef.current.delete(audioElement);
      });

      nextAudioElements.forEach(registerAudioElement);
      syncMediaPlaybackState();
    };

    syncAudioElements();

    const mutationObserver = new MutationObserver(() => {
      syncAudioElements();
    });
    mutationObserver.observe(container, {
      childList: true,
      subtree: true,
    });

    return () => {
      mutationObserver.disconnect();
      audioListenerCleanupMapRef.current.forEach(cleanup => {
        cleanup();
      });
      audioListenerCleanupMapRef.current.clear();
      audioWaitingStateMapRef.current.clear();
    };
  }, [chatRef, syncMediaPlaybackState]);

  const handleStepChange = useCallback(
    (element: SlideElement | undefined, index: number) => {
      setPlaybackState(prevState => {
        if (
          prevState.currentStepIndex === index &&
          prevState.totalStepCount === markerStepCount
        ) {
          return prevState;
        }

        return {
          ...prevState,
          currentStepIndex: index,
          totalStepCount: markerStepCount,
        };
      });
    },
    [markerStepCount],
  );

  useEffect(() => {
    const currentStepHasAudio = hasListenStepAudio(currentMarkerStepElement);
    const currentStepHasBlockingInteraction = hasBlockingListenInteraction(
      currentMarkerStepElement,
    );
    const isSameMarkerStep =
      previousMarkerStepKeyRef.current === currentMarkerStepKey;

    setPlaybackState(prevState => {
      const nextHasCompletedCurrentStepAudio = currentStepHasAudio
        ? isSameMarkerStep
          ? prevState.hasCompletedCurrentStepAudio
          : false
        : true;

      if (
        prevState.totalStepCount === markerStepCount &&
        prevState.currentStepHasAudio === currentStepHasAudio &&
        prevState.currentStepHasBlockingInteraction ===
          currentStepHasBlockingInteraction &&
        prevState.hasCompletedCurrentStepAudio ===
          nextHasCompletedCurrentStepAudio
      ) {
        return prevState;
      }

      return {
        ...prevState,
        totalStepCount: markerStepCount,
        currentStepHasAudio,
        currentStepHasBlockingInteraction,
        hasCompletedCurrentStepAudio: nextHasCompletedCurrentStepAudio,
      };
    });
    previousMarkerStepKeyRef.current = currentMarkerStepKey;
  }, [currentMarkerStepElement, currentMarkerStepKey, markerStepCount]);

  useEffect(() => {
    onPlaybackStateChange?.({
      isAudioPlaying: playbackState.isAudioPlaying,
      isAudioSequenceActive: getListenPlaybackSequenceActive(playbackState),
    });
  }, [onPlaybackStateChange, playbackState]);

  useEffect(() => {
    previousMarkerStepKeyRef.current = '';
    setPlaybackState({
      currentStepIndex: -1,
      totalStepCount: markerStepCount,
      currentStepHasAudio: false,
      currentStepHasBlockingInteraction: false,
      hasCompletedCurrentStepAudio: false,
      isAudioPlaying: false,
      isAudioWaiting: false,
    });
  }, [lessonId, markerSequenceKey]);

  useEffect(() => {
    setPlaybackState(prevState =>
      reconcileListenPlaybackStepCount(prevState, markerStepCount),
    );
  }, [markerStepCount]);

  useEffect(
    () => () => {
      onPlaybackStateChange?.({
        isAudioPlaying: false,
        isAudioSequenceActive: false,
      });
    },
    [onPlaybackStateChange],
  );

  return (
    <div
      className={cn(
        'listen-reveal-wrapper',
        mobileStyle ? 'mobile bg-white' : 'bg-[var(--color-slide-desktop-bg)]',
      )}
      ref={chatRef}
    >
      <div className='listen-slide-shell'>
        <Slide
          // playerAlwaysVisible={true}
          className='h-full w-full listen-slide-root'
          elementList={elementList}
          interactionTexts={{
            title: t('module.chat.listenInteractionHint'),
            confirmButtonText: t('module.renderUi.core.confirm'),
            copyButtonText: t('module.renderUi.core.copyCode'),
            copiedButtonText: t('module.renderUi.core.copied'),
          }}
          bufferingText={t('module.chat.slideAudioBuffering')}
          onPlayerVisibilityChange={handlePlayerVisibilityChange}
          onStepChange={handleStepChange}
          interactionDefaultValueOptions={
            lessonFeedbackInteractionDefaultValueOptions
          }
          onSend={handleInteractionSend}
          playerClassName={mobileStyle ? 'listen-slide-player-mobile' : ''}
          showPlayer={!shouldRenderEmptyPpt}
        />
      </div>
    </div>
  );
};

ListenModeSlideRenderer.displayName = 'ListenModeSlideRenderer';

export default memo(ListenModeSlideRenderer);

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Image from 'next/image';
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
  resolveCurrentStepAudioCompletion,
  type ListenPlaybackState,
} from './listenPlaybackState';
import AskBlock from './AskBlock';
import type { AskMessage } from './AskBlock';
import AskIcon from '@/c-assets/newchat/light/icon_ask.svg';
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
  shifuBid?: string;
  previewMode?: boolean;
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
  lessonId = '',
  shifuBid = '',
  previewMode = false,
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
  const [isCustomAskOpen, setIsCustomAskOpen] = useState(false);
  const [isPlayerVisible, setIsPlayerVisible] = useState(true);
  const [currentStepBlockBid, setCurrentStepBlockBid] = useState('');
  const customAskActionRef = useRef<HTMLButtonElement | null>(null);
  const customAskOverlayRef = useRef<HTMLDivElement | null>(null);
  const slideShellRef = useRef<HTMLDivElement | null>(null);
  const { lastInteractionBid, lastItemIsInteraction, firstContentItem } =
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

  const askListByParentElementBid = useMemo(() => {
    const askMapping = new Map<string, ChatContentItem['ask_list']>();
    items.forEach(item => {
      if (item.type !== ChatContentItemType.ASK || !item.parent_element_bid) {
        return;
      }
      askMapping.set(item.parent_element_bid, item.ask_list ?? []);
    });
    return askMapping;
  }, [items]);

  const fallbackAskElementBid = firstContentItem?.element_bid ?? '';
  const resolvedAskElementBid = currentStepBlockBid || fallbackAskElementBid;
  const currentAskList = useMemo<AskMessage[]>(
    () =>
      (resolvedAskElementBid
        ? askListByParentElementBid.get(resolvedAskElementBid) ?? []
        : []) as AskMessage[],
    [askListByParentElementBid, resolvedAskElementBid],
  );

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

  const closeInteractionOverlayIfOpen = useCallback(() => {
    const shellElement = slideShellRef.current;
    if (!shellElement) {
      return;
    }

    const notesToggleButton =
      shellElement.querySelector<HTMLButtonElement>(
        'button[aria-label="Notes"].slide-player__action',
      ) ??
      shellElement.querySelector<HTMLButtonElement>(
        '.slide-player__controls .slide-player__group:last-of-type > .slide-player__action:last-of-type',
      );

    if (
      !notesToggleButton ||
      !notesToggleButton.classList.contains('slide-player__action--active')
    ) {
      return;
    }

    // Reuse the player toggle path so the default overlay closes first.
    notesToggleButton.click();
  }, []);

  const handleCustomAskToggle = useCallback(() => {
    setIsCustomAskOpen(prevOpen => {
      const nextOpen = !prevOpen;
      if (nextOpen) {
        closeInteractionOverlayIfOpen();
      }
      return nextOpen;
    });
  }, [closeInteractionOverlayIfOpen]);

  const handleCustomAskClose = useCallback(() => {
    setIsCustomAskOpen(false);
  }, []);

  const handlePlayerVisibilityChange = useCallback(
    (visible: boolean) => {
      setIsPlayerVisible(visible);
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
      const blockBid = (element as ListenSlideElement | undefined)?.blockBid;
      if (blockBid && blockBid !== 'empty-ppt') {
        setCurrentStepBlockBid(blockBid);
      }

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
    if (!mobileStyle) {
      return;
    }
    setIsCustomAskOpen(false);
  }, [mobileStyle]);

  useEffect(() => {
    if (!isCustomAskOpen) {
      return;
    }

    const handleWindowPointerDown = (event: PointerEvent) => {
      const eventTarget = event.target as Node | null;

      if (!eventTarget) {
        return;
      }

      if (customAskActionRef.current?.contains(eventTarget)) {
        return;
      }

      if (customAskOverlayRef.current?.contains(eventTarget)) {
        return;
      }

      setIsCustomAskOpen(false);
    };

    window.addEventListener('pointerdown', handleWindowPointerDown);

    return () => {
      window.removeEventListener('pointerdown', handleWindowPointerDown);
    };
  }, [isCustomAskOpen]);

  useEffect(() => {
    const currentStepHasAudio = hasListenStepAudio(currentMarkerStepElement);
    const currentStepHasBlockingInteraction = hasBlockingListenInteraction(
      currentMarkerStepElement,
    );
    const isSameMarkerStep =
      previousMarkerStepKeyRef.current === currentMarkerStepKey;

    setPlaybackState(prevState => {
      const nextHasCompletedCurrentStepAudio =
        resolveCurrentStepAudioCompletion({
          previousStepHasAudio: prevState.currentStepHasAudio,
          nextStepHasAudio: currentStepHasAudio,
          previousCompleted: prevState.hasCompletedCurrentStepAudio,
          isSameMarkerStep,
        });

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

  const playerCustomActions = useMemo(
    () => (
      <button
        aria-label={t('module.chat.ask')}
        className={cn(
          'slide-player__action listen-slide-custom-player-action',
          isCustomAskOpen && 'slide-player__action--active',
        )}
        onClick={handleCustomAskToggle}
        ref={customAskActionRef}
        type='button'
      >
        <svg
          xmlns='http://www.w3.org/2000/svg'
          width='32'
          height='32'
          viewBox='0 0 32 32'
          fill='none'
          className='slide-player__icon listen-slide-custom-player-icon'
        >
          <path
            d='M26.3445 4.74414C26.4675 5.09781 26.6652 5.42133 26.9246 5.69141C27.184 5.96145 27.499 6.17239 27.8474 6.30957L29.8621 7.10254L27.8474 7.89648C27.499 8.03368 27.184 8.24459 26.9246 8.51465C26.6652 8.78475 26.4675 9.10822 26.3445 9.46191L25.6257 11.5264L24.908 9.46191C24.7849 9.10813 24.5864 8.78479 24.3269 8.51465C24.0674 8.24451 23.7526 8.03368 23.4041 7.89648L21.3894 7.10254L23.4041 6.30957C23.7526 6.17238 24.0674 5.96155 24.3269 5.69141C24.5864 5.42126 24.7849 5.09794 24.908 4.74414L25.6257 2.67871L26.3445 4.74414Z'
            fill='currentColor'
            stroke='currentColor'
            strokeWidth='2'
          />
          <path
            d='M16 3.70312C16.1784 3.70312 16.3558 3.70749 16.5322 3.71484L17.0586 3.74707C17.1746 3.75677 17.2657 3.82138 17.3213 3.95996C17.3818 4.11086 17.3772 4.31265 17.2832 4.4834C17.1747 4.68036 16.9667 4.79221 16.7686 4.7793C16.5128 4.76236 16.2563 4.75294 16 4.75293C9.84302 4.75293 4.81741 9.6034 4.53711 15.6904L4.5332 15.7549L4.5293 15.7959L4.52539 15.8311V27.7031H14.7822L14.834 27.6943L15.0098 27.6631L15.2109 27.6768C15.4715 27.6944 15.7346 27.7031 16 27.7031C22.3375 27.7031 27.4745 22.566 27.4746 16.2285C27.4746 16.0954 27.5582 15.9612 27.6973 15.9004C27.7337 15.8846 27.7698 15.8698 27.8037 15.8545V15.8535C27.9815 15.7729 28.1848 15.7842 28.332 15.8564C28.4673 15.9228 28.5235 16.0181 28.5244 16.1328C28.5247 16.1646 28.5254 16.1966 28.5254 16.2285C28.5253 23.1458 22.9173 28.7529 16 28.7529C15.7108 28.7529 15.4238 28.7438 15.1396 28.7246L15.0674 28.7197L14.9951 28.7324C14.9163 28.7463 14.8343 28.7529 14.75 28.7529H4.875C4.10179 28.7529 3.47468 28.1267 3.47461 27.3535V15.8535C3.47461 15.7964 3.47888 15.7407 3.48535 15.6865L3.4873 15.6641L3.48828 15.6426C3.79411 8.99765 9.27913 3.70312 16 3.70312Z'
            fill='currentColor'
            stroke='currentColor'
            strokeWidth='2'
          />
          <path
            d='M16 11.3262C16.1392 11.3262 16.2726 11.382 16.3711 11.4805C16.4695 11.5789 16.5254 11.7123 16.5254 11.8516V21.9766C16.5254 22.1158 16.4695 22.2492 16.3711 22.3477C16.2726 22.4461 16.1392 22.502 16 22.502C15.8608 22.502 15.7274 22.4461 15.6289 22.3477C15.5304 22.2492 15.4746 22.1158 15.4746 21.9766V11.8516C15.4746 11.7123 15.5304 11.5789 15.6289 11.4805C15.7274 11.382 15.8608 11.3262 16 11.3262ZM11 13.7012C11.1392 13.7012 11.2726 13.757 11.3711 13.8555C11.4696 13.9539 11.5254 14.0873 11.5254 14.2266V19.4766C11.5254 19.6158 11.4696 19.7492 11.3711 19.8477C11.2726 19.9461 11.1392 20.002 11 20.002C10.8608 20.002 10.7274 19.9461 10.6289 19.8477C10.5304 19.7492 10.4746 19.6158 10.4746 19.4766V14.2266L10.4854 14.124C10.5055 14.023 10.555 13.9294 10.6289 13.8555C10.7274 13.757 10.8608 13.7012 11 13.7012ZM21 13.7012C21.1392 13.7012 21.2726 13.757 21.3711 13.8555C21.4695 13.9539 21.5254 14.0873 21.5254 14.2266V19.4766C21.5254 19.6158 21.4695 19.7492 21.3711 19.8477C21.2726 19.9461 21.1392 20.002 21 20.002C20.8608 20.002 20.7274 19.9461 20.6289 19.8477C20.5305 19.7492 20.4746 19.6158 20.4746 19.4766V14.2266C20.4746 14.0873 20.5305 13.9539 20.6289 13.8555C20.7274 13.757 20.8608 13.7012 21 13.7012Z'
            fill='currentColor'
            stroke='currentColor'
            strokeWidth='2'
          />
        </svg>
      </button>
    ),
    [handleCustomAskToggle, isCustomAskOpen, t],
  );

  const shouldRenderMobileAskEntry = mobileStyle && !shouldRenderEmptyPpt;

  console.log('elementlist', elementList);

  return (
    <div
      className={cn(
        'listen-reveal-wrapper',
        mobileStyle ? 'mobile bg-white' : 'bg-[var(--color-slide-desktop-bg)]',
      )}
      ref={chatRef}
    >
      <div
        className='listen-slide-shell'
        ref={slideShellRef}
      >
        {shouldRenderMobileAskEntry ? (
          <button
            type='button'
            className='listen-slide-mobile-ask-entry listen-slide-mobile-ask-button'
            onClick={handleCustomAskToggle}
          >
            <Image
              src={AskIcon.src}
              alt='ask'
              width={14}
              height={14}
            />
            <span>{t('module.chat.ask')}</span>
          </button>
        ) : null}
        {isCustomAskOpen && !shouldRenderEmptyPpt ? (
          mobileStyle ? (
            <div
              className='listen-slide-mobile-ask-panel'
              ref={customAskOverlayRef}
            >
              <AskBlock
                askList={currentAskList}
                className='listen-slide-ask-block'
                element_bid={resolvedAskElementBid}
                isExpanded={true}
                onToggleAskExpanded={handleCustomAskClose}
                outline_bid={lessonId}
                preview_mode={previewMode}
                shifu_bid={shifuBid}
              />
            </div>
          ) : (
            <div
              className={cn(
                'slide-ask-overlay',
                isPlayerVisible
                  ? 'slide-ask-overlay--with-player'
                  : 'slide-ask-overlay--standalone',
              )}
              ref={customAskOverlayRef}
            >
              <div className='slide-player__ask-card'>
                <div className='slide-player__ask-body'>
                  <AskBlock
                    askList={currentAskList}
                    className='listen-slide-ask-block'
                    element_bid={resolvedAskElementBid}
                    isExpanded={true}
                    onToggleAskExpanded={handleCustomAskClose}
                    outline_bid={lessonId}
                    preview_mode={previewMode}
                    shifu_bid={shifuBid}
                  />
                </div>
                <div className='slide-player__ask-arrow' />
              </div>
            </div>
          )
        ) : null}
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
          playerCustomActions={mobileStyle ? undefined : playerCustomActions}
          showPlayer={!shouldRenderEmptyPpt}
        />
      </div>
    </div>
  );
};

ListenModeSlideRenderer.displayName = 'ListenModeSlideRenderer';

export default memo(ListenModeSlideRenderer);

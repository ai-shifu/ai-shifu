import { memo, useCallback, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { lessonFeedbackInteractionDefaultValueOptions } from '@/c-utils/lesson-feedback-interaction-defaults';
import {
  getAudioSegmentDataListFromTracks,
  hasAudioContentInTrack,
  mergeAudioSegmentDataList,
} from '@/c-utils/audio-utils';
import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';
import {
  ELEMENT_TYPE,
  LESSON_FEEDBACK_INTERACTION_MARKER,
} from '@/c-api/studyV2';
import {
  type OnSendContentParams,
  Slide,
  type Element as SlideElement,
} from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import { normalizeAudioTracks } from './listenModeUtils';
import './ListenModeRenderer.scss';
import { useListenContentData } from './useListenMode';

type ListenSlideElement = SlideElement & {
  blockBid?: string;
  page?: number;
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
}

type ResolveRenderSequence = (params: {
  item: ChatContentItem;
  itemType: 'content' | 'interaction';
  fallbackSequence: number;
}) => number;

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

const resolveItemAudioSegments = (item: ChatContentItem) => {
  const normalizedTracks = normalizeAudioTracks(item);
  const trackAudioSegments = getAudioSegmentDataListFromTracks(
    normalizedTracks.filter(track => hasAudioContentInTrack(track)),
  );
  const mergedAudioSegments = mergeAudioSegmentDataList(item.element_bid, [
    ...(item.audio_segments ?? []),
    ...trackAudioSegments,
  ]);

  return mergedAudioSegments.length > 0 ? mergedAudioSegments : undefined;
};

const resolveItemAudioUrl = (item: ChatContentItem) => {
  if (item.audio_url || item.audioUrl) {
    return item.audio_url ?? item.audioUrl;
  }

  return normalizeAudioTracks(item).find(track => hasAudioContentInTrack(track))
    ?.audioUrl;
};

const resolveContentElementType = (item: ChatContentItem) => {
  // `element_type` comes from backend `ElementType` (e.g. text/tables/code).
  // `ChatContentItemType.CONTENT` is a different "content item kind" enum,
  // so we should not compare them directly.
  if (item.element_type) {
    return item.element_type;
  }

  return ELEMENT_TYPE.TEXT;
};

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
      const audioSegments = resolveItemAudioSegments(item);
      const audioUrl = resolveItemAudioUrl(item);
      const contentType = resolveContentElementType(item);

      if (!hasResolvedFirstContentType) {
        hasResolvedFirstContentType = true;
        hasLeadingTextContentElement = contentType === ELEMENT_TYPE.TEXT;
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

    if (item.content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER)) {
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
  onSend,
  onPlayerVisibilityChange,
}: ListenModeSlideRendererProps) => {
  const { t } = useTranslation();
  const renderSequenceByStreamKeyRef = useRef<Map<string, number>>(new Map());
  const [interactionInputMap, setInteractionInputMap] = useState<
    Record<string, string>
  >({});
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

  console.log('elementList', items, elementList);

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
          onPlayerVisibilityChange={onPlayerVisibilityChange}
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

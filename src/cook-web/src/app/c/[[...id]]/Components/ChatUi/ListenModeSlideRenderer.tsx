import { memo, useCallback, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { lessonFeedbackInteractionDefaultValueOptions } from '@/c-utils/lesson-feedback-interaction-defaults';
import { hasAudioContentInTrack } from '@/c-utils/audio-utils';
import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';
import { LESSON_FEEDBACK_INTERACTION_MARKER } from '@/c-api/studyV2';
import {
  splitContentSegments,
  type OnSendContentParams,
  Slide,
  type Element as SlideElement,
} from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import {
  buildSlidePageMapping,
  normalizeAudioTracks,
  sortSegmentsByIndex,
} from './listenModeUtils';
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
  previewMode?: boolean;
  onRequestAudioForBlock?: (elementBid: string) => Promise<any>;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
  onPlayerVisibilityChange?: (visible: boolean) => void;
}

const resolveSegmentElementType = (segmentType: string) =>
  segmentType === 'sandbox' ? 'html' : 'markdown';

const createEmptyStateElement = (
  sectionTitle: string | undefined,
): ListenSlideElement => ({
  sequence_number: 1,
  type: 'slot',
  content: (
    <div className='flex h-full w-full items-center justify-center font-bold text-primary'>
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
}: {
  items: ChatContentItem[];
  sectionTitle?: string;
  interactionInputMap: Record<string, string>;
  lastInteractionBid: string | null;
  lastItemIsInteraction: boolean;
}) => {
  let pageCursor = 0;
  let sequenceNumber = 0;
  const elementList: ListenSlideElement[] = [];

  items.forEach(item => {
    if (item.type === ChatContentItemType.CONTENT) {
      const segments = item.content
        ? splitContentSegments(item.content, true)
        : [];
      const slideSegments = segments.filter(
        segment => segment.type === 'markdown' || segment.type === 'sandbox',
      );
      const fallbackPage = Math.max(pageCursor - 1, 0);
      const pageIndices = slideSegments.map((_, index) => pageCursor + index);
      const tracks = normalizeAudioTracks(item);
      const { pageBySlideId, resolvePageByPosition } = buildSlidePageMapping(
        item,
        pageIndices,
        fallbackPage,
      );
      const tracksByPage = new Map<number, typeof tracks>();

      tracks.forEach(track => {
        const position = Number(track.position ?? 0);
        const page =
          (track.slideId ? pageBySlideId.get(track.slideId) : undefined) ??
          resolvePageByPosition(position);
        const currentTracks = tracksByPage.get(page) ?? [];
        currentTracks.push(track);
        tracksByPage.set(page, currentTracks);
      });

      slideSegments.forEach((segment, index) => {
        const page = pageCursor + index;
        const pageTracks = tracksByPage.get(page) ?? [];
        const [primaryTrack, ...secondaryTracks] = pageTracks;

        sequenceNumber += 1;
        elementList.push({
          sequence_number: sequenceNumber,
          type: resolveSegmentElementType(segment.type),
          content: segment.value,
          is_marker: true,
          is_renderable: true,
          is_new: true,
          is_speakable: hasAudioContentInTrack(primaryTrack),
          audio_url: primaryTrack?.audioUrl,
          audio_segments: primaryTrack
            ? sortSegmentsByIndex(primaryTrack.audioSegments ?? []).map(
                audioSegment => ({
                  segment_index: audioSegment.segmentIndex,
                  audio_data: audioSegment.audioData,
                  duration_ms: audioSegment.durationMs,
                  is_final: audioSegment.isFinal,
                  position: audioSegment.position,
                  slide_id: audioSegment.slideId,
                  av_contract: audioSegment.avContract ?? null,
                }),
              )
            : undefined,
          blockBid: item.element_bid,
          page,
        });

        secondaryTracks.forEach(track => {
          if (!hasAudioContentInTrack(track)) {
            return;
          }

          sequenceNumber += 1;
          elementList.push({
            sequence_number: sequenceNumber,
            type: 'slot',
            content: null,
            is_speakable: true,
            audio_url: track.audioUrl,
            audio_segments: sortSegmentsByIndex(track.audioSegments ?? []).map(
              audioSegment => ({
                segment_index: audioSegment.segmentIndex,
                audio_data: audioSegment.audioData,
                duration_ms: audioSegment.durationMs,
                is_final: audioSegment.isFinal,
                position: audioSegment.position,
                slide_id: audioSegment.slideId,
                av_contract: audioSegment.avContract ?? null,
              }),
            ),
            blockBid: item.element_bid,
            page,
          });
        });
      });

      pageCursor += slideSegments.length;
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
      sequence_number: sequenceNumber,
      type: 'interaction',
      content: item.content || '',
      is_marker: true,
      is_renderable: true,
      is_new: true,
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

  return elementList;
};

const ListenModeSlideRenderer = ({
  items,
  mobileStyle,
  chatRef,
  isLoading = false,
  sectionTitle,
  previewMode = false,
  onRequestAudioForBlock,
  onSend,
  onPlayerVisibilityChange,
}: ListenModeSlideRendererProps) => {
  const { t } = useTranslation();
  const requestedAudioBlockBidsRef = useRef<Set<string>>(new Set());
  const [interactionInputMap, setInteractionInputMap] = useState<
    Record<string, string>
  >({});
  const { ttsReadyElementBids, lastInteractionBid, lastItemIsInteraction } =
    useListenContentData(items);

  const elementList = useMemo(
    () =>
      buildSlideElementList({
        items,
        sectionTitle,
        interactionInputMap,
        lastInteractionBid,
        lastItemIsInteraction,
      }),
    [
      interactionInputMap,
      items,
      lastInteractionBid,
      lastItemIsInteraction,
      sectionTitle,
    ],
  );

  const shouldRenderEmptyPpt =
    !isLoading &&
    elementList.length === 1 &&
    elementList[0]?.blockBid === 'empty-ppt';

  const handleStepChange = useCallback(
    (element?: SlideElement) => {
      const currentElement = element as ListenSlideElement | undefined;
      const blockBid = currentElement?.blockBid;

      if (
        previewMode ||
        !blockBid ||
        !onRequestAudioForBlock ||
        requestedAudioBlockBidsRef.current.has(blockBid) ||
        !ttsReadyElementBids.has(blockBid)
      ) {
        return;
      }

      const hasAudio = Boolean(
        currentElement?.audio_url || currentElement?.audio_segments?.length,
      );
      if (currentElement?.type === 'interaction' || hasAudio) {
        return;
      }

      requestedAudioBlockBidsRef.current.add(blockBid);
      void onRequestAudioForBlock(blockBid).catch(() => {
        requestedAudioBlockBidsRef.current.delete(blockBid);
      });
    },
    [onRequestAudioForBlock, previewMode, ttsReadyElementBids],
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

  console.log('elementList', elementList);

  return (
    <div
      className={cn(
        'listen-reveal-wrapper bg-[var(--color-4)]',
        mobileStyle ? 'mobile' : '',
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
          onPlayerVisibilityChange={onPlayerVisibilityChange}
          interactionDefaultValueOptions={
            lessonFeedbackInteractionDefaultValueOptions
          }
          onSend={handleInteractionSend}
          onStepChange={handleStepChange}
          playerClassName={mobileStyle ? 'listen-slide-player-mobile' : ''}
          showPlayer={!shouldRenderEmptyPpt}
        />
      </div>
    </div>
  );
};

ListenModeSlideRenderer.displayName = 'ListenModeSlideRenderer';

export default memo(ListenModeSlideRenderer);

import {
  memo,
  useCallback,
  useMemo,
  useRef,
  useState,
} from 'react';
import { cn } from '@/lib/utils';
import { hasAudioContentInTrack } from '@/c-utils/audio-utils';
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
  onRequestAudioForBlock?: (generatedBlockBid: string) => Promise<any>;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
  onPlayerVisibilityChange?: (visible: boolean) => void;
}

const resolveSegmentElementType = (segmentType: string) =>
  segmentType === 'sandbox' ? 'html' : 'markdown';

const buildSubmittedInteractionValue = (content: OnSendContentParams) =>
  [
    ...(content.selectedValues ?? []),
    content.inputText?.trim() ?? '',
    content.buttonText?.trim() ?? '',
  ]
    .filter(Boolean)
    .join(', ');

const createEmptyStateElement = (
  sectionTitle: string | undefined,
): ListenSlideElement => ({
  serial_number: 1,
  type: 'slot',
  content: (
    <div className='flex h-full w-full items-center justify-center font-bold text-primary'>
      {sectionTitle}
    </div>
  ),
  is_checkpoint: true,
  is_show: true,
  operation: 'new',
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
  let serialNumber = 0;
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

        serialNumber += 1;
        elementList.push({
          serial_number: serialNumber,
          type: resolveSegmentElementType(segment.type),
          content: segment.value,
          is_checkpoint: true,
          is_show: true,
          operation: 'new',
          is_read: hasAudioContentInTrack(primaryTrack),
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
          blockBid: item.generated_block_bid,
          page,
        });

        secondaryTracks.forEach(track => {
          if (!hasAudioContentInTrack(track)) {
            return;
          }

          serialNumber += 1;
          elementList.push({
            serial_number: serialNumber,
            type: 'slot',
            content: null,
            is_read: true,
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
            blockBid: item.generated_block_bid,
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

    const currentUserInput = interactionInputMap[item.generated_block_bid] ?? '';
    const isLatestEditable =
      lastItemIsInteraction && item.generated_block_bid === lastInteractionBid;

    serialNumber += 1;
    elementList.push({
      serial_number: serialNumber,
      type: 'interaction',
      content: item.content || '',
      is_checkpoint: true,
      is_show: true,
      operation: 'new',
      blockBid: item.generated_block_bid,
      page: Math.max(pageCursor - 1, 0),
      user_input: currentUserInput,
      readonly: Boolean(item.readonly) || Boolean(currentUserInput) || !isLatestEditable,
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
  const requestedAudioBlockBidsRef = useRef<Set<string>>(new Set());
  const [interactionInputMap, setInteractionInputMap] = useState<
    Record<string, string>
  >({});
  const { ttsReadyBlockBids, lastInteractionBid, lastItemIsInteraction } =
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

  const shouldRenderEmptyPpt = !isLoading && elementList.length === 1 && elementList[0]?.blockBid === 'empty-ppt';

  const handleStepChange = useCallback(
    (element?: SlideElement) => {
      const currentElement = element as ListenSlideElement | undefined;
      const blockBid = currentElement?.blockBid;

      if (
        previewMode ||
        !blockBid ||
        !onRequestAudioForBlock ||
        requestedAudioBlockBidsRef.current.has(blockBid) ||
        !ttsReadyBlockBids.has(blockBid)
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
    [onRequestAudioForBlock, previewMode, ttsReadyBlockBids],
  );

  const handleInteractionSend = useCallback(
    (content: OnSendContentParams, element?: SlideElement) => {
      const blockBid = (element as ListenSlideElement | undefined)?.blockBid;
      if (!blockBid) {
        return;
      }

      const submittedValue = buildSubmittedInteractionValue(content);
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
          onPlayerVisibilityChange={onPlayerVisibilityChange}
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

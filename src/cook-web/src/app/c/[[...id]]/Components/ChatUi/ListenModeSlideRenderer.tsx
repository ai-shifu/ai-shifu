import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { lessonFeedbackInteractionDefaultValueOptions } from '@/c-utils/lesson-feedback-interaction-defaults';
import { hasAudioContentInTrack } from '@/c-utils/audio-utils';
import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';
import {
  ELEMENT_TYPE,
  LESSON_FEEDBACK_INTERACTION_MARKER,
  type AudioSegmentData,
} from '@/c-api/studyV2';
import {
  ContentRender,
  type OnSendContentParams,
} from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import { normalizeAudioTracks, sortSegmentsByIndex } from './listenModeUtils';
import {
  AudioPlayer,
  type AudioPlayerHandle,
} from '@/components/audio/AudioPlayer';
import type { AudioSegment } from '@/c-utils/audio-utils';
import './ListenModeRenderer.scss';
import AskBlock from './AskBlock';
import ListenPlayer from './ListenPlayer';

// ── Step data model ──

interface ListenStep {
  bid: string;
  content: string;
  elementType: string;
  audioSegments?: AudioSegmentData[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  /** Pre-loaded ask history from payload.asks */
  askList?: ChatContentItem[];
  isMarker?: boolean;
}

// ── Helpers ──

const resolveItemAudioSegments = (
  item: ChatContentItem,
): AudioSegmentData[] | undefined => {
  if (item.audio_segments?.length) return item.audio_segments;
  const primaryTrack = normalizeAudioTracks(item).find(track =>
    hasAudioContentInTrack(track),
  );
  if (!primaryTrack) return undefined;
  return sortSegmentsByIndex(primaryTrack.audioSegments ?? []).map(seg => ({
    segment_index: seg.segmentIndex,
    audio_data: seg.audioData,
    duration_ms: seg.durationMs,
    is_final: seg.isFinal,
    position: seg.position,
  }));
};

const resolveItemAudioUrl = (item: ChatContentItem): string | undefined => {
  if (item.audio_url || item.audioUrl) return item.audio_url ?? item.audioUrl;
  return normalizeAudioTracks(item).find(track => hasAudioContentInTrack(track))
    ?.audioUrl;
};

/**
 * Build ordered visual steps + optional trailing interaction.
 *
 * - is_renderable=true  → visual step
 * - is_renderable=false, is_speakable=true → narration audio for previous visual
 * - interaction → trailing interaction
 */
const buildSteps = (
  items: ChatContentItem[],
): { steps: ListenStep[]; interaction: ChatContentItem | null } => {
  const steps: ListenStep[] = [];
  let interaction: ChatContentItem | null = null;

  items.forEach(item => {
    if (item.type === ChatContentItemType.CONTENT) {
      const isRenderable = item.is_renderable !== false;

      if (isRenderable) {
        steps.push({
          bid: item.element_bid,
          content: item.content || '',
          elementType: item.element_type || ELEMENT_TYPE.HTML,
          askList: item.ask_list,
          isMarker: item.is_marker ?? true,
        });
      } else {
        // Narration → merge audio into previous visual step
        const audioSegments = resolveItemAudioSegments(item);
        const audioUrl = resolveItemAudioUrl(item);
        const last = steps[steps.length - 1];
        if (last) {
          if (audioSegments?.length) {
            last.audioSegments = [
              ...(last.audioSegments ?? []),
              ...audioSegments,
            ];
          }
          if (audioUrl) last.audioUrl = audioUrl;
          last.isAudioStreaming = item.isAudioStreaming;
        }
      }
      return;
    }

    if (item.type !== ChatContentItemType.INTERACTION) return;
    if (item.content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER)) return;

    interaction = item;
  });

  return { steps, interaction };
};

// ── Props ──

interface ListenModeSlideRendererProps {
  items: ChatContentItem[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  isLoading?: boolean;
  sectionTitle?: string;
  lessonId?: string;
  lessonStatus?: string;
  previewMode?: boolean;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
  onPlayerVisibilityChange?: (visible: boolean) => void;
  toggleAskExpanded?: (parentElementBid: string) => void;
  shifuBid?: string;
  outlineBid?: string;
}

// ── Component ──

const ListenModeSlideRenderer = ({
  items,
  mobileStyle,
  chatRef,
  isLoading = false,
  sectionTitle,
  previewMode = false,
  onSend,
  shifuBid = '',
  outlineBid = '',
}: ListenModeSlideRendererProps) => {
  const { t } = useTranslation();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [isAskOpen, setIsAskOpen] = useState(false);
  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);

  // ── Build steps ──

  const { steps, interaction } = useMemo(() => buildSteps(items), [items]);

  // History vs run mode
  const isHistoryMode = useMemo(() => {
    if (items.length === 0) return false;
    return items.every(
      item =>
        item.isHistory ||
        item.type === ChatContentItemType.LIKE_STATUS ||
        item.type === ChatContentItemType.ASK,
    );
  }, [items]);

  // Marker indices for history navigation
  const markerIndices = useMemo(() => {
    const indices: number[] = [];
    steps.forEach((step, idx) => {
      if (step.isMarker) indices.push(idx);
    });
    return indices;
  }, [steps]);

  // ── Auto-advance in run mode ──

  const prevStepCountRef = useRef(steps.length);
  useEffect(() => {
    if (isHistoryMode) {
      prevStepCountRef.current = steps.length;
      return;
    }
    const prevCount = prevStepCountRef.current;
    prevStepCountRef.current = steps.length;
    if (prevCount === 0 && steps.length > 0) {
      setCurrentStepIndex(0);
    }
  }, [steps.length, isHistoryMode]);

  // ── Current step ──

  const clampedIndex = Math.min(
    currentStepIndex,
    Math.max(steps.length - 1, 0),
  );
  const currentStep = steps[clampedIndex] ?? null;

  const showInteraction =
    interaction && (steps.length === 0 || currentStepIndex >= steps.length);

  // Close ask panel when step changes
  useEffect(() => {
    setIsAskOpen(false);
  }, [clampedIndex]);

  // ── Audio segments for player ──

  const playerSegments: AudioSegment[] = useMemo(() => {
    if (!currentStep?.audioSegments?.length) return [];
    return currentStep.audioSegments.map(seg => ({
      segmentIndex: seg.segment_index,
      audioData: seg.audio_data,
      durationMs: seg.duration_ms,
      isFinal: seg.is_final,
      position: seg.position,
    }));
  }, [currentStep?.audioSegments]);

  // ── Player controls ──

  const handlePlay = useCallback(() => {
    audioPlayerRef.current?.play();
  }, []);

  const handlePause = useCallback((traceId?: string) => {
    audioPlayerRef.current?.pause({ traceId });
  }, []);

  const handlePrev = useCallback(() => {
    if (isHistoryMode) {
      const currentMarkerPos = markerIndices.findIndex(
        idx => idx >= clampedIndex,
      );
      const prevMarkerIdx =
        currentMarkerPos > 0
          ? markerIndices[currentMarkerPos - 1]
          : (markerIndices[0] ?? 0);
      setCurrentStepIndex(prevMarkerIdx);
    } else {
      setCurrentStepIndex(prev => Math.max(prev - 1, 0));
    }
  }, [isHistoryMode, markerIndices, clampedIndex]);

  const handleNext = useCallback(() => {
    if (isHistoryMode) {
      const currentMarkerPos = markerIndices.findIndex(
        idx => idx > clampedIndex,
      );
      if (currentMarkerPos >= 0) {
        setCurrentStepIndex(markerIndices[currentMarkerPos]);
      } else if (interaction) {
        setCurrentStepIndex(steps.length);
      }
    } else {
      setCurrentStepIndex(prev => prev + 1);
    }
  }, [isHistoryMode, markerIndices, clampedIndex, interaction, steps.length]);

  const handleAudioEnded = useCallback(() => {
    setIsAudioPlaying(false);
    if (!isHistoryMode) {
      setCurrentStepIndex(prev => prev + 1);
    }
  }, [isHistoryMode]);

  const handlePlayStateChange = useCallback((playing: boolean) => {
    setIsAudioPlaying(playing);
  }, []);

  // ── Interaction send ──

  const handleInteractionSend = useCallback(
    (content: OnSendContentParams, blockBid: string) => {
      onSend?.(content, blockBid);
    },
    [onSend],
  );

  // ── Ask toggle (笔记/追问 button in ListenPlayer) ──

  const handleToggleAsk = useCallback(() => {
    setIsAskOpen(prev => !prev);
  }, []);

  // ── Disabled states ──

  const prevDisabled = isHistoryMode
    ? clampedIndex <= (markerIndices[0] ?? 0)
    : currentStepIndex <= 0;

  const nextDisabled = isHistoryMode
    ? clampedIndex >= (markerIndices[markerIndices.length - 1] ?? 0) &&
      !interaction
    : showInteraction;

  // ── Empty state ──

  if (!isLoading && steps.length === 0 && !interaction) {
    return (
      <div
        className={cn(
          'listen-reveal-wrapper',
          mobileStyle
            ? 'mobile bg-white'
            : 'bg-[var(--color-slide-desktop-bg)]',
        )}
        ref={chatRef}
      >
        <div className='flex h-full w-full items-center justify-center text-center text-[40px] font-bold leading-[1.3] text-primary'>
          {sectionTitle}
        </div>
      </div>
    );
  }

  const confirmButtonText = t('module.renderUi.core.confirm');
  const copyButtonText = t('module.renderUi.core.copyCode');
  const copiedButtonText = t('module.renderUi.core.copied');
  const shouldAutoPlay = !isHistoryMode;

  return (
    <div
      className={cn(
        'listen-reveal-wrapper',
        mobileStyle ? 'mobile bg-white' : 'bg-[var(--color-slide-desktop-bg)]',
      )}
      ref={chatRef}
    >
      {/* Visual content area */}
      <div className='listen-slide-shell'>
        {currentStep && !showInteraction && (
          <div className='h-full w-full overflow-auto p-6'>
            <ContentRender
              content={currentStep.content}
              enableTypewriter={false}
              readonly={true}
              confirmButtonText={confirmButtonText}
              copyButtonText={copyButtonText}
              copiedButtonText={copiedButtonText}
              onSend={() => {}}
              interactionDefaultValueOptions={
                lessonFeedbackInteractionDefaultValueOptions
              }
            />
            {/* Audio engine — hidden, controlled via ref */}
            <AudioPlayer
              ref={audioPlayerRef}
              key={currentStep.bid}
              audioUrl={currentStep.audioUrl}
              streamingSegments={playerSegments}
              isStreaming={Boolean(currentStep.isAudioStreaming)}
              autoPlay={shouldAutoPlay}
              onEnded={handleAudioEnded}
              onPlayStateChange={handlePlayStateChange}
              alwaysVisible={false}
              className='hidden'
            />
          </div>
        )}

        {showInteraction && (
          <div className='h-full w-full overflow-auto p-6'>
            {/* Interaction is rendered via ListenPlayer overlay */}
          </div>
        )}
      </div>

      {/* Ask panel — slides up from player bar when open */}
      {isAskOpen && currentStep && shifuBid && outlineBid && (
        <AskBlock
          askList={(currentStep.askList || []) as any[]}
          isExpanded={true}
          shifu_bid={shifuBid}
          outline_bid={outlineBid}
          preview_mode={previewMode}
          element_bid={currentStep.bid}
          isListenMode={true}
          onToggleAskExpanded={handleToggleAsk}
        />
      )}

      {/* Player bar */}
      <ListenPlayer
        mobileStyle={mobileStyle}
        isAudioPlaying={isAudioPlaying}
        onPlay={handlePlay}
        onPause={handlePause}
        onPrev={handlePrev}
        onNext={handleNext}
        prevDisabled={prevDisabled}
        nextDisabled={nextDisabled}
        interaction={showInteraction ? interaction : null}
        interactionReadonly={
          interaction
            ? Boolean(interaction.readonly) || Boolean(interaction.user_input)
            : undefined
        }
        onSend={handleInteractionSend}
        onNotes={handleToggleAsk}
        showControls={steps.length > 0 || Boolean(interaction)}
      />
    </div>
  );
};

ListenModeSlideRenderer.displayName = 'ListenModeSlideRenderer';

export default memo(ListenModeSlideRenderer);

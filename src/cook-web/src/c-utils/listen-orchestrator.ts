import type { AudioCompleteData, AvContractData } from '@/c-api/studyV2';

export const LISTEN_AUDIO_EVENT_TYPES = {
  AUDIO_SEGMENT: 'audio_segment',
  AUDIO_COMPLETE: 'audio_complete',
} as const;

type ListenAudioEventType =
  (typeof LISTEN_AUDIO_EVENT_TYPES)[keyof typeof LISTEN_AUDIO_EVENT_TYPES];

export const normalizeListenAudioPosition = (raw: unknown): number => {
  const position = Number(raw ?? 0);
  if (Number.isNaN(position) || position < 0) {
    return 0;
  }
  return Math.floor(position);
};

export const buildListenUnitId = ({
  type,
  generatedBlockBid,
  position,
  fallbackIndex,
  resolveContentBid,
}: {
  type: string;
  generatedBlockBid?: string | null;
  position?: unknown;
  fallbackIndex: number;
  resolveContentBid?: (blockBid: string | null) => string | null;
}): string => {
  if (type === 'content') {
    // Always use bid:position for content items to keep unit IDs stable
    // across list rebuilds.  slideId arrives asynchronously (via avContract /
    // backend slides) which would change the ID mid-sequence, causing
    // resolveCurrentSequenceIndex to return -1 and breaking playback.
    const resolved =
      resolveContentBid?.(generatedBlockBid || null) ?? generatedBlockBid ?? '';
    const stableBid = resolved || `unknown-${fallbackIndex}`;
    const stablePosition = normalizeListenAudioPosition(position);
    return `content:${stableBid}:${stablePosition}`;
  }

  if (type === 'interaction') {
    return `interaction:${generatedBlockBid || fallbackIndex}`;
  }

  return `other:${generatedBlockBid || fallbackIndex}`;
};

/**
 * Extract all available audio positions from a chat content item.
 * Consolidates positions from avContract, audios, and audioTracksByPosition.
 *
 * @param item - The chat content item to extract positions from
 * @returns Sorted array of unique audio positions
 *
 * @example
 * const positions = extractAudioPositions({
 *   avContract: { speakable_segments: [{ position: 0 }, { position: 1 }] },
 *   audios: [{ position: 2 }],
 *   audioTracksByPosition: { '3': { ... } },
 * });
 * // => [0, 1, 2, 3]
 */
export const extractAudioPositions = (item: {
  avContract?: Pick<AvContractData, 'speakable_segments'> | null;
  audios?: Array<{ position?: unknown }> | null;
  audioTracksByPosition?: Record<string, unknown> | null;
}): number[] => {
  // Extract positions from AV contract speakable segments
  const contractPositions = item.avContract?.speakable_segments
    ? item.avContract.speakable_segments
        .map(segment => Number(segment.position ?? 0))
        .filter(value => !Number.isNaN(value))
    : [];

  // Extract positions from persisted audio array
  const persistedPositions =
    item.audios && item.audios.length > 0
      ? Array.from(
          new Set(
            item.audios
              .map(audio => Number(audio.position ?? 0))
              .filter(value => !Number.isNaN(value)),
          ),
        )
      : [];

  // Extract positions from audio tracks by position map
  const trackPositions =
    item.audioTracksByPosition &&
    Object.keys(item.audioTracksByPosition).length > 0
      ? Object.keys(item.audioTracksByPosition)
          .map(Number)
          .filter(value => !Number.isNaN(value))
      : [];

  // Combine all positions, deduplicate, and sort
  return Array.from(
    new Set([...contractPositions, ...persistedPositions, ...trackPositions]),
  ).sort((a, b) => a - b);
};

export const mapContractSpeakablePages = ({
  avContract,
  previousVisualPageBeforeBlock,
  firstVisualPage,
  visualSegmentCount,
}: {
  avContract?: AvContractData | null;
  previousVisualPageBeforeBlock: number;
  firstVisualPage: number;
  visualSegmentCount: number;
}): number[] | null => {
  const speakableSegments = avContract?.speakable_segments || [];
  if (speakableSegments.length === 0) {
    return null;
  }

  const boundariesByEnd = (avContract?.visual_boundaries || [])
    .map(boundary => {
      const position = Number(boundary.position ?? -1);
      const sourceSpan = Array.isArray(boundary.source_span)
        ? boundary.source_span
        : [];
      const end = Number(sourceSpan[1] ?? -1);
      if (Number.isNaN(position) || Number.isNaN(end)) {
        return null;
      }
      return { position, end };
    })
    .filter(
      (boundary): boundary is { position: number; end: number } =>
        boundary !== null,
    )
    .sort((a, b) => a.end - b.end);

  const contractPages: number[] = [];
  speakableSegments.forEach(segment => {
    const position = Number(segment.position ?? -1);
    if (Number.isNaN(position) || position < 0) {
      return;
    }

    const sourceSpan = Array.isArray(segment.source_span)
      ? segment.source_span
      : [];
    const sourceStart = Number(sourceSpan[0] ?? -1);
    const precedingBoundary =
      !Number.isNaN(sourceStart) && sourceStart >= 0
        ? boundariesByEnd.filter(boundary => boundary.end <= sourceStart).pop()
        : undefined;
    if (
      !precedingBoundary ||
      precedingBoundary.position >= visualSegmentCount ||
      firstVisualPage < 0
    ) {
      contractPages[position] = previousVisualPageBeforeBlock;
      return;
    }
    contractPages[position] = firstVisualPage + precedingBoundary.position;
  });

  return contractPages.some(page => typeof page === 'number')
    ? contractPages
    : null;
};

export type ListenInboundAudioEvent = {
  type: ListenAudioEventType;
  generatedBlockBid: string;
  position: number;
  slideId?: string;
  payload: Record<string, unknown>;
};

type ListenRecordAudioLike = {
  position?: number;
  slide_id?: string;
  audio_url?: string;
  audio_bid?: string;
  duration_ms?: number;
  [key: string]: unknown;
};

type NormalizedListenRecordAudio = {
  position: number;
  slide_id?: string;
  audio_url?: string;
  audio_bid?: string;
  duration_ms?: number;
};

type NormalizedListenRecordAudios = {
  audios?: NormalizedListenRecordAudio[];
  audioSlideIdByPosition?: Record<number, string>;
  audioTracksByPosition?: Record<
    number,
    {
      audioUrl?: string;
      audioDurationMs?: number;
      audioBid?: string;
      isAudioStreaming: false;
    }
  >;
};

export const toListenInboundAudioEvent = (
  response: Record<string, unknown> | null | undefined,
  fallbackGeneratedBlockBid?: string,
): ListenInboundAudioEvent | null => {
  if (!response) {
    return null;
  }

  const eventType = String(response.type || '');
  if (
    eventType !== LISTEN_AUDIO_EVENT_TYPES.AUDIO_SEGMENT &&
    eventType !== LISTEN_AUDIO_EVENT_TYPES.AUDIO_COMPLETE
  ) {
    return null;
  }

  const payload = ((response.content ?? response.data ?? {}) || {}) as Record<
    string,
    unknown
  >;
  const generatedBlockBid =
    String(
      response.generated_block_bid ||
        payload.generated_block_bid ||
        fallbackGeneratedBlockBid ||
        '',
    ) || '';
  if (!generatedBlockBid) {
    return null;
  }

  return {
    type: eventType as ListenAudioEventType,
    generatedBlockBid,
    position: normalizeListenAudioPosition(payload.position),
    slideId:
      typeof payload.slide_id === 'string' && payload.slide_id
        ? payload.slide_id
        : undefined,
    payload,
  };
};

export const normalizeListenRecordAudios = ({
  audioUrl,
  audios,
}: {
  audioUrl?: string;
  audios?: Array<ListenRecordAudioLike | AudioCompleteData> | null;
}): NormalizedListenRecordAudios => {
  const normalizedList = (audios || [])
    .map(audio => ({
      position: normalizeListenAudioPosition(audio?.position),
      slide_id:
        typeof audio?.slide_id === 'string' ? audio.slide_id : undefined,
      audio_url:
        typeof audio?.audio_url === 'string' ? audio.audio_url : undefined,
      audio_bid:
        typeof audio?.audio_bid === 'string' ? audio.audio_bid : undefined,
      duration_ms:
        typeof audio?.duration_ms === 'number' ? audio.duration_ms : undefined,
    }))
    .sort((a, b) => a.position - b.position);

  // Backward compatibility: if only legacy audio_url exists, project it as position 0.
  if (!normalizedList.length && audioUrl) {
    normalizedList.push({
      position: 0,
      slide_id: undefined,
      audio_url: audioUrl,
      audio_bid: undefined,
      duration_ms: undefined,
    });
  }

  if (!normalizedList.length) {
    return {};
  }

  const slideIdByPosition = normalizedList.reduce(
    (acc, audio) => {
      if (audio.slide_id) {
        acc[audio.position] = audio.slide_id;
      }
      return acc;
    },
    {} as Record<number, string>,
  );

  const tracksByPosition = normalizedList.reduce(
    (acc, audio) => {
      acc[audio.position] = {
        audioUrl: audio.audio_url,
        audioDurationMs: audio.duration_ms,
        audioBid: audio.audio_bid,
        isAudioStreaming: false,
      };
      return acc;
    },
    {} as Record<
      number,
      {
        audioUrl?: string;
        audioDurationMs?: number;
        audioBid?: string;
        isAudioStreaming: false;
      }
    >,
  );

  return {
    audios: normalizedList,
    audioSlideIdByPosition:
      Object.keys(slideIdByPosition).length > 0 ? slideIdByPosition : undefined,
    audioTracksByPosition: tracksByPosition,
  };
};

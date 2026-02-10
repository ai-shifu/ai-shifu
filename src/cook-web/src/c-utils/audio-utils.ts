import type {
  AudioCompleteData,
  AudioSegmentData,
  AudioUrlEntry,
} from '@/c-api/studyV2';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
}

/** Per-position audio state within a block. */
export interface BlockAudioPosition {
  position: number;
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  audioDurationMs?: number;
  isAudioStreaming?: boolean;
}

export interface AudioItem {
  generated_block_bid: string;
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
  /** Per-position audio entries (populated when block has visual boundaries). */
  audioPositions?: BlockAudioPosition[];
}

type EnsureItem<T> = (items: T[], blockId: string) => T[];

export interface AudioSegmentPayload {
  segment_index?: number;
  segmentIndex?: number;
  audio_data?: string;
  audioData?: string;
  duration_ms?: number;
  durationMs?: number;
  is_final?: boolean;
  isFinal?: boolean;
}

export const normalizeAudioSegmentPayload = (
  payload: AudioSegmentPayload,
): AudioSegment | null => {
  const segmentIndex = payload.segment_index ?? payload.segmentIndex;
  const audioData = payload.audio_data ?? payload.audioData;

  if (segmentIndex === undefined || !audioData) {
    return null;
  }

  return {
    segmentIndex,
    audioData,
    durationMs: payload.duration_ms ?? payload.durationMs ?? 0,
    isFinal: payload.is_final ?? payload.isFinal ?? false,
  };
};

const toAudioSegment = (segment: AudioSegmentData): AudioSegment => ({
  segmentIndex: segment.segment_index,
  audioData: segment.audio_data,
  durationMs: segment.duration_ms,
  isFinal: segment.is_final,
});

export const mergeAudioSegment = (
  segments: AudioSegment[],
  incoming: AudioSegment,
): AudioSegment[] => {
  if (
    segments.some(segment => segment.segmentIndex === incoming.segmentIndex)
  ) {
    return segments;
  }
  return [...segments, incoming].sort(
    (a, b) => a.segmentIndex - b.segmentIndex,
  );
};

/**
 * Find or create a BlockAudioPosition entry for the given position.
 */
const ensurePosition = (
  positions: BlockAudioPosition[],
  pos: number,
): BlockAudioPosition[] => {
  if (positions.some(p => p.position === pos)) {
    return positions;
  }
  return [...positions, { position: pos }].sort(
    (a, b) => a.position - b.position,
  );
};

export const upsertAudioSegment = <T extends AudioItem>(
  items: T[],
  blockId: string,
  segment: AudioSegmentData,
  ensureItem?: EnsureItem<T>,
): T[] => {
  const nextItems = ensureItem ? ensureItem(items, blockId) : items;
  const mappedSegment = toAudioSegment(segment);
  const position = segment.position ?? 0;

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    // Always update the per-position array
    const currentPositions = ensurePosition(
      item.audioPositions || [],
      position,
    );
    const updatedPositions = currentPositions.map(p => {
      if (p.position !== position) return p;
      const existing = p.audioSegments || [];
      const merged = mergeAudioSegment(existing, mappedSegment);
      if (merged === existing) return p;
      return {
        ...p,
        audioSegments: merged,
        isAudioStreaming: !mappedSegment.isFinal,
      };
    });

    // Backward compat: also mirror position 0 to top-level fields
    if (position === 0) {
      const existingSegments = item.audioSegments || [];
      const updatedSegments = mergeAudioSegment(
        existingSegments,
        mappedSegment,
      );
      return {
        ...item,
        audioSegments:
          updatedSegments !== existingSegments
            ? updatedSegments
            : item.audioSegments,
        isAudioStreaming: !mappedSegment.isFinal,
        audioPositions: updatedPositions,
      };
    }

    return {
      ...item,
      audioPositions: updatedPositions,
    };
  });
};

export const upsertAudioComplete = <T extends AudioItem>(
  items: T[],
  blockId: string,
  complete: Partial<AudioCompleteData>,
  ensureItem?: EnsureItem<T>,
): T[] => {
  const nextItems = ensureItem ? ensureItem(items, blockId) : items;
  const position = complete.position ?? 0;

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    // Always update the per-position array
    const currentPositions = ensurePosition(
      item.audioPositions || [],
      position,
    );
    const updatedPositions = currentPositions.map(p => {
      if (p.position !== position) return p;
      return {
        ...p,
        audioUrl: complete.audio_url ?? undefined,
        audioDurationMs: complete.duration_ms,
        isAudioStreaming: false,
      };
    });

    // Backward compat: also mirror position 0 to top-level fields
    if (position === 0) {
      return {
        ...item,
        audioUrl: complete.audio_url ?? undefined,
        audioDurationMs: complete.duration_ms,
        isAudioStreaming: false,
        audioPositions: updatedPositions,
      };
    }

    return {
      ...item,
      audioPositions: updatedPositions,
    };
  });
};

/**
 * Build audioPositions from a history record's audio_urls list.
 * Returns undefined if the input is empty/missing (single-position legacy).
 */
export const buildAudioPositionsFromHistory = (
  audioUrls?: AudioUrlEntry[],
): BlockAudioPosition[] | undefined => {
  if (!audioUrls || audioUrls.length === 0) return undefined;
  return audioUrls
    .map(entry => ({
      position: entry.position,
      audioUrl: entry.audio_url,
      audioDurationMs: entry.duration_ms,
      isAudioStreaming: false,
    }))
    .sort((a, b) => a.position - b.position);
};

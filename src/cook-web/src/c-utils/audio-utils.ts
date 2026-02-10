import type { AudioCompleteData, AudioSegmentData } from '@/c-api/studyV2';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
}

export interface AudioPartState {
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
}

export interface AudioItem {
  generated_block_bid: string;
  audioParts?: Record<number, AudioPartState>;
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
}

type EnsureItem<T> = (items: T[], blockId: string) => T[];

export interface AudioSegmentPayload {
  position?: number;
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

export const getAudioPart = <T extends AudioItem>(
  item: T | undefined | null,
  position: number,
): AudioPartState | null => {
  if (!item) {
    return null;
  }
  const pos = Number.isFinite(position) ? position : 0;
  const parts = item.audioParts;
  if (parts && parts[pos]) {
    return parts[pos] ?? null;
  }
  if (pos === 0) {
    return {
      audioSegments: item.audioSegments,
      audioUrl: item.audioUrl,
      isAudioStreaming: item.isAudioStreaming,
      audioDurationMs: item.audioDurationMs,
    };
  }
  return null;
};

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

export const upsertAudioSegment = <T extends AudioItem>(
  items: T[],
  blockId: string,
  segment: AudioSegmentData,
  ensureItem?: EnsureItem<T>,
  position: number = 0,
): T[] => {
  const nextItems = ensureItem ? ensureItem(items, blockId) : items;
  const mappedSegment = toAudioSegment(segment);
  const pos = Number.isFinite(position) ? position : 0;

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    const existingPart = getAudioPart(item, pos) ?? {};
    const existingSegments = existingPart.audioSegments || [];
    const updatedSegments = mergeAudioSegment(existingSegments, mappedSegment);
    const nextIsStreaming = !mappedSegment.isFinal;
    if (
      updatedSegments === existingSegments &&
      Boolean(existingPart.isAudioStreaming) === Boolean(nextIsStreaming)
    ) {
      return item;
    }

    const nextPart: AudioPartState = {
      ...existingPart,
      audioSegments: updatedSegments,
      isAudioStreaming: nextIsStreaming,
    };

    const nextAudioParts = {
      ...(item.audioParts || {}),
      [pos]: nextPart,
    };

    return {
      ...item,
      audioParts: nextAudioParts,
      ...(pos === 0
        ? {
            audioSegments: updatedSegments,
            isAudioStreaming: nextIsStreaming,
          }
        : null),
    };
  });
};

export const upsertAudioComplete = <T extends AudioItem>(
  items: T[],
  blockId: string,
  complete: Partial<AudioCompleteData>,
  ensureItem?: EnsureItem<T>,
  position: number = 0,
): T[] => {
  const nextItems = ensureItem ? ensureItem(items, blockId) : items;
  const pos = Number.isFinite(position) ? position : 0;

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    const existingPart = getAudioPart(item, pos) ?? {};
    const nextPart: AudioPartState = {
      ...existingPart,
      audioUrl: complete.audio_url ?? undefined,
      audioDurationMs: complete.duration_ms,
      isAudioStreaming: false,
    };
    const nextAudioParts = {
      ...(item.audioParts || {}),
      [pos]: nextPart,
    };

    return {
      ...item,
      audioParts: nextAudioParts,
      ...(pos === 0
        ? {
            audioUrl: complete.audio_url ?? undefined,
            audioDurationMs: complete.duration_ms,
            isAudioStreaming: false,
          }
        : null),
    };
  });
};

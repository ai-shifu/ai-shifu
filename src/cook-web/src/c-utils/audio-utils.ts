import type { AudioCompleteData, AudioSegmentData } from '@/c-api/studyV2';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
}

export interface AudioItem {
  generated_block_bid: string;
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
}

type EnsureItem<T> = (items: T[], blockId: string) => T[];

const toAudioSegment = (segment: AudioSegmentData): AudioSegment => ({
  segmentIndex: segment.segment_index,
  audioData: segment.audio_data,
  durationMs: segment.duration_ms,
  isFinal: segment.is_final,
});

const mergeAudioSegment = (
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
): T[] => {
  const nextItems = ensureItem ? ensureItem(items, blockId) : items;
  const mappedSegment = toAudioSegment(segment);

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    const existingSegments = item.audioSegments || [];
    const updatedSegments = mergeAudioSegment(existingSegments, mappedSegment);
    if (updatedSegments === existingSegments) {
      return item;
    }

    return {
      ...item,
      audioSegments: updatedSegments,
      isAudioStreaming: !mappedSegment.isFinal,
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

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    return {
      ...item,
      audioUrl: complete.audio_url ?? undefined,
      audioDurationMs: complete.duration_ms,
      isAudioStreaming: false,
    };
  });
};

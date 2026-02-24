import type {
  AudioCompleteData,
  AudioRecordData,
  AudioSegmentData,
} from '@/c-api/studyV2';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
  position?: number; // Positional index within block
}

// Completed audio record with position
export interface AudioRecord {
  position: number;
  audioUrl: string;
  audioBid: string;
  durationMs: number;
}

export interface AudioItem {
  generated_block_bid: string;
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
  audioRecords?: AudioRecord[]; // Positional audio records (ordered by position)
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
  position: segment.position,
});

export const toAudioRecord = (data: AudioRecordData): AudioRecord => ({
  position: data.position,
  audioUrl: data.audio_url,
  audioBid: data.audio_bid,
  durationMs: data.duration_ms,
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

    const position = complete.position ?? 0;
    const newRecord: AudioRecord = {
      position,
      audioUrl: complete.audio_url ?? '',
      audioBid: (complete as AudioCompleteData).audio_bid ?? '',
      durationMs: complete.duration_ms ?? 0,
    };

    // Accumulate positional audio records (deduplicate by position)
    const existing = item.audioRecords ?? [];
    const alreadyExists = existing.some(r => r.position === position);
    const audioRecords = alreadyExists
      ? existing.map(r => (r.position === position ? newRecord : r))
      : [...existing, newRecord].sort((a, b) => a.position - b.position);

    return {
      ...item,
      // Backward compatible: first audio URL
      audioUrl: audioRecords[0]?.audioUrl ?? complete.audio_url ?? undefined,
      audioDurationMs: complete.duration_ms,
      isAudioStreaming: false,
      audioRecords,
    };
  });
};

import type { AudioCompleteData, AudioSegmentData } from '@/c-api/studyV2';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
}

export interface AudioTrack {
  audioBid: string;
  audioUrl: string;
  durationMs: number;
  position: number;
}

export interface AudioItem {
  generated_block_bid: string;
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
  audioTracks?: AudioTrack[];
  audioPlaybackBid?: string;
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

const toAudioTrack = (
  complete: Partial<AudioCompleteData>,
): AudioTrack | null => {
  const audioUrl = complete.audio_url;
  if (!audioUrl) {
    return null;
  }
  return {
    audioBid: complete.audio_bid ?? '',
    audioUrl,
    durationMs: complete.duration_ms ?? 0,
    position: Number(complete.position ?? 0),
  };
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

export const mergeAudioTrack = (
  tracks: AudioTrack[],
  incoming: AudioTrack,
): AudioTrack[] => {
  const existingIndex = tracks.findIndex(
    track => track.position === incoming.position,
  );
  if (existingIndex < 0) {
    return [...tracks, incoming].sort((a, b) => a.position - b.position);
  }
  const existing = tracks[existingIndex];
  if (
    existing.audioBid === incoming.audioBid &&
    existing.audioUrl === incoming.audioUrl &&
    existing.durationMs === incoming.durationMs
  ) {
    return tracks;
  }
  const nextTracks = [...tracks];
  nextTracks[existingIndex] = incoming;
  return nextTracks.sort((a, b) => a.position - b.position);
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
  const nextTrack = toAudioTrack(complete);

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    const existingTracks = item.audioTracks || [];
    const updatedTracks = nextTrack
      ? mergeAudioTrack(existingTracks, nextTrack)
      : existingTracks;
    const fallbackTrack = updatedTracks[0];

    return {
      ...item,
      audioUrl: fallbackTrack?.audioUrl ?? complete.audio_url ?? undefined,
      audioDurationMs:
        fallbackTrack?.durationMs ??
        complete.duration_ms ??
        item.audioDurationMs,
      audioTracks: updatedTracks,
      isAudioStreaming: false,
    };
  });
};

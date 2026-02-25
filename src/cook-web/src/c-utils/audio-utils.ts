import type { AudioCompleteData, AudioSegmentData } from '@/c-api/studyV2';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
  position?: number;
  slideId?: string;
  avContract?: Record<string, any> | null;
}

export interface AudioTrack {
  position: number;
  slideId?: string;
  audioUrl?: string;
  durationMs?: number;
  isAudioStreaming?: boolean;
  audioSegments?: AudioSegment[];
  avContract?: Record<string, any> | null;
}

export interface AudioItem {
  generated_block_bid: string;
  audioSegments?: AudioSegment[];
  audioTracks?: AudioTrack[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
}

type EnsureItem<T> = (items: T[], blockId: string) => T[];

const logAudioUtilsDebug = (event: string, payload?: Record<string, any>) => {
  if (process.env.NODE_ENV === 'production') {
    return;
  }
  console.log(`[listen-audio-debug] ${event}`, payload ?? {});
};

export interface AudioSegmentPayload {
  segment_index?: number;
  segmentIndex?: number;
  audio_data?: string;
  audioData?: string;
  duration_ms?: number;
  durationMs?: number;
  is_final?: boolean;
  isFinal?: boolean;
  position?: number;
  slide_id?: string;
  slideId?: string;
  av_contract?: Record<string, any> | null;
  avContract?: Record<string, any> | null;
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
    position: payload.position,
    slideId: payload.slide_id ?? payload.slideId,
    avContract: payload.av_contract ?? payload.avContract ?? null,
  };
};

const toAudioSegment = (segment: AudioSegmentData): AudioSegment => ({
  segmentIndex: segment.segment_index,
  audioData: segment.audio_data,
  durationMs: segment.duration_ms,
  isFinal: segment.is_final,
  position: segment.position,
  slideId: segment.slide_id,
  avContract: segment.av_contract ?? null,
});

export const mergeAudioSegment = (
  segments: AudioSegment[],
  incoming: AudioSegment,
): AudioSegment[] => {
  const isDuplicated = segments.some(
    segment =>
      segment.segmentIndex === incoming.segmentIndex &&
      (segment.position ?? 0) === (incoming.position ?? 0),
  );
  if (isDuplicated) {
    logAudioUtilsDebug('audio-utils-segment-deduped', {
      segmentIndex: incoming.segmentIndex,
      position: incoming.position ?? 0,
      existingSegments: segments.length,
    });
    return segments;
  }
  return [...segments, incoming].sort(
    (a, b) =>
      (a.position ?? 0) - (b.position ?? 0) || a.segmentIndex - b.segmentIndex,
  );
};

const upsertAudioTrackSegment = (
  tracks: AudioTrack[],
  incoming: AudioSegment,
): AudioTrack[] => {
  const nextTracks = [...tracks];
  const position = incoming.position ?? 0;
  const targetIndex = nextTracks.findIndex(
    track => (track.position ?? 0) === position,
  );
  const currentTrack: AudioTrack =
    targetIndex >= 0
      ? { ...nextTracks[targetIndex] }
      : {
          position,
          audioSegments: [],
          isAudioStreaming: true,
        };

  currentTrack.audioSegments = mergeAudioSegment(
    currentTrack.audioSegments ?? [],
    incoming,
  );
  if (incoming.slideId) {
    currentTrack.slideId = incoming.slideId;
  }
  if (incoming.avContract) {
    currentTrack.avContract = incoming.avContract;
  }
  currentTrack.isAudioStreaming = !incoming.isFinal;

  if (targetIndex >= 0) {
    nextTracks[targetIndex] = currentTrack;
  } else {
    nextTracks.push(currentTrack);
  }

  return nextTracks.sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
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
    const updatedTracks = upsertAudioTrackSegment(
      item.audioTracks ?? [],
      mappedSegment,
    );
    const hasStreamingTrack = updatedTracks.some(
      track => track.isAudioStreaming,
    );

    const hasNoChanges =
      updatedSegments === existingSegments &&
      updatedTracks.length === (item.audioTracks ?? []).length &&
      updatedTracks.every(
        (track, index) => track === (item.audioTracks ?? [])[index],
      );
    logAudioUtilsDebug('audio-utils-upsert-segment', {
      blockId,
      segmentIndex: mappedSegment.segmentIndex,
      position: mappedSegment.position ?? 0,
      existingSegments: existingSegments.length,
      mergedSegments: updatedSegments.length,
      existingTracks: item.audioTracks?.length ?? 0,
      mergedTracks: updatedTracks.length,
      hasNoChanges,
      isFinal: mappedSegment.isFinal,
    });
    if (hasNoChanges) {
      return item;
    }

    return {
      ...item,
      audioSegments: updatedSegments,
      audioTracks: updatedTracks,
      isAudioStreaming: hasStreamingTrack || !mappedSegment.isFinal,
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
  const position =
    complete.position === undefined || complete.position === null
      ? null
      : Number(complete.position);

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    if (position !== null && Number.isFinite(position)) {
      const nextTracks = [...(item.audioTracks ?? [])];
      const targetIndex = nextTracks.findIndex(
        track => (track.position ?? 0) === position,
      );
      const currentTrack: AudioTrack =
        targetIndex >= 0
          ? { ...nextTracks[targetIndex] }
          : {
              position,
              audioSegments: [],
              isAudioStreaming: false,
            };

      currentTrack.audioUrl = complete.audio_url ?? currentTrack.audioUrl;
      currentTrack.durationMs = complete.duration_ms ?? currentTrack.durationMs;
      currentTrack.isAudioStreaming = false;
      if (complete.slide_id) {
        currentTrack.slideId = complete.slide_id;
      }
      if (complete.av_contract) {
        currentTrack.avContract = complete.av_contract;
      }

      if (targetIndex >= 0) {
        nextTracks[targetIndex] = currentTrack;
      } else {
        nextTracks.push(currentTrack);
      }
      nextTracks.sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
      logAudioUtilsDebug('audio-utils-upsert-complete', {
        blockId,
        position,
        trackIndex: targetIndex,
        hasAudioUrl: Boolean(currentTrack.audioUrl),
        durationMs: currentTrack.durationMs ?? 0,
        trackCount: nextTracks.length,
      });

      const singleTrack = nextTracks.length === 1 ? nextTracks[0] : null;

      return {
        ...item,
        audioTracks: nextTracks,
        audioUrl: singleTrack?.audioUrl,
        audioDurationMs: singleTrack?.durationMs,
        isAudioStreaming: nextTracks.some(track => track.isAudioStreaming),
      };
    }

    return {
      ...item,
      audioUrl: complete.audio_url ?? undefined,
      audioDurationMs: complete.duration_ms,
      isAudioStreaming: false,
    };
  });
};

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
type SegmentKeyParams = {
  segmentIndex: number;
  position?: number | null;
};

const DEFAULT_AUDIO_POSITION = 0;

const normalizeAudioPosition = (position?: number | null) =>
  Number(position ?? DEFAULT_AUDIO_POSITION);

const logAudioUtilsDebug = (event: string, payload?: Record<string, any>) => {
  // if (process.env.NODE_ENV === 'production') {
  return;
  // }
  console.log(`[listen-audio-debug] ${event}`, payload ?? {});
};

export const sortAudioTracksByPosition = <T extends { position?: number }>(
  tracks: T[] = [],
) =>
  [...tracks].sort(
    (a, b) =>
      normalizeAudioPosition(a.position) - normalizeAudioPosition(b.position),
  );

export const sortAudioSegmentsByIndex = <T extends { segmentIndex: number }>(
  segments: T[] = [],
) => [...segments].sort((a, b) => a.segmentIndex - b.segmentIndex);

export const getAudioTrackByPosition = <T extends { position?: number }>(
  tracks: T[] = [],
  position: number = DEFAULT_AUDIO_POSITION,
): T | null => {
  if (!tracks.length) {
    return null;
  }
  const normalizedPosition = normalizeAudioPosition(position);
  const orderedTracks = sortAudioTracksByPosition(tracks);
  return (
    orderedTracks.find(
      track => normalizeAudioPosition(track.position) === normalizedPosition,
    ) ?? orderedTracks[0]
  );
};

export const hasAudioContentInTrack = (
  track?: Pick<
    AudioTrack,
    'audioUrl' | 'isAudioStreaming' | 'audioSegments'
  > | null,
) =>
  Boolean(
    track?.audioUrl ||
    track?.isAudioStreaming ||
    (track?.audioSegments && track.audioSegments.length > 0),
  );

export const hasAudioContentInTracks = (
  tracks: Array<
    Pick<AudioTrack, 'audioUrl' | 'isAudioStreaming' | 'audioSegments'>
  > = [],
) => tracks.some(track => hasAudioContentInTrack(track));

export const buildAudioSegmentUniqueKey = (
  blockId: string,
  params: SegmentKeyParams,
) =>
  `${blockId}:${normalizeAudioPosition(params.position)}:${params.segmentIndex}`;

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
  position: normalizeAudioPosition(segment.position),
  slideId: segment.slide_id,
  avContract: segment.av_contract ?? null,
});

export const mergeAudioSegmentByUniqueKey = (
  blockId: string,
  segments: AudioSegment[],
  incoming: AudioSegment,
): AudioSegment[] => {
  const incomingKey = buildAudioSegmentUniqueKey(blockId, incoming);
  const isDuplicated = segments.some(
    segment => buildAudioSegmentUniqueKey(blockId, segment) === incomingKey,
  );
  if (isDuplicated) {
    logAudioUtilsDebug('audio-utils-segment-deduped', {
      blockId,
      dedupeKey: incomingKey,
      segmentIndex: incoming.segmentIndex,
      position: normalizeAudioPosition(incoming.position),
      existingSegments: segments.length,
    });
    return segments;
  }
  return sortAudioSegmentsByIndex([...segments, incoming]);
};

const upsertAudioTrackSegment = (
  blockId: string,
  tracks: AudioTrack[],
  incoming: AudioSegment,
): AudioTrack[] => {
  const position = normalizeAudioPosition(incoming.position);
  const targetIndex = tracks.findIndex(
    track => normalizeAudioPosition(track.position) === position,
  );
  const existingTrack = targetIndex >= 0 ? tracks[targetIndex] : undefined;
  const existingSegments = existingTrack?.audioSegments ?? [];
  const nextSegments = mergeAudioSegmentByUniqueKey(
    blockId,
    existingSegments,
    incoming,
  );
  const nextStreaming = !incoming.isFinal;

  const hasNoChanges =
    existingTrack &&
    nextSegments === existingSegments &&
    existingTrack.isAudioStreaming === nextStreaming &&
    (!incoming.slideId || existingTrack.slideId === incoming.slideId) &&
    (!incoming.avContract || existingTrack.avContract === incoming.avContract);
  if (hasNoChanges) {
    return tracks;
  }

  const nextTrack: AudioTrack = existingTrack
    ? { ...existingTrack }
    : {
        position,
        audioSegments: [],
        isAudioStreaming: true,
      };

  nextTrack.position = position;
  nextTrack.audioSegments = nextSegments;
  nextTrack.isAudioStreaming = nextStreaming;
  if (incoming.slideId) {
    nextTrack.slideId = incoming.slideId;
  }
  if (incoming.avContract) {
    nextTrack.avContract = incoming.avContract;
  }

  if (targetIndex >= 0) {
    const nextTracks = [...tracks];
    nextTracks[targetIndex] = nextTrack;
    return sortAudioTracksByPosition(nextTracks);
  }
  return sortAudioTracksByPosition([...tracks, nextTrack]);
};

const normalizeTrackForUpsert = (
  complete: Partial<AudioCompleteData>,
): {
  position: number;
  slideId?: string;
  avContract?: Record<string, any> | null;
} => {
  const parsedPosition =
    complete.position === undefined || complete.position === null
      ? NaN
      : Number(complete.position);
  return {
    position: Number.isFinite(parsedPosition)
      ? parsedPosition
      : DEFAULT_AUDIO_POSITION,
    slideId: complete.slide_id ?? undefined,
    avContract: complete.av_contract ?? null,
  };
};

const upsertAudioTrackComplete = (
  tracks: AudioTrack[],
  complete: Partial<AudioCompleteData>,
): AudioTrack[] => {
  const { position, slideId, avContract } = normalizeTrackForUpsert(complete);
  const targetIndex = tracks.findIndex(
    track => normalizeAudioPosition(track.position) === position,
  );
  const existingTrack = targetIndex >= 0 ? tracks[targetIndex] : undefined;
  const hasNoChanges =
    existingTrack &&
    existingTrack.audioUrl === (complete.audio_url ?? existingTrack.audioUrl) &&
    existingTrack.durationMs ===
      (complete.duration_ms ?? existingTrack.durationMs) &&
    existingTrack.isAudioStreaming === false &&
    (!slideId || existingTrack.slideId === slideId) &&
    (!avContract || existingTrack.avContract === avContract);
  if (hasNoChanges) {
    return tracks;
  }

  const nextTrack: AudioTrack = existingTrack
    ? { ...existingTrack }
    : {
        position,
        audioSegments: [],
        isAudioStreaming: false,
      };
  nextTrack.position = position;
  nextTrack.audioUrl = complete.audio_url ?? nextTrack.audioUrl;
  nextTrack.durationMs = complete.duration_ms ?? nextTrack.durationMs;
  nextTrack.isAudioStreaming = false;
  if (slideId) {
    nextTrack.slideId = slideId;
  }
  if (avContract) {
    nextTrack.avContract = avContract;
  }

  if (targetIndex >= 0) {
    const nextTracks = [...tracks];
    nextTracks[targetIndex] = nextTrack;
    return sortAudioTracksByPosition(nextTracks);
  }
  return sortAudioTracksByPosition([...tracks, nextTrack]);
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

    const existingTracks = item.audioTracks ?? [];
    const updatedTracks = upsertAudioTrackSegment(
      blockId,
      existingTracks,
      mappedSegment,
    );
    const hasStreamingTrack = updatedTracks.some(
      track => track.isAudioStreaming,
    );

    const hasNoChanges = updatedTracks === existingTracks;
    logAudioUtilsDebug('audio-utils-upsert-segment', {
      blockId,
      segmentIndex: mappedSegment.segmentIndex,
      dedupeKey: buildAudioSegmentUniqueKey(blockId, mappedSegment),
      position: normalizeAudioPosition(mappedSegment.position),
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

  return nextItems.map(item => {
    if (item.generated_block_bid !== blockId) {
      return item;
    }

    const existingTracks = item.audioTracks ?? [];
    const nextTracks = upsertAudioTrackComplete(existingTracks, complete);
    const { position } = normalizeTrackForUpsert(complete);
    const targetTrack =
      getAudioTrackByPosition(nextTracks, position) ??
      getAudioTrackByPosition(nextTracks);
    const nextIsAudioStreaming = nextTracks.some(
      track => track.isAudioStreaming,
    );
    const hasNoChanges =
      nextTracks === existingTracks &&
      item.audioUrl === targetTrack?.audioUrl &&
      item.audioDurationMs === targetTrack?.durationMs &&
      Boolean(item.isAudioStreaming) === Boolean(nextIsAudioStreaming);
    logAudioUtilsDebug('audio-utils-upsert-complete', {
      blockId,
      position,
      hasAudioUrl: Boolean(targetTrack?.audioUrl),
      durationMs: targetTrack?.durationMs ?? 0,
      trackCount: nextTracks.length,
      hasNoChanges,
    });
    if (hasNoChanges) {
      return item;
    }

    return {
      ...item,
      audioTracks: nextTracks,
      audioUrl: targetTrack?.audioUrl,
      audioDurationMs: targetTrack?.durationMs,
      isAudioStreaming: nextIsAudioStreaming,
    };
  });
};

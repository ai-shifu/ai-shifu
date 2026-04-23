import type {
  AudioCompleteData,
  AudioSegmentData,
  SubtitleCueData,
} from '@/c-api/studyV2';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
  subtitleCues?: SubtitleCueData[];
  position?: number;
  elementId?: string;
  slideId?: string;
  avContract?: Record<string, any> | null;
}

export interface AudioTrack {
  position: number;
  slideId?: string;
  audioUrl?: string;
  durationMs?: number;
  isAudioStreaming?: boolean;
  subtitleCues?: SubtitleCueData[];
  audioSegments?: AudioSegment[];
  avContract?: Record<string, any> | null;
}

export interface AudioItem {
  element_bid: string;
  audioSegments?: AudioSegment[];
  audioTracks?: AudioTrack[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
}

type EnsureItem<T> = (items: T[], elementBid: string) => T[];
type SegmentKeyParams = {
  segmentIndex: number;
  position?: number | null;
  elementId?: string | null;
};

const DEFAULT_AUDIO_POSITION = 0;

const normalizeAudioPosition = (position?: number | null) =>
  Number(position ?? DEFAULT_AUDIO_POSITION);

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
  elementBid: string,
  params: SegmentKeyParams,
) =>
  [
    elementBid,
    params.elementId ?? '',
    normalizeAudioPosition(params.position),
    params.segmentIndex,
  ].join(':');

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
  element_id?: string;
  elementId?: string;
  slide_id?: string;
  slideId?: string;
  subtitle_cues?: SubtitleCueData[];
  subtitleCues?: SubtitleCueData[];
  av_contract?: Record<string, any> | null;
  avContract?: Record<string, any> | null;
}

const normalizeSubtitleCueNumber = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim()) {
    const parsedValue = Number(value);
    if (Number.isFinite(parsedValue)) {
      return parsedValue;
    }
  }

  return null;
};

const sortSubtitleCues = (cues: SubtitleCueData[]) =>
  [...cues].sort(
    (prevCue, nextCue) =>
      Number(prevCue.position ?? 0) - Number(nextCue.position ?? 0) ||
      Number(prevCue.start_ms ?? 0) - Number(nextCue.start_ms ?? 0) ||
      Number(prevCue.end_ms ?? 0) - Number(nextCue.end_ms ?? 0) ||
      Number(prevCue.segment_index ?? 0) - Number(nextCue.segment_index ?? 0),
  );

const normalizeSubtitleCues = (
  rawSubtitleCues: unknown,
): SubtitleCueData[] | undefined => {
  if (!Array.isArray(rawSubtitleCues)) {
    return undefined;
  }

  const normalizedSubtitleCues = rawSubtitleCues.reduce<SubtitleCueData[]>(
    (result, cue) => {
      if (!cue || typeof cue !== 'object') {
        return result;
      }

      const rawCue = cue as Record<string, unknown>;
      const text = typeof rawCue.text === 'string' ? rawCue.text : undefined;
      const startMs = normalizeSubtitleCueNumber(
        rawCue.start_ms ?? rawCue.startMs,
      );
      const endMs = normalizeSubtitleCueNumber(rawCue.end_ms ?? rawCue.endMs);

      if (!text || startMs === null || endMs === null) {
        return result;
      }

      const segmentIndex = normalizeSubtitleCueNumber(
        rawCue.segment_index ?? rawCue.segmentIndex,
      );
      const position = normalizeSubtitleCueNumber(rawCue.position);

      result.push({
        text,
        start_ms: startMs,
        end_ms: endMs,
        ...(segmentIndex === null ? {} : { segment_index: segmentIndex }),
        ...(position === null ? {} : { position }),
      });

      return result;
    },
    [],
  );

  return normalizedSubtitleCues.length > 0
    ? sortSubtitleCues(normalizedSubtitleCues)
    : undefined;
};

const resolveLatestSegmentSubtitleCues = (
  segments: AudioSegment[] = [],
): SubtitleCueData[] | undefined => {
  const latestSegmentWithSubtitleCues = [...sortAudioSegmentsByIndex(segments)]
    .reverse()
    .find(
      segment =>
        Array.isArray(segment.subtitleCues) && segment.subtitleCues.length > 0,
    );

  return latestSegmentWithSubtitleCues?.subtitleCues;
};

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
    subtitleCues: normalizeSubtitleCues(
      payload.subtitle_cues ?? payload.subtitleCues,
    ),
    position: payload.position,
    elementId: payload.element_id ?? payload.elementId,
    slideId: payload.slide_id ?? payload.slideId,
    avContract: payload.av_contract ?? payload.avContract ?? null,
  };
};

const toAudioSegment = (segment: AudioSegmentData): AudioSegment => ({
  segmentIndex: segment.segment_index,
  audioData: segment.audio_data,
  durationMs: segment.duration_ms,
  isFinal: segment.is_final,
  subtitleCues: normalizeSubtitleCues(segment.subtitle_cues),
  position: normalizeAudioPosition(segment.position),
  elementId: segment.element_id,
  slideId: segment.slide_id,
  avContract: segment.av_contract ?? null,
});

export const toAudioSegmentData = (segment: AudioSegment): AudioSegmentData => {
  const subtitleCues = normalizeSubtitleCues(segment.subtitleCues);

  return {
    segment_index: segment.segmentIndex,
    audio_data: segment.audioData,
    duration_ms: segment.durationMs,
    is_final: segment.isFinal,
    position: normalizeAudioPosition(segment.position),
    element_id: segment.elementId,
    slide_id: segment.slideId,
    av_contract: segment.avContract ?? null,
    ...(subtitleCues ? { subtitle_cues: subtitleCues } : {}),
  };
};

export const getAudioSegmentDataListFromTracks = (
  tracks: AudioTrack[] = [],
): AudioSegmentData[] =>
  sortAudioTracksByPosition(tracks).flatMap(track => {
    const orderedSegments = sortAudioSegmentsByIndex(track.audioSegments ?? []);
    const finalSegmentIndex = orderedSegments.length - 1;

    return orderedSegments.map((segment, index) =>
      toAudioSegmentData(
        index === finalSegmentIndex &&
          Array.isArray(track.subtitleCues) &&
          track.subtitleCues.length > 0
          ? { ...segment, subtitleCues: track.subtitleCues }
          : segment,
      ),
    );
  });

export const mergeAudioSegmentDataList = (
  elementBid: string,
  segments: AudioSegmentData[] = [],
): AudioSegmentData[] => {
  const mergedSegments = segments.reduce<AudioSegment[]>((result, segment) => {
    const normalizedSegment = normalizeAudioSegmentPayload(segment);

    if (!normalizedSegment) {
      return result;
    }

    return mergeAudioSegmentByUniqueKey(elementBid, result, normalizedSegment);
  }, []);

  return mergedSegments.map(toAudioSegmentData);
};

export const mergeAudioSegmentByUniqueKey = (
  blockId: string,
  segments: AudioSegment[],
  incoming: AudioSegment,
): AudioSegment[] => {
  const incomingKey = buildAudioSegmentUniqueKey(blockId, incoming);
  const duplicatedIndex = segments.findIndex(
    segment => buildAudioSegmentUniqueKey(blockId, segment) === incomingKey,
  );
  if (duplicatedIndex >= 0) {
    const duplicatedSegment = segments[duplicatedIndex];
    const mergedDuplicatedSegment: AudioSegment = {
      ...duplicatedSegment,
      ...incoming,
      // Promote final-state segments to avoid waiting forever after playback.
      isFinal: Boolean(duplicatedSegment?.isFinal || incoming.isFinal),
      position: normalizeAudioPosition(
        incoming.position ?? duplicatedSegment?.position,
      ),
      subtitleCues: incoming.subtitleCues ?? duplicatedSegment?.subtitleCues,
      audioData: incoming.audioData || duplicatedSegment?.audioData || '',
      durationMs: incoming.durationMs ?? duplicatedSegment?.durationMs ?? 0,
    };
    const nextSegments = [...segments];
    nextSegments[duplicatedIndex] = mergedDuplicatedSegment;
    return sortAudioSegmentsByIndex(nextSegments);
  }
  return sortAudioSegmentsByIndex([...segments, incoming]);
};

export const buildAudioTracksFromSegmentData = (
  audios: AudioSegmentData[] = [],
): AudioTrack[] => {
  if (!audios.length) {
    return [];
  }

  const trackByPosition = new Map<number, AudioTrack>();

  [...audios]
    .sort(
      (a, b) =>
        Number(a.position ?? 0) - Number(b.position ?? 0) ||
        Number(a.segment_index ?? 0) - Number(b.segment_index ?? 0),
    )
    .forEach(audio => {
      const mappedSegment = toAudioSegment(audio);
      const position = normalizeAudioPosition(mappedSegment.position);
      const track = trackByPosition.get(position) ?? {
        position,
        audioSegments: [],
        isAudioStreaming: false,
      };

      track.audioSegments = [...(track.audioSegments ?? []), mappedSegment];
      track.isAudioStreaming = Boolean(
        track.audioSegments?.some(segment => !segment.isFinal),
      );
      track.subtitleCues =
        resolveLatestSegmentSubtitleCues(track.audioSegments) ??
        track.subtitleCues;

      trackByPosition.set(position, track);
    });

  return sortAudioTracksByPosition(Array.from(trackByPosition.values()));
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
  const nextSubtitleCues =
    resolveLatestSegmentSubtitleCues(nextSegments) ??
    existingTrack?.subtitleCues;
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
  nextTrack.subtitleCues = nextSubtitleCues;
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
  subtitleCues?: SubtitleCueData[];
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
    subtitleCues: normalizeSubtitleCues(complete.subtitle_cues),
  };
};

const upsertAudioTrackComplete = (
  tracks: AudioTrack[],
  complete: Partial<AudioCompleteData>,
): AudioTrack[] => {
  const { position, slideId, avContract, subtitleCues } =
    normalizeTrackForUpsert(complete);
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
  if (subtitleCues) {
    nextTrack.subtitleCues = subtitleCues;
  }
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
  elementBid: string,
  segment: AudioSegmentData,
  ensureItem?: EnsureItem<T>,
): T[] => {
  const nextItems = ensureItem ? ensureItem(items, elementBid) : items;
  const mappedSegment = toAudioSegment(segment);

  return nextItems.map(item => {
    if (item.element_bid !== elementBid) {
      return item;
    }

    const existingTracks = item.audioTracks ?? [];
    const updatedTracks = upsertAudioTrackSegment(
      elementBid,
      existingTracks,
      mappedSegment,
    );
    const hasStreamingTrack = updatedTracks.some(
      track => track.isAudioStreaming,
    );

    const hasNoChanges = updatedTracks === existingTracks;
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
  elementBid: string,
  complete: Partial<AudioCompleteData>,
  ensureItem?: EnsureItem<T>,
): T[] => {
  const nextItems = ensureItem ? ensureItem(items, elementBid) : items;

  return nextItems.map(item => {
    if (item.element_bid !== elementBid) {
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

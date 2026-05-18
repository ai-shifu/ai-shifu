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
  position?: number;
  streamElementNumber?: number;
  streamElementType?: string;
  elementId?: string;
  slideId?: string;
  avContract?: Record<string, unknown> | null;
  subtitleCues?: SubtitleCueData[];
}

export interface AudioTrack {
  position: number;
  slideId?: string;
  audioUrl?: string;
  durationMs?: number;
  isAudioStreaming?: boolean;
  audioSegments?: AudioSegment[];
  avContract?: Record<string, unknown> | null;
  subtitleCues?: SubtitleCueData[];
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
  stream_element_number?: number;
  streamElementNumber?: number;
  stream_element_type?: string;
  streamElementType?: string;
  element_id?: string;
  elementId?: string;
  slide_id?: string;
  slideId?: string;
  av_contract?: Record<string, unknown> | null;
  avContract?: Record<string, unknown> | null;
  subtitle_cues?: unknown;
  subtitleCues?: unknown;
}

const parseAudioPayloadObject = (
  payload: unknown,
): Record<string, unknown> | null => {
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    return payload as Record<string, unknown>;
  }

  if (typeof payload !== 'string') {
    return null;
  }

  const normalized = payload.trim();
  if (!normalized || !normalized.startsWith('{')) {
    return null;
  }

  try {
    const parsed = JSON.parse(normalized);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch (error) {
    console.warn('Failed to parse audio payload object:', error);
  }

  return null;
};

const readAudioPayloadField = (
  payload: Record<string, unknown>,
  keys: string[],
) => {
  for (const key of keys) {
    if (key in payload) {
      return payload[key];
    }
  }
  return undefined;
};

const normalizeAudioPayloadNumber = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim()) {
    const parsedValue = Number(value);
    if (Number.isFinite(parsedValue)) {
      return parsedValue;
    }
  }

  return undefined;
};

const normalizeAudioPayloadBoolean = (value: unknown) => {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    const normalized = value.toLowerCase();
    if (normalized === 'true') {
      return true;
    }
    if (normalized === 'false') {
      return false;
    }
  }
  return undefined;
};

const normalizeAudioPayloadString = (value: unknown) =>
  typeof value === 'string' ? value : undefined;

const normalizeAudioPayloadObject = (value: unknown) =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;

const normalizeAudioSubtitleCueNumber = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim()) {
    const parsedValue = Number(value);
    if (Number.isFinite(parsedValue)) {
      return parsedValue;
    }
  }

  return undefined;
};

export const normalizeAudioSubtitleCues = (
  rawSubtitleCues: unknown,
): SubtitleCueData[] | undefined => {
  if (!Array.isArray(rawSubtitleCues)) {
    return undefined;
  }

  const subtitleCues = rawSubtitleCues.reduce<SubtitleCueData[]>(
    (result, rawCue) => {
      if (!rawCue || typeof rawCue !== 'object') {
        return result;
      }

      const cue = rawCue as Record<string, unknown>;
      const text = typeof cue.text === 'string' ? cue.text : '';
      const startMs = normalizeAudioSubtitleCueNumber(cue.start_ms);
      const endMs = normalizeAudioSubtitleCueNumber(cue.end_ms);

      if (!text || startMs === undefined || endMs === undefined) {
        return result;
      }

      const segmentIndex = normalizeAudioSubtitleCueNumber(cue.segment_index);
      const position = normalizeAudioSubtitleCueNumber(cue.position);

      result.push({
        text,
        start_ms: startMs,
        end_ms: endMs,
        ...(segmentIndex === undefined ? {} : { segment_index: segmentIndex }),
        ...(position === undefined ? {} : { position }),
      });

      return result;
    },
    [],
  );

  return subtitleCues.length > 0 ? subtitleCues : undefined;
};

export const normalizeAudioSegmentPayload = (
  payload: unknown,
): AudioSegment | null => {
  const source = parseAudioPayloadObject(payload);
  if (!source) {
    return null;
  }

  const segmentIndex = normalizeAudioPayloadNumber(
    readAudioPayloadField(source, ['segment_index', 'segmentIndex']),
  );
  const audioData = normalizeAudioPayloadString(
    readAudioPayloadField(source, ['audio_data', 'audioData']),
  );

  if (segmentIndex === undefined || !audioData) {
    return null;
  }

  return {
    segmentIndex,
    audioData,
    durationMs:
      normalizeAudioPayloadNumber(
        readAudioPayloadField(source, ['duration_ms', 'durationMs']),
      ) ?? 0,
    isFinal:
      normalizeAudioPayloadBoolean(
        readAudioPayloadField(source, ['is_final', 'isFinal']),
      ) ?? false,
    position: normalizeAudioPayloadNumber(source.position),
    streamElementNumber: normalizeAudioPayloadNumber(
      readAudioPayloadField(source, [
        'stream_element_number',
        'streamElementNumber',
      ]),
    ),
    streamElementType: normalizeAudioPayloadString(
      readAudioPayloadField(source, [
        'stream_element_type',
        'streamElementType',
      ]),
    ),
    elementId: normalizeAudioPayloadString(
      readAudioPayloadField(source, ['element_id', 'elementId']),
    ),
    slideId: normalizeAudioPayloadString(
      readAudioPayloadField(source, ['slide_id', 'slideId']),
    ),
    avContract:
      normalizeAudioPayloadObject(
        readAudioPayloadField(source, ['av_contract', 'avContract']),
      ) ?? null,
    subtitleCues: normalizeAudioSubtitleCues(
      readAudioPayloadField(source, ['subtitle_cues', 'subtitleCues']),
    ),
  };
};

export const normalizeAudioCompletePayload = (
  payload: unknown,
): AudioCompleteData | null => {
  const source = parseAudioPayloadObject(payload);
  if (!source) {
    return null;
  }

  const audioUrl =
    normalizeAudioPayloadString(
      readAudioPayloadField(source, ['audio_url', 'audioUrl']),
    )?.trim() || '';

  if (!audioUrl) {
    return null;
  }

  const audioBid =
    normalizeAudioPayloadString(
      readAudioPayloadField(source, ['audio_bid', 'audioBid']),
    ) || '';
  const durationMs =
    normalizeAudioPayloadNumber(
      readAudioPayloadField(source, ['duration_ms', 'durationMs']),
    ) ?? 0;
  const position = normalizeAudioPayloadNumber(source.position);
  const streamElementNumber = normalizeAudioPayloadNumber(
    readAudioPayloadField(source, [
      'stream_element_number',
      'streamElementNumber',
    ]),
  );
  const streamElementType = normalizeAudioPayloadString(
    readAudioPayloadField(source, ['stream_element_type', 'streamElementType']),
  );
  const slideId = normalizeAudioPayloadString(
    readAudioPayloadField(source, ['slide_id', 'slideId']),
  );
  const avContract = normalizeAudioPayloadObject(
    readAudioPayloadField(source, ['av_contract', 'avContract']),
  );
  const subtitleCues = normalizeAudioSubtitleCues(
    readAudioPayloadField(source, ['subtitle_cues', 'subtitleCues']),
  );

  return {
    audio_url: audioUrl,
    audio_bid: audioBid,
    duration_ms: durationMs,
    ...(position === undefined ? {} : { position }),
    ...(streamElementNumber === undefined
      ? {}
      : { stream_element_number: streamElementNumber }),
    ...(streamElementType ? { stream_element_type: streamElementType } : {}),
    ...(slideId ? { slide_id: slideId } : {}),
    ...(avContract === undefined ? {} : { av_contract: avContract }),
    ...(subtitleCues ? { subtitle_cues: subtitleCues } : {}),
  };
};

const toAudioSegment = (segment: AudioSegmentData): AudioSegment => ({
  segmentIndex: segment.segment_index,
  audioData: segment.audio_data,
  durationMs: segment.duration_ms,
  isFinal: segment.is_final,
  position: normalizeAudioPosition(segment.position),
  streamElementNumber: segment.stream_element_number,
  streamElementType: segment.stream_element_type,
  elementId: segment.element_id,
  slideId: segment.slide_id,
  avContract: segment.av_contract ?? null,
  subtitleCues: normalizeAudioSubtitleCues(segment.subtitle_cues),
});

export const toAudioSegmentData = (
  segment: AudioSegment,
): AudioSegmentData => ({
  segment_index: segment.segmentIndex,
  audio_data: segment.audioData,
  duration_ms: segment.durationMs,
  is_final: segment.isFinal,
  position: normalizeAudioPosition(segment.position),
  stream_element_number: segment.streamElementNumber,
  stream_element_type: segment.streamElementType,
  element_id: segment.elementId,
  slide_id: segment.slideId,
  av_contract: segment.avContract ?? null,
  subtitle_cues: segment.subtitleCues,
});

export const getAudioSegmentDataListFromTracks = (
  tracks: AudioTrack[] = [],
): AudioSegmentData[] =>
  sortAudioTracksByPosition(tracks).flatMap(track =>
    sortAudioSegmentsByIndex(track.audioSegments ?? []).map(toAudioSegmentData),
  );

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
      audioData: incoming.audioData || duplicatedSegment?.audioData || '',
      durationMs: incoming.durationMs ?? duplicatedSegment?.durationMs ?? 0,
      subtitleCues: incoming.subtitleCues ?? duplicatedSegment?.subtitleCues,
    };
    const nextSegments = [...segments];
    nextSegments[duplicatedIndex] = mergedDuplicatedSegment;
    return sortAudioSegmentsByIndex(nextSegments);
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
  const incomingSubtitleCues = incoming.subtitleCues;

  const hasNoChanges =
    existingTrack &&
    nextSegments === existingSegments &&
    existingTrack.isAudioStreaming === nextStreaming &&
    (!incoming.slideId || existingTrack.slideId === incoming.slideId) &&
    (!incoming.avContract ||
      existingTrack.avContract === incoming.avContract) &&
    (!incomingSubtitleCues ||
      existingTrack.subtitleCues === incomingSubtitleCues);
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
  if (incomingSubtitleCues) {
    nextTrack.subtitleCues = incomingSubtitleCues;
  }

  if (targetIndex >= 0) {
    const nextTracks = [...tracks];
    nextTracks[targetIndex] = nextTrack;
    return sortAudioTracksByPosition(nextTracks);
  }
  return sortAudioTracksByPosition([...tracks, nextTrack]);
};

const markLastAudioSegmentFinal = (
  segments: AudioSegment[] = [],
): AudioSegment[] => {
  if (!segments.length) {
    return segments;
  }

  const sortedSegments = sortAudioSegmentsByIndex(segments);
  const lastSegmentIndex = sortedSegments.length - 1;
  const lastSegment = sortedSegments[lastSegmentIndex];
  const isSameOrder = sortedSegments.every(
    (segment, index) => segment === segments[index],
  );

  if (lastSegment?.isFinal) {
    return isSameOrder ? segments : sortedSegments;
  }

  const nextSegments = [...sortedSegments];
  nextSegments[lastSegmentIndex] = {
    ...lastSegment,
    isFinal: true,
  };
  return nextSegments;
};

const normalizeTrackForUpsert = (
  complete: Partial<AudioCompleteData>,
): {
  position: number;
  slideId?: string;
  avContract?: Record<string, unknown> | null;
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
    subtitleCues: normalizeAudioSubtitleCues(complete.subtitle_cues),
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
  const finalizedAudioSegments = existingTrack?.audioSegments?.length
    ? markLastAudioSegmentFinal(existingTrack.audioSegments)
    : existingTrack?.audioSegments;
  const hasNoChanges =
    existingTrack &&
    existingTrack.audioUrl === (complete.audio_url ?? existingTrack.audioUrl) &&
    existingTrack.durationMs ===
      (complete.duration_ms ?? existingTrack.durationMs) &&
    existingTrack.isAudioStreaming === false &&
    existingTrack.audioSegments === finalizedAudioSegments &&
    (!slideId || existingTrack.slideId === slideId) &&
    (!avContract || existingTrack.avContract === avContract) &&
    (!subtitleCues || existingTrack.subtitleCues === subtitleCues);
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
  if (finalizedAudioSegments) {
    nextTrack.audioSegments = finalizedAudioSegments;
  }
  if (slideId) {
    nextTrack.slideId = slideId;
  }
  if (avContract) {
    nextTrack.avContract = avContract;
  }
  if (subtitleCues) {
    nextTrack.subtitleCues = subtitleCues;
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

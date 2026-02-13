export const LISTEN_AUDIO_EVENT_TYPES = {
  AUDIO_SEGMENT: 'audio_segment',
  AUDIO_COMPLETE: 'audio_complete',
} as const;

export type ListenAudioEventType =
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
  slideId,
  fallbackIndex,
  resolveContentBid,
}: {
  type: string;
  generatedBlockBid?: string | null;
  position?: unknown;
  slideId?: string | null;
  fallbackIndex: number;
  resolveContentBid?: (blockBid: string | null) => string | null;
}): string => {
  if (type === 'content') {
    if (slideId) {
      return `content-slide:${slideId}`;
    }
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

export type ListenInboundAudioEvent = {
  type: ListenAudioEventType;
  generatedBlockBid: string;
  position: number;
  slideId?: string;
  payload: Record<string, unknown>;
};

export type ListenRecordAudioLike = {
  position?: number;
  slide_id?: string;
  audio_url?: string;
  audio_bid?: string;
  duration_ms?: number;
  [key: string]: unknown;
};

export type NormalizedListenRecordAudio = {
  position: number;
  slide_id?: string;
  audio_url?: string;
  audio_bid?: string;
  duration_ms?: number;
};

export type NormalizedListenRecordAudios = {
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
  response: any,
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
  audios?: ListenRecordAudioLike[] | null;
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
      audio_url: audioUrl,
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

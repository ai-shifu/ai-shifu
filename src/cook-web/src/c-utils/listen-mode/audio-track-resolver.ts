type PersistedAudioTrack = {
  position?: number;
  audio_url?: string;
  duration_ms?: number;
};

type StreamingAudioTrack = {
  audioUrl?: string;
  audioSegments?: Array<any>;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
};

export type ListenAudioTrackSource = {
  audioUrl?: string;
  audioSegments?: Array<any>;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
  audios?: Array<PersistedAudioTrack>;
  audioTracksByPosition?: Record<number, StreamingAudioTrack>;
  avContract?: {
    speakable_segments?: Array<any>;
  } | null;
};

export type ResolvedListenAudioTrack = {
  audioUrl?: string;
  audioSegments?: Array<any>;
  isAudioStreaming: boolean;
  audioDurationMs?: number;
};

export const hasAnyAudioPayload = (item: ListenAudioTrackSource): boolean => {
  const hasAnySegmentedAudio = Boolean(
    (item.audios && item.audios.length > 0) ||
    (item.audioTracksByPosition &&
      Object.keys(item.audioTracksByPosition).length > 0),
  );
  const hasContractAudioPositions = Boolean(
    item.avContract?.speakable_segments &&
    item.avContract.speakable_segments.length > 0,
  );
  return Boolean(
    item.audioUrl ||
    (item.audioSegments && item.audioSegments.length > 0) ||
    item.isAudioStreaming ||
    hasAnySegmentedAudio ||
    hasContractAudioPositions,
  );
};

export const resolveListenAudioTrack = (
  item: ListenAudioTrackSource,
  position: number,
): ResolvedListenAudioTrack => {
  const track = item.audioTracksByPosition?.[position];
  const persisted = (item.audios || [])
    .filter(audio => Number(audio.position ?? 0) === position)
    .pop();
  const legacyForZero = position === 0;

  return {
    audioUrl:
      track?.audioUrl ||
      persisted?.audio_url ||
      (legacyForZero ? item.audioUrl : undefined),
    audioSegments:
      track?.audioSegments ?? (legacyForZero ? item.audioSegments : undefined),
    isAudioStreaming: Boolean(
      track?.isAudioStreaming || (legacyForZero && item.isAudioStreaming),
    ),
    audioDurationMs:
      track?.audioDurationMs ??
      persisted?.duration_ms ??
      (legacyForZero ? item.audioDurationMs : undefined),
  };
};

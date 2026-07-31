import {
  type AudioCompleteData,
  type AudioSegmentData,
  ELEMENT_TYPE,
  type ListenSlideData,
  type StudyRecordItem,
} from '@/c-api/studyV2';
import {
  getAudioSegmentDataListFromTracks,
  mergeAudioSegmentDataList,
  normalizeAudioSubtitleCues,
  sortAudioTracksByPosition,
  type AudioTrack,
} from '@/c-utils/audio-utils';
import { type ChatContentItem, ChatContentItemType } from '@/c-types/chatUi';
import {
  normalizeLegacyBlockCompatList,
  stripCustomButtonAfterContent,
} from './chatUiUtils';

const DEFAULT_LISTEN_AUDIO_POSITION = 0;

export const normalizeOptionalNumber = (value: unknown) => {
  if (value === undefined || value === null) {
    return undefined;
  }

  const normalized = Number(value);
  return Number.isFinite(normalized) ? normalized : undefined;
};

export const resolveStudyRecordAudioComplete = (
  record: StudyRecordItem,
): Partial<AudioCompleteData> | null => {
  const audioPayload = record.payload?.audio as
    | Record<string, unknown>
    | undefined;
  const audioUrl =
    (typeof record.audio_url === 'string' && record.audio_url.trim()) ||
    (typeof audioPayload?.audio_url === 'string' &&
      audioPayload.audio_url.trim()) ||
    '';

  if (!audioUrl) {
    return null;
  }

  const audioBid =
    typeof audioPayload?.audio_bid === 'string'
      ? audioPayload.audio_bid
      : undefined;
  const durationMs = normalizeOptionalNumber(audioPayload?.duration_ms);
  const position = normalizeOptionalNumber(audioPayload?.position);
  const slideId =
    typeof audioPayload?.slide_id === 'string'
      ? audioPayload.slide_id
      : undefined;
  const avContract =
    audioPayload?.av_contract &&
    typeof audioPayload.av_contract === 'object' &&
    !Array.isArray(audioPayload.av_contract)
      ? (audioPayload.av_contract as Record<string, unknown>)
      : undefined;
  const subtitleCues = normalizeAudioSubtitleCues(audioPayload?.subtitle_cues);

  return {
    audio_url: audioUrl,
    ...(audioBid ? { audio_bid: audioBid } : {}),
    ...(durationMs === undefined ? {} : { duration_ms: durationMs }),
    ...(position === undefined ? {} : { position }),
    ...(slideId ? { slide_id: slideId } : {}),
    ...(avContract ? { av_contract: avContract } : {}),
    ...(subtitleCues ? { subtitle_cues: subtitleCues } : {}),
  };
};

export const hydrateAudioTracksWithCompleteUrl = (
  tracks: AudioTrack[] = [],
  audioComplete?: Partial<AudioCompleteData> | null,
): AudioTrack[] => {
  if (!audioComplete?.audio_url) {
    return tracks;
  }

  const position =
    normalizeOptionalNumber(audioComplete.position) ??
    DEFAULT_LISTEN_AUDIO_POSITION;
  const targetIndex = tracks.findIndex(track => track.position === position);
  const targetTrack =
    targetIndex >= 0
      ? { ...tracks[targetIndex] }
      : {
          position,
          audioSegments: [],
          isAudioStreaming: false,
        };

  const nextTrack: AudioTrack = {
    ...targetTrack,
    audioUrl: audioComplete.audio_url,
    durationMs: audioComplete.duration_ms ?? targetTrack.durationMs,
    isAudioStreaming: false,
    slideId: audioComplete.slide_id ?? targetTrack.slideId,
    avContract: audioComplete.av_contract ?? targetTrack.avContract,
    subtitleCues: audioComplete.subtitle_cues ?? targetTrack.subtitleCues,
  };
  const nextTracks =
    targetIndex >= 0
      ? tracks.map((track, index) =>
          index === targetIndex ? nextTrack : track,
        )
      : [...tracks, nextTrack];

  return sortAudioTracksByPosition(nextTracks);
};

const normalizeCanonicalChatContentItem = (
  item: ChatContentItem,
): ChatContentItem => {
  const nextContent =
    typeof item.content === 'string'
      ? (stripCustomButtonAfterContent(item.content) ?? '')
      : item.content;
  const nextAskList = Array.isArray(item.ask_list)
    ? item.ask_list.map(normalizeCanonicalChatContentItem)
    : item.ask_list;
  const hasContentChanged = nextContent !== item.content;
  const hasAskListChanged = nextAskList !== item.ask_list;

  if (!hasContentChanged && !hasAskListChanged) {
    return item;
  }

  return {
    ...item,
    ...(hasContentChanged ? { content: nextContent } : {}),
    ...(hasAskListChanged ? { ask_list: nextAskList } : {}),
  };
};

export const normalizeCanonicalChatContentList = (
  items: ChatContentItem[],
): ChatContentItem[] =>
  normalizeLegacyBlockCompatList(items).map(normalizeCanonicalChatContentItem);

const resolvePayloadVisualContent = (
  payload?: StudyRecordItem['payload'] | null,
) => {
  const previousVisuals = payload?.previous_visuals;
  if (!Array.isArray(previousVisuals)) {
    return '';
  }

  return previousVisuals
    .map(item => {
      if (!item || typeof item !== 'object') {
        return '';
      }
      const content = (item as { content?: unknown }).content;
      return typeof content === 'string' ? content.trim() : '';
    })
    .filter(Boolean)
    .join('\n\n');
};

export const resolveRenderableRecordContent = (record: StudyRecordItem) => {
  const content = record.content ?? '';
  if (content.trim()) {
    return content;
  }
  return resolvePayloadVisualContent(record.payload) || content;
};

export const normalizeHistoryAudioTracks = (
  audios: AudioSegmentData[] = [],
  audioComplete?: Partial<AudioCompleteData> | null,
): AudioTrack[] => {
  if (!audios.length) {
    return hydrateAudioTracksWithCompleteUrl([], audioComplete);
  }

  const trackByPosition = new Map<number, AudioTrack>();

  [...audios]
    .sort(
      (a, b) =>
        Number(a.position ?? 0) - Number(b.position ?? 0) ||
        Number(a.segment_index ?? 0) - Number(b.segment_index ?? 0),
    )
    .forEach(audio => {
      const position = Number(audio.position ?? 0);
      const track = trackByPosition.get(position) ?? {
        position,
        audioSegments: [],
        isAudioStreaming: false,
      };

      track.audioSegments = [
        ...(track.audioSegments ?? []),
        {
          segmentIndex: Number(audio.segment_index ?? 0),
          audioData: audio.audio_data,
          durationMs: Number(audio.duration_ms ?? 0),
          isFinal: Boolean(audio.is_final),
          position,
          elementId: audio.element_id,
          slideId: audio.slide_id,
          avContract: audio.av_contract ?? null,
          subtitleCues: audio.subtitle_cues,
        },
      ];
      track.isAudioStreaming = Boolean(
        track.audioSegments?.some(segment => !segment.isFinal),
      );

      trackByPosition.set(position, track);
    });

  return hydrateAudioTracksWithCompleteUrl(
    [...trackByPosition.values()],
    audioComplete,
  );
};

export const resolveRecordUserInput = (
  record?: Pick<StudyRecordItem, 'user_input' | 'payload'> | null,
) => {
  if (!record) {
    return undefined;
  }

  const payloadUserInput =
    typeof record.payload?.user_input === 'string'
      ? record.payload.user_input
      : undefined;

  return record.user_input ?? payloadUserInput;
};

export const resolveRecordElementType = (
  record?: Pick<StudyRecordItem, 'element_type'> | null,
) => {
  const rawElementType = (record as { element_type?: unknown } | null)
    ?.element_type;
  return typeof rawElementType === 'string' ? rawElementType : '';
};

export const isAskOrAnswerElementType = (elementType?: string | null) => {
  return elementType === 'ask' || elementType === 'answer';
};

export const buildElementContentItem = (
  record: StudyRecordItem,
  options: {
    getPendingListenSlides: (identityBids: string[]) => ListenSlideData[];
    isAudioBackfillReadyForBlock: (
      generatedBlockBid?: string | null,
      elementBid?: string | null,
    ) => boolean;
    mergeListenSlides: (
      ...slideLists: Array<ListenSlideData[] | undefined>
    ) => ListenSlideData[];
    previousItem?: ChatContentItem;
    resolveElementItemBid: (
      record?: Pick<
        StudyRecordItem,
        'element_bid' | 'generated_block_bid' | 'target_element_bid'
      > | null,
    ) => string;
    resolveListenSlideIdentityBids: (
      ...sources: Array<
        Partial<StudyRecordItem & ListenSlideData> | string | null | undefined
      >
    ) => string[];
    isHistory?: boolean;
    shouldRenderAsHistoryInReadMode?: boolean;
    shouldUseTypewriter?: boolean;
    listenSlides?: ListenSlideData[];
  },
): ChatContentItem => {
  const itemBid = options.resolveElementItemBid(record);
  const previousAudioSegments = Array.isArray(
    options.previousItem?.audio_segments,
  )
    ? options.previousItem?.audio_segments
    : [];
  const previousTrackAudioSegments = getAudioSegmentDataListFromTracks(
    options.previousItem?.audioTracks ?? [],
  );
  const incomingAudioSegments = Array.isArray(record.audio_segments)
    ? record.audio_segments
    : [];
  const mergedAudioSegments = mergeAudioSegmentDataList(itemBid, [
    ...previousAudioSegments,
    ...previousTrackAudioSegments,
    ...incomingAudioSegments,
  ]);
  const historyTracks = normalizeHistoryAudioTracks(
    mergedAudioSegments,
    resolveStudyRecordAudioComplete(record),
  );
  const singleTrack = historyTracks.length === 1 ? historyTracks[0] : null;
  const isInteractionElement = record.element_type === ELEMENT_TYPE.INTERACTION;
  const generatedBlockBid = record.generated_block_bid || itemBid;
  const identityBids = options.resolveListenSlideIdentityBids(
    record,
    itemBid,
    generatedBlockBid,
  );
  const pendingListenSlides = options.getPendingListenSlides(identityBids);
  const content = resolveRenderableRecordContent(record);

  return {
    ...options.previousItem,
    ...record,
    element_bid: itemBid,
    generated_block_bid: generatedBlockBid,
    content,
    customRenderBar: () => null,
    user_input:
      resolveRecordUserInput(record) ?? options.previousItem?.user_input ?? '',
    readonly: options.previousItem?.readonly ?? false,
    isHistory: options.isHistory,
    shouldRenderAsHistoryInReadMode:
      options.shouldRenderAsHistoryInReadMode ??
      (options.previousItem?.isHistory
        ? false
        : (options.previousItem?.shouldRenderAsHistoryInReadMode ?? false)),
    is_final:
      options.previousItem?.is_final === true ? true : Boolean(record.is_final),
    shouldUseTypewriter:
      options.shouldUseTypewriter ??
      options.previousItem?.shouldUseTypewriter ??
      false,
    isAudioBackfillReady:
      options.isHistory ||
      options.previousItem?.isHistory ||
      options.previousItem?.isAudioBackfillReady ||
      options.isAudioBackfillReadyForBlock(generatedBlockBid, itemBid),
    type: isInteractionElement
      ? ChatContentItemType.INTERACTION
      : ChatContentItemType.CONTENT,
    audioUrl:
      singleTrack?.audioUrl ??
      record.audio_url ??
      options.previousItem?.audioUrl,
    audioDurationMs:
      singleTrack?.durationMs ?? options.previousItem?.audioDurationMs,
    audioTracks:
      historyTracks.length > 0
        ? historyTracks
        : options.previousItem?.audioTracks,
    audio_segments:
      mergedAudioSegments.length > 0
        ? mergedAudioSegments
        : options.previousItem?.audio_segments,
    listenSlides: options.mergeListenSlides(
      options.previousItem?.listenSlides,
      options.listenSlides,
      pendingListenSlides,
    ),
  };
};

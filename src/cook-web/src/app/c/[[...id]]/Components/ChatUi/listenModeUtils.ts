import type { ChatContentItem } from './useChatLogicHook';
import type {
  StudyRecordAudioPayload,
  StudyRecordPayload,
} from '@/c-api/studyV2';
import { stripDisallowedSubtitleTrailingPunctuation } from '@/c-utils/subtitleUtils';
import type { ElementSubtitleCue } from 'markdown-flow-ui/slide';
import {
  getAudioSegmentDataListFromTracks,
  hasAudioContentInTrack,
  hasAudioContentInTracks,
  mergeAudioSegmentDataList,
  type AudioSegment,
  type AudioTrack,
} from '@/c-utils/audio-utils';

const MARKDOWN_VIDEO_IFRAME_PATTERN =
  /<iframe\b[^>]*\bdata-tag\s*=\s*(["'])video\1[^>]*>[\s\S]*?<\/iframe>/i;
const MIN_LISTEN_MODE_TTS_TEXT_LENGTH = 2;
const CUSTOM_BUTTON_RE =
  /<custom-button-after-content\b[\s\S]*?<\/custom-button-after-content>/gi;
const HTML_COMMENT_RE = /<!--[\s\S]*?-->/g;
const HTML_TAG_RE = /<\/?\s*[a-zA-Z][a-zA-Z0-9:_-]*\b[^>]*>/g;
const HTML_SPACE_ENTITY_RE = /&(?:nbsp|ensp|emsp|thinsp|zwnj|zwj);/gi;
const SPEAKABLE_TEXT_RE = /[\p{L}\p{N}]/u;

const normalizeListenModeSpeakableText = (content?: string) =>
  String(content ?? '')
    .replace(CUSTOM_BUTTON_RE, ' ')
    .replace(HTML_COMMENT_RE, ' ')
    .replace(HTML_TAG_RE, ' ')
    .replace(HTML_SPACE_ENTITY_RE, ' ')
    .trim();

const hasListenModeSpeakableText = (content?: string) => {
  const text = normalizeListenModeSpeakableText(content);
  return (
    text.length >= MIN_LISTEN_MODE_TTS_TEXT_LENGTH &&
    SPEAKABLE_TEXT_RE.test(text)
  );
};

export const sortByPosition = <T extends { position?: number }>(
  list: T[] = [],
) =>
  [...list].sort((a, b) => Number(a.position ?? 0) - Number(b.position ?? 0));

export const sortSegmentsByIndex = (segments: AudioSegment[] = []) =>
  [...segments].sort(
    (a, b) => Number(a.segmentIndex ?? 0) - Number(b.segmentIndex ?? 0),
  );

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

const sortSubtitleCues = (cues: ElementSubtitleCue[]) =>
  [...cues].sort(
    (prevCue, nextCue) =>
      Number(prevCue.position ?? 0) - Number(nextCue.position ?? 0) ||
      Number(prevCue.start_ms ?? 0) - Number(nextCue.start_ms ?? 0) ||
      Number(prevCue.end_ms ?? 0) - Number(nextCue.end_ms ?? 0) ||
      Number(prevCue.segment_index ?? 0) - Number(nextCue.segment_index ?? 0),
  );

interface ListenSlideSubtitleCueSource {
  payload?: StudyRecordPayload;
  audioTracks?: AudioTrack[];
}

const normalizeRawSubtitleCues = (
  rawSubtitleCues: unknown,
): ElementSubtitleCue[] | undefined => {
  if (!Array.isArray(rawSubtitleCues)) {
    return undefined;
  }

  const normalizedSubtitleCues = rawSubtitleCues.reduce<ElementSubtitleCue[]>(
    (result, cue) => {
      if (!cue || typeof cue !== 'object') {
        return result;
      }

      const rawCue = cue as Record<string, unknown>;
      const text =
        typeof rawCue.text === 'string'
          ? stripDisallowedSubtitleTrailingPunctuation(rawCue.text)
          : undefined;
      const startMs = normalizeSubtitleCueNumber(rawCue.start_ms);
      const endMs = normalizeSubtitleCueNumber(rawCue.end_ms);

      if (!text || startMs === null || endMs === null) {
        return result;
      }

      const segmentIndex = normalizeSubtitleCueNumber(rawCue.segment_index);
      const position = normalizeSubtitleCueNumber(rawCue.position);

      result.push({
        text,
        start_ms: startMs,
        end_ms: endMs,
        // Always emit the slide contract shape after normalization.
        segment_index: segmentIndex ?? 0,
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

const resolveAudioTrackSubtitleCues = (
  tracks: AudioTrack[] = [],
): unknown[] => {
  return sortByPosition(tracks).flatMap(track => {
    if (track.subtitleCues?.length) {
      return track.subtitleCues.map(cue => ({
        ...cue,
        position: cue.position ?? track.position,
      }));
    }

    return sortSegmentsByIndex(track.audioSegments ?? []).flatMap(segment =>
      (segment.subtitleCues ?? []).map(cue => ({
        ...cue,
        position: cue.position ?? segment.position ?? track.position,
      })),
    );
  });
};

export const resolveListenSlideSubtitleCues = (
  item: ListenSlideSubtitleCueSource,
): ElementSubtitleCue[] | undefined => {
  const audioPayload = item.payload?.audio as
    | StudyRecordAudioPayload
    | undefined;
  const payloadSubtitleCues = normalizeRawSubtitleCues(
    audioPayload?.subtitle_cues,
  );

  if (payloadSubtitleCues?.length) {
    return payloadSubtitleCues;
  }

  const trackSubtitleCues = resolveAudioTrackSubtitleCues(
    item.audioTracks ?? [],
  );
  return trackSubtitleCues.length > 0
    ? normalizeRawSubtitleCues(trackSubtitleCues)
    : undefined;
};

export const normalizeAudioTracks = (item: ChatContentItem): AudioTrack[] => {
  const trackByPosition = new Map<number, AudioTrack>();

  (item.audioTracks ?? []).forEach(track => {
    const position = Number(track.position ?? 0);
    const trackSubtitleCues = track.subtitleCues?.length
      ? track.subtitleCues
      : sortSegmentsByIndex(track.audioSegments ?? []).flatMap(
          segment => segment.subtitleCues ?? [],
        );
    trackByPosition.set(position, {
      ...track,
      position,
      audioSegments: sortSegmentsByIndex(track.audioSegments ?? []),
      subtitleCues:
        trackSubtitleCues.length > 0 ? trackSubtitleCues : undefined,
    });
  });

  return sortByPosition(Array.from(trackByPosition.values()));
};

interface ListenSlideAudioSource {
  audioUrl?: string;
  audioSegments?: ChatContentItem['audio_segments'];
  isAudioStreaming?: boolean;
}

const hasFinalizedAudioSegments = (track: AudioTrack) => {
  const segments = sortSegmentsByIndex(track.audioSegments ?? []);
  return segments.length > 0 && Boolean(segments[segments.length - 1]?.isFinal);
};

export const resolveListenSlideAudioSource = (
  item: ChatContentItem,
): ListenSlideAudioSource => {
  const normalizedTracks = normalizeAudioTracks(item);
  const playableTracks = normalizedTracks.filter(track =>
    hasAudioContentInTrack(track),
  );

  // Keep one canonical source in slide playback to avoid duplicated playback.
  if (playableTracks.length > 0) {
    const completedTrack = playableTracks.find(track =>
      Boolean(track.audioUrl?.trim()),
    );
    if (completedTrack?.audioUrl) {
      const completedTrackAudioSegments = mergeAudioSegmentDataList(
        item.element_bid,
        getAudioSegmentDataListFromTracks([completedTrack]),
      );

      // Preserve streamed segment history with the completed URL so the slide
      // player can continue from the played boundary instead of replaying from
      // the beginning when backfilled audio finalizes mid-session.
      return {
        audioUrl: completedTrack.audioUrl,
        audioSegments:
          completedTrackAudioSegments.length > 0
            ? completedTrackAudioSegments
            : undefined,
        isAudioStreaming:
          Boolean(completedTrack.isAudioStreaming) &&
          !hasFinalizedAudioSegments(completedTrack),
      };
    }

    const trackAudioSegments = mergeAudioSegmentDataList(
      item.element_bid,
      getAudioSegmentDataListFromTracks(playableTracks),
    );
    return {
      audioUrl: playableTracks.find(track => track.audioUrl)?.audioUrl,
      audioSegments:
        trackAudioSegments.length > 0 ? trackAudioSegments : undefined,
      isAudioStreaming: playableTracks.some(track =>
        Boolean(track.isAudioStreaming),
      ),
    };
  }

  const legacyAudioSegments = mergeAudioSegmentDataList(
    item.element_bid,
    item.audio_segments ?? [],
  );
  return {
    audioUrl: item.audio_url ?? item.audioUrl,
    audioSegments:
      legacyAudioSegments.length > 0 ? legacyAudioSegments : undefined,
    isAudioStreaming:
      typeof item.isAudioStreaming === 'boolean'
        ? item.isAudioStreaming
        : legacyAudioSegments.some(segment => !segment.is_final),
  };
};

export const resolveListenSlideElementType = (
  item: Pick<ChatContentItem, 'content' | 'element_type'>,
) => {
  const normalizedContent = item.content?.trim() ?? '';

  // Prefer the explicit video iframe signature so slide rendering can
  // route embedded videos through the dedicated `video` element type.
  if (MARKDOWN_VIDEO_IFRAME_PATTERN.test(normalizedContent)) {
    return 'video';
  }

  if (item.element_type) {
    return item.element_type;
  }

  return 'text';
};

export const canRequestListenModeTtsForItem = (
  item?: ChatContentItem | null,
) => {
  if (!item || item.type !== 'content') {
    return false;
  }

  return Boolean(
    (item.is_speakable === true && hasListenModeSpeakableText(item.content)) ||
    item.audio_url ||
    item.audioUrl ||
    item.isAudioStreaming ||
    item.audio_segments?.length ||
    hasAudioContentInTracks(item.audioTracks ?? []),
  );
};

export const hasPlayableListenAudioForItem = (item?: ChatContentItem | null) =>
  Boolean(
    item?.audio_url?.trim() ||
    item?.audioUrl?.trim() ||
    item?.isAudioStreaming ||
    (item?.audio_segments?.length ?? 0) > 0 ||
    hasAudioContentInTracks(item?.audioTracks ?? []),
  );

export const isListenModeAudioBackfillCandidate = (
  item?: ChatContentItem | null,
) => {
  if (!item || item.type !== 'content') {
    return false;
  }

  const elementBid = item.element_bid?.trim();
  if (!elementBid || elementBid === 'loading') {
    return false;
  }

  return (
    item.is_speakable !== false && hasListenModeSpeakableText(item.content)
  );
};

export const isListenModeAudioBackfillReady = (item?: ChatContentItem | null) =>
  Boolean(
    item?.isHistory ||
    item?.isAudioBackfillReady ||
    hasPlayableListenAudioForItem(item),
  );

export const getMissingListenModeAudioBlockBids = (
  items: ChatContentItem[],
) => {
  const seen = new Set<string>();
  const missingBids: string[] = [];

  items.forEach(item => {
    if (!isListenModeAudioBackfillCandidate(item)) {
      return;
    }

    if (hasPlayableListenAudioForItem(item)) {
      return;
    }

    const requestBid =
      item.generated_block_bid?.trim() || item.element_bid?.trim();
    if (!requestBid || seen.has(requestBid)) {
      return;
    }

    seen.add(requestBid);
    missingBids.push(requestBid);
  });

  return missingBids;
};

export const resolveListenModeTtsReadyElementBids = (
  items: ChatContentItem[],
) => {
  const speakableContentBids = new Set<string>();

  items.forEach(item => {
    if (!canRequestListenModeTtsForItem(item)) {
      return;
    }

    const bid = item.element_bid;
    if (!bid || bid === 'loading') {
      return;
    }

    speakableContentBids.add(bid);
  });

  const ready = new Set<string>();

  items.forEach(item => {
    if (item.type !== 'likeStatus') {
      return;
    }

    const parentBid = item.parent_element_bid;
    if (!parentBid || !speakableContentBids.has(parentBid)) {
      return;
    }

    ready.add(parentBid);
  });

  return ready;
};

export interface ListenSlidePageMapping {
  blockSlides: NonNullable<ChatContentItem['listenSlides']>;
  pageBySlideId: Map<string, number>;
  resolvePageByPosition: (position: number) => number;
}

export const buildSlidePageMapping = (
  item: ChatContentItem,
  pageIndices: number[],
  fallbackPage: number,
): ListenSlidePageMapping => {
  const itemIdentityBids = new Set(
    [item.element_bid, item.generated_block_bid].filter(Boolean),
  );
  const blockSlides = [...(item.listenSlides ?? [])]
    .filter(slide => {
      const generatedBlockBid = slide.generated_block_bid || '';
      const explicitSlideIdentityBids = [
        slide.element_bid,
        slide.target_element_bid,
      ].filter(
        (bid): bid is string => Boolean(bid) && bid !== generatedBlockBid,
      );

      if (explicitSlideIdentityBids.length > 0) {
        return explicitSlideIdentityBids.some(bid => itemIdentityBids.has(bid));
      }

      if (generatedBlockBid) {
        return item.generated_block_bid === generatedBlockBid;
      }

      return true;
    })
    .sort(
      (a, b) =>
        Number(a.slide_index ?? 0) - Number(b.slide_index ?? 0) ||
        Number(a.audio_position ?? 0) - Number(b.audio_position ?? 0),
    );
  const pageBySlideId = new Map<string, number>();
  const pageByAudioPosition = new Map<number, number>();
  const realSlides = blockSlides.filter(slide => !slide.is_placeholder);

  if (pageIndices.length > 0 && realSlides.length > 0) {
    realSlides.forEach((slide, index) => {
      const page = pageIndices[Math.min(index, pageIndices.length - 1)];
      pageBySlideId.set(slide.slide_id, page);
    });
  }

  blockSlides.forEach((slide, index) => {
    if (pageBySlideId.has(slide.slide_id)) {
      return;
    }

    const samePositionSlide = realSlides.find(
      candidate =>
        Number(candidate.audio_position ?? 0) ===
          Number(slide.audio_position ?? 0) &&
        pageBySlideId.has(candidate.slide_id),
    );
    if (samePositionSlide) {
      pageBySlideId.set(
        slide.slide_id,
        pageBySlideId.get(samePositionSlide.slide_id)!,
      );
      return;
    }

    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const previous = blockSlides[cursor];
      const previousPage = pageBySlideId.get(previous.slide_id);
      if (previousPage !== undefined) {
        pageBySlideId.set(slide.slide_id, previousPage);
        return;
      }
    }

    const firstPage = pageIndices[0];
    if (firstPage !== undefined) {
      pageBySlideId.set(slide.slide_id, firstPage);
      return;
    }

    pageBySlideId.set(slide.slide_id, fallbackPage);
  });

  blockSlides.forEach(slide => {
    const page = pageBySlideId.get(slide.slide_id);
    if (page === undefined) {
      return;
    }
    const position = Number(slide.audio_position ?? 0);
    const hasCurrent = pageByAudioPosition.has(position);
    if (!hasCurrent || !slide.is_placeholder) {
      pageByAudioPosition.set(position, page);
    }
  });

  const resolvePageByPosition = (position: number) => {
    if (pageByAudioPosition.has(position)) {
      return pageByAudioPosition.get(position)!;
    }
    const orderedPositions = [...pageByAudioPosition.keys()].sort(
      (a, b) => a - b,
    );
    let nearestLower: number | null = null;
    orderedPositions.forEach(candidate => {
      if (candidate <= position) {
        nearestLower = candidate;
      }
    });
    if (nearestLower !== null) {
      return pageByAudioPosition.get(nearestLower)!;
    }
    if (pageIndices.length > 0) {
      return pageIndices[0];
    }
    return fallbackPage;
  };

  return {
    blockSlides,
    pageBySlideId,
    resolvePageByPosition,
  };
};

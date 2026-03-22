import type { ChatContentItem } from './useChatLogicHook';
import type { AudioSegment, AudioTrack } from '@/c-utils/audio-utils';

export const sortByPosition = <T extends { position?: number }>(
  list: T[] = [],
) =>
  [...list].sort((a, b) => Number(a.position ?? 0) - Number(b.position ?? 0));

export const sortSegmentsByIndex = (segments: AudioSegment[] = []) =>
  [...segments].sort(
    (a, b) => Number(a.segmentIndex ?? 0) - Number(b.segmentIndex ?? 0),
  );

export const normalizeAudioTracks = (item: ChatContentItem): AudioTrack[] => {
  const trackByPosition = new Map<number, AudioTrack>();

  (item.audioTracks ?? []).forEach(track => {
    const position = Number(track.position ?? 0);
    trackByPosition.set(position, {
      ...track,
      position,
      audioSegments: sortSegmentsByIndex(track.audioSegments ?? []),
    });
  });

  return sortByPosition(Array.from(trackByPosition.values()));
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
  const blockSlides = [...(item.listenSlides ?? [])]
    .filter(slide => slide.element_bid === item.element_bid)
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

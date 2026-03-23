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
  blockSlides: any[];
  pageBySlideId: Map<string, number>;
  resolvePageByPosition: (position: number) => number;
}

export const buildSlidePageMapping = (
  _item: ChatContentItem,
  pageIndices: number[],
  fallbackPage: number,
): ListenSlidePageMapping => {
  const resolvePageByPosition = (position: number) => {
    if (pageIndices.length > 0) {
      return (
        pageIndices[Math.min(position, pageIndices.length - 1)] ??
        pageIndices[0]
      );
    }
    return fallbackPage;
  };

  return {
    blockSlides: [],
    pageBySlideId: new Map(),
    resolvePageByPosition,
  };
};

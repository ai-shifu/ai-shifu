import { create } from 'zustand';
import type { ListenSlideData } from '@/c-api/studyV2';
import type { ChatContentItem } from '@/c-types/chatUi';

export interface LessonRunContentCacheEntry {
  items: ChatContentItem[];
  pendingSlidesByBid: Record<string, ListenSlideData[]>;
  audioBackfillReadyBids: string[];
  updatedAt: number;
}

interface LessonRunContentStoreState {
  entries: Record<string, LessonRunContentCacheEntry>;
  replaceItems: (cacheKey: string, items: ChatContentItem[]) => void;
  updatePendingSlides: (
    cacheKey: string,
    updater: (
      pendingSlidesByBid: Record<string, ListenSlideData[]>,
    ) => Record<string, ListenSlideData[]>,
  ) => void;
  markAudioBackfillReady: (cacheKey: string, bids: string[]) => void;
  resetLesson: (cacheKey: string) => void;
  clearAll: () => void;
}

export const EMPTY_LESSON_RUN_ITEMS: ChatContentItem[] = [];

export const EMPTY_LESSON_RUN_CONTENT_ENTRY: LessonRunContentCacheEntry = {
  items: EMPTY_LESSON_RUN_ITEMS,
  pendingSlidesByBid: {},
  audioBackfillReadyBids: [],
  updatedAt: 0,
};

export const buildLessonRunContentCacheKey = ({
  shifuBid,
  outlineBid,
  previewMode = false,
}: {
  shifuBid: string;
  outlineBid: string;
  previewMode?: boolean;
}) =>
  `${shifuBid || 'unknown-shifu'}:${outlineBid || 'unknown-outline'}:${
    previewMode ? 'preview' : 'live'
  }`;

const createEmptyEntry = (): LessonRunContentCacheEntry => ({
  items: EMPTY_LESSON_RUN_ITEMS,
  pendingSlidesByBid: {},
  audioBackfillReadyBids: [],
  updatedAt: Date.now(),
});

const getExistingEntry = (
  entries: Record<string, LessonRunContentCacheEntry>,
  cacheKey: string,
) => entries[cacheKey] ?? createEmptyEntry();

export const useLessonRunContentStore = create<LessonRunContentStoreState>(
  set => ({
    entries: {},
    replaceItems: (cacheKey, items) => {
      if (!cacheKey) {
        return;
      }
      set(state => {
        const previousEntry = getExistingEntry(state.entries, cacheKey);
        return {
          entries: {
            ...state.entries,
            [cacheKey]: {
              ...previousEntry,
              items,
              updatedAt: Date.now(),
            },
          },
        };
      });
    },
    updatePendingSlides: (cacheKey, updater) => {
      if (!cacheKey) {
        return;
      }
      set(state => {
        const previousEntry = getExistingEntry(state.entries, cacheKey);
        return {
          entries: {
            ...state.entries,
            [cacheKey]: {
              ...previousEntry,
              pendingSlidesByBid: updater(previousEntry.pendingSlidesByBid),
              updatedAt: Date.now(),
            },
          },
        };
      });
    },
    markAudioBackfillReady: (cacheKey, bids) => {
      if (!cacheKey || bids.length === 0) {
        return;
      }
      set(state => {
        const previousEntry = getExistingEntry(state.entries, cacheKey);
        const readyBids = new Set(previousEntry.audioBackfillReadyBids);
        bids.forEach(bid => {
          if (bid) {
            readyBids.add(bid);
          }
        });
        return {
          entries: {
            ...state.entries,
            [cacheKey]: {
              ...previousEntry,
              audioBackfillReadyBids: Array.from(readyBids),
              updatedAt: Date.now(),
            },
          },
        };
      });
    },
    resetLesson: cacheKey => {
      if (!cacheKey) {
        return;
      }
      set(state => ({
        entries: {
          ...state.entries,
          [cacheKey]: createEmptyEntry(),
        },
      }));
    },
    clearAll: () => set({ entries: {} }),
  }),
);

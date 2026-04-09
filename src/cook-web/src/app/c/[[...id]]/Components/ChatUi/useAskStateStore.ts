import { create } from 'zustand';
import type { AskMessage } from './askState';
import {
  areAskMessageListsEqual,
  hasStreamingAskMessage,
  normalizeAskMessageList,
} from './askState';

type AskListUpdater =
  | AskMessage[]
  | ((previousAskList: AskMessage[]) => AskMessage[]);

interface AskStateStore {
  lessonScopeKey: string;
  askListByAnchorElementBid: Record<string, AskMessage[]>;
  ensureLessonScope: (lessonScopeKey: string) => void;
  hydrateAskList: (anchorElementBid: string, askList: AskMessage[]) => void;
  hydrateAskListMap: (askListMap: Map<string, AskMessage[]>) => void;
  setAskList: (anchorElementBid: string, askList: AskListUpdater) => void;
  clearLessonScope: () => void;
}

const shouldSkipHydration = (
  previousAskList: AskMessage[],
  normalizedAskList: AskMessage[],
) => {
  if (areAskMessageListsEqual(previousAskList, normalizedAskList)) {
    return true;
  }

  if (!normalizedAskList.length && previousAskList.length) {
    return true;
  }

  if (
    previousAskList.length &&
    hasStreamingAskMessage(previousAskList) &&
    normalizedAskList.length <= previousAskList.length
  ) {
    return true;
  }

  return false;
};

export const useAskStateStore = create<AskStateStore>((set, get) => ({
  lessonScopeKey: '',
  askListByAnchorElementBid: {},
  ensureLessonScope: lessonScopeKey => {
    if (!lessonScopeKey) {
      return;
    }

    if (get().lessonScopeKey === lessonScopeKey) {
      return;
    }

    set({
      lessonScopeKey,
      askListByAnchorElementBid: {},
    });
  },
  hydrateAskList: (anchorElementBid, askList) => {
    if (!anchorElementBid) {
      return;
    }

    const normalizedAskList = normalizeAskMessageList(askList);
    const previousAskList =
      get().askListByAnchorElementBid[anchorElementBid] ?? [];

    if (shouldSkipHydration(previousAskList, normalizedAskList)) {
      return;
    }

    set(state => ({
      askListByAnchorElementBid: {
        ...state.askListByAnchorElementBid,
        [anchorElementBid]: normalizedAskList,
      },
    }));
  },
  hydrateAskListMap: askListMap => {
    if (!askListMap.size) {
      return;
    }

    const previousAskListByAnchorElementBid = get().askListByAnchorElementBid;
    let hasChanges = false;
    const nextAskListByAnchorElementBid = {
      ...previousAskListByAnchorElementBid,
    };

    askListMap.forEach((askList, anchorElementBid) => {
      if (!anchorElementBid) {
        return;
      }

      const normalizedAskList = normalizeAskMessageList(askList);
      const previousAskList =
        previousAskListByAnchorElementBid[anchorElementBid] ?? [];

      if (shouldSkipHydration(previousAskList, normalizedAskList)) {
        return;
      }

      nextAskListByAnchorElementBid[anchorElementBid] = normalizedAskList;
      hasChanges = true;
    });

    if (!hasChanges) {
      return;
    }

    set({
      askListByAnchorElementBid: nextAskListByAnchorElementBid,
    });
  },
  setAskList: (anchorElementBid, askList) => {
    if (!anchorElementBid) {
      return;
    }

    const previousAskList =
      get().askListByAnchorElementBid[anchorElementBid] ?? [];
    const resolvedAskList =
      typeof askList === 'function' ? askList(previousAskList) : askList;
    const normalizedAskList = normalizeAskMessageList(resolvedAskList);

    if (areAskMessageListsEqual(previousAskList, normalizedAskList)) {
      return;
    }

    set(state => ({
      askListByAnchorElementBid: {
        ...state.askListByAnchorElementBid,
        [anchorElementBid]: normalizedAskList,
      },
    }));
  },
  clearLessonScope: () =>
    set({
      lessonScopeKey: '',
      askListByAnchorElementBid: {},
    }),
}));

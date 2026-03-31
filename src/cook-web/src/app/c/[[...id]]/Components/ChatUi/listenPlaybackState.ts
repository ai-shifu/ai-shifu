import { type Element as SlideElement } from 'markdown-flow-ui/slide';

type ListenStepElement = SlideElement & {
  blockBid?: string;
  page?: number;
};

export type ListenPlaybackState = {
  currentStepIndex: number;
  totalStepCount: number;
  currentStepHasAudio: boolean;
  currentStepHasBlockingInteraction: boolean;
  hasCompletedCurrentStepAudio: boolean;
  isAudioPlaying: boolean;
  isAudioWaiting: boolean;
};

export const getListenMarkerIdentityKey = (element?: SlideElement) => {
  const listenElement = element as ListenStepElement | undefined;

  if (!listenElement) {
    return '';
  }

  return [
    listenElement.type,
    listenElement.sequence_number,
    listenElement.blockBid ?? '',
    listenElement.page ?? '',
  ].join(':');
};

export const buildListenMarkerSequenceKey = (elements: SlideElement[]) =>
  elements.map(getListenMarkerIdentityKey).join('|');

export const reconcileListenPlaybackStepCount = (
  state: ListenPlaybackState,
  markerStepCount: number,
): ListenPlaybackState => {
  const nextStepIndex =
    markerStepCount <= 0
      ? -1
      : state.currentStepIndex < 0
        ? state.currentStepIndex
        : Math.min(state.currentStepIndex, markerStepCount - 1);

  if (
    state.totalStepCount === markerStepCount &&
    state.currentStepIndex === nextStepIndex
  ) {
    return state;
  }

  return {
    ...state,
    totalStepCount: markerStepCount,
    currentStepIndex: nextStepIndex,
  };
};

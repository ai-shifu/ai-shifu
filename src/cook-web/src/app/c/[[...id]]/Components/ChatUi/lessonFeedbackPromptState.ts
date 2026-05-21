import { isLessonFeedbackInteractionContent } from '@/c-utils/lesson-feedback-interaction';

type FeedbackPromptContentItem = {
  type?: string;
  content?: string | null;
  element_bid?: string | null;
};

type ListenFeedbackPromptDelayOptions = {
  lastItemIsLessonFeedbackInteraction: boolean;
  markerStepCount: number;
  currentStepIndex: number;
  currentStepHasAudio: boolean;
  currentStepHasBlockingInteraction: boolean;
  currentStepElementType?: string;
};

type ListenFeedbackPromptReadyOptions = {
  lastItemIsLessonFeedbackInteraction: boolean;
  markerStepCount: number;
  currentStepIndex: number;
  isPlaybackSequenceActive: boolean;
  hasSettledTailInteraction: boolean;
};

export const LESSON_FEEDBACK_TAIL_INTERACTION_SETTLE_DELAY_MS = 2000;

export const findLastVisibleLessonFeedbackElementBid = (
  items: FeedbackPromptContentItem[],
) => {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (
      item?.type === 'interaction' &&
      isLessonFeedbackInteractionContent(item.content || '')
    ) {
      return item.element_bid || '';
    }
  }

  return '';
};

export const shouldDelayListenFeedbackPromptForTailInteraction = ({
  lastItemIsLessonFeedbackInteraction,
  markerStepCount,
  currentStepIndex,
  currentStepHasAudio,
  currentStepHasBlockingInteraction,
  currentStepElementType,
}: ListenFeedbackPromptDelayOptions) =>
  lastItemIsLessonFeedbackInteraction &&
  markerStepCount > 0 &&
  currentStepIndex === markerStepCount - 1 &&
  currentStepElementType === 'interaction' &&
  !currentStepHasAudio &&
  !currentStepHasBlockingInteraction;

export const isListenLessonFeedbackPromptReady = ({
  lastItemIsLessonFeedbackInteraction,
  markerStepCount,
  currentStepIndex,
  isPlaybackSequenceActive,
  hasSettledTailInteraction,
}: ListenFeedbackPromptReadyOptions) =>
  lastItemIsLessonFeedbackInteraction &&
  markerStepCount > 0 &&
  currentStepIndex === markerStepCount - 1 &&
  !isPlaybackSequenceActive &&
  hasSettledTailInteraction;

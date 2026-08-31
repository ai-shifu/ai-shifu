import type { LearningMode } from './learningModeOptions';

export const LEARNING_MODE_SELECTION_EVENT =
  'learner_learning_mode_select' as const;
export const LAST_LEARNING_MODE_EVENT = 'learner_last_learning_mode' as const;

export type LearningModeSelectionSource = 'mobile_switch' | 'desktop_switch';

export const buildLearningModeSelectionAnalytics = ({
  from,
  to,
  source,
}: {
  from: LearningMode;
  to: LearningMode;
  source: LearningModeSelectionSource;
}) => ({
  from_learning_mode: from,
  to_learning_mode: to,
  source,
});

export const shouldTrackLastLearningMode = ({
  previewMode,
  storedLearningMode,
  resolvedLearningMode,
}: {
  previewMode: boolean;
  storedLearningMode: LearningMode | null;
  resolvedLearningMode: LearningMode;
}) =>
  !previewMode &&
  storedLearningMode !== null &&
  storedLearningMode === resolvedLearningMode;

export const buildLastLearningModeAnalytics = ({
  shifuBid,
  outlineBid,
  learningMode,
}: {
  shifuBid: string;
  outlineBid: string;
  learningMode: LearningMode;
}) => ({
  shifu_bid: shifuBid,
  ...(outlineBid ? { outline_bid: outlineBid } : {}),
  learning_mode: learningMode,
});

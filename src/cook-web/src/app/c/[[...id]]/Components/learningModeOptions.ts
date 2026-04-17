import type { TFunction } from 'i18next';

export type LearningMode = 'listen' | 'read';

type LearningModeOption = {
  mode: LearningMode;
};

export const LEARNING_MODE_OPTIONS = [
  {
    mode: 'listen',
  },
  {
    mode: 'read',
  },
] as const satisfies readonly LearningModeOption[];

export const getLearningModeLabel = (
  t: TFunction,
  learningMode: LearningMode,
) => {
  if (learningMode === 'listen') {
    return t('module.chat.learningModeListen');
  }

  return t('module.chat.learningModeRead');
};

export const isListenModeActive = ({
  learningMode,
  courseTtsEnabled,
}: {
  learningMode: LearningMode;
  courseTtsEnabled: boolean | null;
}) => learningMode === 'listen' && courseTtsEnabled !== false;

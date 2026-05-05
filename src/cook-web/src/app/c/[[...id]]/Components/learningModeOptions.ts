import type { TFunction } from 'i18next';

export type LearningMode = 'listen' | 'read';

type LearningModeOption = {
  mode: LearningMode;
};

export const LEARNING_MODE_OPTIONS = [
  {
    mode: 'read',
  },
  {
    mode: 'listen',
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

export const getLearningModeShortLabel = (
  t: TFunction,
  learningMode: LearningMode,
) => {
  if (learningMode === 'listen') {
    return t('module.chat.learningModeListenShort');
  }

  return t('module.chat.learningModeReadShort');
};

export const isListenModeActive = ({
  learningMode,
  courseTtsEnabled,
}: {
  learningMode: LearningMode;
  courseTtsEnabled: boolean | null;
}) => learningMode === 'listen' && courseTtsEnabled !== false;

import type { TFunction } from 'i18next';
import type { LearningMode } from '@/c-types/store';

export type { LearningMode };

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
  {
    mode: 'classroom',
  },
] as const satisfies readonly LearningModeOption[];

export const getAvailableLearningModeOptions = ({
  courseTtsEnabled,
  canUseClassroomMode,
}: {
  courseTtsEnabled: boolean | null;
  canUseClassroomMode: boolean | null;
}) =>
  LEARNING_MODE_OPTIONS.filter(option => {
    if (option.mode === 'listen') {
      return courseTtsEnabled !== false;
    }

    if (option.mode === 'classroom') {
      return canUseClassroomMode === true;
    }

    return true;
  });

export const getLearningModeLabel = (
  t: TFunction,
  learningMode: LearningMode,
) => {
  if (learningMode === 'classroom') {
    return t('module.chat.learningModeClassroom');
  }

  if (learningMode === 'listen') {
    return t('module.chat.learningModeListen');
  }

  return t('module.chat.learningModeRead');
};

export const getLearningModeShortLabel = (
  t: TFunction,
  learningMode: LearningMode,
) => {
  if (learningMode === 'classroom') {
    return t('module.chat.learningModeClassroomShort');
  }

  if (learningMode === 'listen') {
    return t('module.chat.learningModeListenShort');
  }

  return t('module.chat.learningModeReadShort');
};

export const getLearningModeTooltip = (
  t: TFunction,
  learningMode: LearningMode,
) => {
  if (learningMode === 'classroom') {
    return t('module.chat.learningModeClassroomTooltip');
  }

  if (learningMode === 'listen') {
    return t('module.chat.learningModeListenTooltip');
  }

  return t('module.chat.learningModeReadTooltip');
};

export const isListenModeActive = ({
  learningMode,
  courseTtsEnabled,
}: {
  learningMode: LearningMode;
  courseTtsEnabled: boolean | null;
}) => learningMode === 'listen' && courseTtsEnabled !== false;

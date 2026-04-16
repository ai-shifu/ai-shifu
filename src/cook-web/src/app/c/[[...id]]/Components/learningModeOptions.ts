import type { I18nKey } from '@/types/i18n-keys';

export type LearningMode = 'listen' | 'read';

type LearningModeOption = {
  mode: LearningMode;
  labelKey: I18nKey;
};

export const LEARNING_MODE_OPTIONS = [
  {
    mode: 'listen',
    labelKey: 'module.chat.learningModeListen',
  },
  {
    mode: 'read',
    labelKey: 'module.chat.learningModeRead',
  },
] as const satisfies readonly LearningModeOption[];

export const LEARNING_MODE_LABEL_KEYS = LEARNING_MODE_OPTIONS.reduce<
  Record<LearningMode, I18nKey>
>(
  (labels, option) => {
    labels[option.mode] = option.labelKey;
    return labels;
  },
  {} as Record<LearningMode, I18nKey>,
);

export const isListenModeActive = ({
  learningMode,
  courseTtsEnabled,
}: {
  learningMode: LearningMode;
  courseTtsEnabled: boolean | null;
}) => learningMode === 'listen' && courseTtsEnabled !== false;

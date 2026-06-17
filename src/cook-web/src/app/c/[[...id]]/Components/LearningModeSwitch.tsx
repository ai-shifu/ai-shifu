import styles from './LearningModeSwitch.module.scss';

import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useCourseStore } from '@/c-store/useCourseStore';
import {
  getAvailableLearningModeOptions,
  getLearningModeLabel,
  getLearningModeShortLabel,
  LEARNING_MODE_OPTIONS,
  type LearningMode,
} from './learningModeOptions';
import HeaderBetaBadge from './HeaderBetaBadge';
import { setLearningModeInUrl } from './learningModeUrl';

interface LearningModeSwitchProps {
  className?: string;
  size?: 'mobile' | 'desktop';
}

export const LearningModeSwitch = ({
  className,
  size = 'mobile',
}: LearningModeSwitchProps) => {
  const { t } = useTranslation();
  const courseTtsEnabled = useCourseStore(state => state.courseTtsEnabled);
  const { learningMode, updateLearningMode, canUseClassroomMode } =
    useSystemStore(
      useShallow(state => ({
        learningMode: state.learningMode,
        updateLearningMode: state.updateLearningMode,
        canUseClassroomMode: state.canUseClassroomMode,
      })),
    );
  const availableOptions = getAvailableLearningModeOptions({
    courseTtsEnabled,
    canUseClassroomMode,
  });
  const availableOptionModes = new Set(
    availableOptions.map(option => option.mode),
  );
  const renderedOptions = LEARNING_MODE_OPTIONS.filter(
    option =>
      availableOptionModes.has(option.mode) || option.mode === learningMode,
  );

  const handleLearningModeSelect = (nextLearningMode: LearningMode) => {
    setLearningModeInUrl(nextLearningMode);
    updateLearningMode(nextLearningMode);
  };

  if (renderedOptions.length <= 1) {
    return null;
  }

  return (
    <div
      role='radiogroup'
      aria-label={t('module.chat.learningModeToggle')}
      className={cn(
        styles.learningModeSwitch,
        size === 'desktop' ? styles.learningModeSwitchDesktop : '',
        className,
      )}
    >
      {renderedOptions.map(option => {
        const isActive = learningMode === option.mode;
        const isListenOption = option.mode === 'listen';

        return (
          <button
            type='button'
            role='radio'
            key={option.mode}
            aria-label={getLearningModeLabel(t, option.mode)}
            aria-checked={isActive}
            className={cn(
              styles.segment,
              isListenOption ? styles.listenSegment : '',
              size === 'desktop' ? styles.segmentDesktop : '',
              isActive ? styles.segmentActive : '',
            )}
            onClick={() => handleLearningModeSelect(option.mode)}
          >
            <span className={styles.segmentLabel}>
              {getLearningModeShortLabel(t, option.mode)}
            </span>
            {isListenOption ? (
              <HeaderBetaBadge
                variant='inline'
                className={styles.betaBadge}
              />
            ) : null}
          </button>
        );
      })}
    </div>
  );
};

export default memo(LearningModeSwitch);

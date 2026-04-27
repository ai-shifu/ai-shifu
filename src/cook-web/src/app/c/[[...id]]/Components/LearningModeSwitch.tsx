import styles from './LearningModeSwitch.module.scss';

import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { useSystemStore } from '@/c-store/useSystemStore';
import {
  getLearningModeShortLabel,
  LEARNING_MODE_OPTIONS,
} from './learningModeOptions';
import HeaderBetaBadge from './HeaderBetaBadge';

interface LearningModeSwitchProps {
  className?: string;
  size?: 'mobile' | 'desktop';
}

export const LearningModeSwitch = ({
  className,
  size = 'mobile',
}: LearningModeSwitchProps) => {
  const { t } = useTranslation();
  const { learningMode, updateLearningMode } = useSystemStore(
    useShallow(state => ({
      learningMode: state.learningMode,
      updateLearningMode: state.updateLearningMode,
    })),
  );

  return (
    <button
      type='button'
      aria-label={t('module.chat.learningModeToggle')}
      aria-pressed={learningMode === 'listen'}
      className={cn(
        styles.learningModeSwitch,
        size === 'desktop' ? styles.learningModeSwitchDesktop : '',
        className,
      )}
      onClick={() =>
        updateLearningMode(learningMode === 'listen' ? 'read' : 'listen')
      }
    >
      {LEARNING_MODE_OPTIONS.map(option => {
        const isActive = learningMode === option.mode;
        const isListenOption = option.mode === 'listen';

        return (
          <span
            key={option.mode}
            className={cn(
              styles.segment,
              isListenOption ? styles.listenSegment : '',
              size === 'desktop' ? styles.segmentDesktop : '',
              isActive ? styles.segmentActive : '',
            )}
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
          </span>
        );
      })}
    </button>
  );
};

export default memo(LearningModeSwitch);

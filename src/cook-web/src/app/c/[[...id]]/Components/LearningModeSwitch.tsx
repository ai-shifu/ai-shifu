import styles from './LearningModeSwitch.module.scss';

import {
  BookOpen,
  Headphones,
  Presentation,
  type LucideIcon,
} from 'lucide-react';
import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useCourseStore } from '@/c-store/useCourseStore';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  getAvailableLearningModeOptions,
  getLearningModeLabel,
  getLearningModeTooltip,
  LEARNING_MODE_OPTIONS,
  type LearningMode,
} from './learningModeOptions';
import { setLearningModeInUrl } from './learningModeUrl';

const learningModeIcons: Record<LearningMode, LucideIcon> = {
  read: BookOpen,
  listen: Headphones,
  classroom: Presentation,
};

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
    <TooltipProvider delayDuration={0}>
      <div
        role='radiogroup'
        aria-label={t('module.chat.learningModeToggle')}
        className={cn(styles.learningModeSwitch, className)}
      >
        {renderedOptions.map(option => {
          const isActive = learningMode === option.mode;
          const ModeIcon = learningModeIcons[option.mode];

          return (
            <Tooltip key={option.mode}>
              <TooltipTrigger asChild>
                <button
                  type='button'
                  role='radio'
                  aria-label={getLearningModeLabel(t, option.mode)}
                  aria-checked={isActive}
                  className={cn(
                    styles.segment,
                    size === 'desktop' ? styles.segmentDesktop : '',
                    isActive ? styles.segmentActive : '',
                  )}
                  onClick={() => handleLearningModeSelect(option.mode)}
                >
                  <ModeIcon
                    aria-hidden='true'
                    size={size === 'desktop' ? 16 : 12}
                    strokeWidth={2}
                  />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                {getLearningModeTooltip(t, option.mode)}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
};

export default memo(LearningModeSwitch);

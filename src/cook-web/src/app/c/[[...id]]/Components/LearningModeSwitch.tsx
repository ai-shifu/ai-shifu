import styles from './LearningModeSwitch.module.scss';

import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'next/navigation';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useEnvStore } from '@/c-store/envStore';
import { parseUrlParams } from '@/c-utils/urlUtils';
import type { CourseStoreState, EnvStoreState } from '@/c-types/store';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  getAvailableLearningModeOptions,
  getCourseScopedTtsEnabled,
  getLearningModeLabel,
  getLearningModeShortLabel,
  getLearningModeTooltip,
  LEARNING_MODE_OPTIONS,
  type LearningMode,
} from './learningModeOptions';
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
  const routeParams = useParams<{ id?: string[] }>();
  const courseId = useEnvStore((state: EnvStoreState) => state.courseId);
  const params = parseUrlParams() as Record<string, string>;
  const routeCourseId = Array.isArray(routeParams?.id) ? routeParams.id[0] : '';
  const storageCourseId = routeCourseId || params.courseId || courseId;
  const {
    courseTtsEnabled,
    courseTtsStatusCourseId,
    courseTtsStatusPreviewMode,
  } = useCourseStore(
    useShallow((state: CourseStoreState) => ({
      courseTtsEnabled: state.courseTtsEnabled,
      courseTtsStatusCourseId: state.courseTtsStatusCourseId,
      courseTtsStatusPreviewMode: state.courseTtsStatusPreviewMode,
    })),
  );
  const previewMode = useSystemStore(state => state.previewMode);
  const courseTtsEnabledForCourse = getCourseScopedTtsEnabled({
    courseTtsEnabled,
    courseTtsStatusCourseId,
    courseTtsStatusPreviewMode,
    courseId: storageCourseId,
    previewMode,
  });
  const { learningMode, updateLearningMode, canUseClassroomMode } =
    useSystemStore(
      useShallow(state => ({
        learningMode: state.learningMode,
        updateLearningMode: state.updateLearningMode,
        canUseClassroomMode: state.canUseClassroomMode,
      })),
    );
  const availableOptions = getAvailableLearningModeOptions({
    courseTtsEnabled: courseTtsEnabledForCourse,
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
                  <span className={styles.segmentLabel}>
                    {getLearningModeShortLabel(t, option.mode)}
                  </span>
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

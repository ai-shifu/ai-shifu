import classNames from 'classnames';
import styles from './CourseSection.module.scss';
import { useCallback, useContext } from 'react';
import { memo } from 'react';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import ResetChapterButton from './ResetChapterButton';
import { AppContext } from '../AppContext';
import Image from 'next/image';
import imgLearningSelected from '@/c-assets/newchat/light/icon16-learning-selected.png';
import imgLearning from '@/c-assets/newchat/light/icon16-learning.png';
import { CircleCheck, CircleDotDashed } from 'lucide-react';
import imgLearningCompletedSelected from '@/c-assets/newchat/light/icon16-learning-completed-selected.png';
import imgLearningCompleted from '@/c-assets/newchat/light/icon16-learning-completed.png';
import { LEARNING_PERMISSION } from '@/c-api/studyV2';
import { useUserStore } from '@/store';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useTranslation } from 'react-i18next';

const getCourseTitleLang = (title: string) => {
  const trimmed = title.trim();
  if (!trimmed) {
    return undefined;
  }
  const containsLatin = /[A-Za-z]/.test(trimmed);
  const containsCJK = /[\u4E00-\u9FFF]/.test(trimmed);
  return containsLatin && !containsCJK ? 'en' : undefined;
};

export const CourseSection = ({
  id,
  name = '',
  type,
  is_paid,
  status_value = LESSON_STATUS_VALUE.LEARNING,
  selected,
  canLearning = false,
  chapterId,
  onSelect,
  onTrySelect,
}) => {
  const { t } = useTranslation();
  const courseTitleLang = getCourseTitleLang(name);
  const { mobileStyle } = useContext(AppContext);
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const { openPayModal } = useCourseStore(
    useShallow(state => ({
      openPayModal: state.openPayModal,
    })),
  );
  const genIconClassName = () => {
    switch (status_value) {
      // @ts-expect-error EXPECT
      case LESSON_STATUS_VALUE.NOT_START:
      case LESSON_STATUS_VALUE.LOCKED:
        return styles.small;
      case LESSON_STATUS_VALUE.PREPARE_LEARNING:
      case LESSON_STATUS_VALUE.LEARNING:
      case LESSON_STATUS_VALUE.COMPLETED:
        return '';
      default:
        return styles.small;
    }
  };

  const onSectionClick = useCallback(() => {
    onTrySelect?.({ id });

    if (status_value === LESSON_STATUS_VALUE.LOCKED) {
      return;
    }

    if (
      (type === LEARNING_PERMISSION.TRIAL ||
        type === LEARNING_PERMISSION.NORMAL) &&
      !isLoggedIn
    ) {
      window.location.href = `/login?redirect=${encodeURIComponent(location.pathname + location.search)}`;
      return;
    }

    if (type === LEARNING_PERMISSION.NORMAL && !is_paid) {
      openPayModal({
        type,
        payload: {
          chapterId,
          lessonId: id,
        },
      });
      return;
    }

    onSelect?.({ id });
  }, [
    onTrySelect,
    id,
    is_paid,
    status_value,
    onSelect,
    type,
    isLoggedIn,
    openPayModal,
    chapterId,
  ]);

  const onResetButtonClick = useCallback(e => {
    e.stopPropagation();
  }, []);

  const isNormalNotPaid = type === LEARNING_PERMISSION.NORMAL && !is_paid;

  const leftSection = (
    <div
      className={cn(styles.leftSection, isNormalNotPaid ? styles.notPaid : '')}
    >
      <div className={styles.courseTitle} lang={courseTitleLang}>
        {name}
      </div>
    </div>
  );

  return (
    <div
      className={classNames(
        styles.courseSection,
        selected && styles.selected,
        canLearning ? styles.available : styles.unavailable,
        mobileStyle && styles.mobile,
      )}
      onClick={onSectionClick}
    >
      <div className={classNames(styles.iconWrapper, genIconClassName())}>
        <div className={styles.topLine}></div>
        <div className={styles.icon}>
          {type === LEARNING_PERMISSION.NORMAL && !is_paid ? (
            <CircleDotDashed
              className={styles.bigIcon}
              color='rgba(10, 10, 10, 0.1)'
            />
          ) : (
            <>
              {status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING && (
                <CircleDotDashed
                  className={styles.bigIcon}
                  color={selected ? '#0A0A0A' : 'rgba(10, 10, 10, 0.1)'}
                />
              )}

              {status_value === LESSON_STATUS_VALUE.LEARNING && (
                <CircleDotDashed className={styles.bigIcon} />
              )}
              {status_value === LESSON_STATUS_VALUE.COMPLETED && (
                <CircleCheck className={styles.bigIcon} />
              )}
            </>
          )}
        </div>
        <div className={styles.bottomLine}></div>
      </div>
      <div className={styles.textArea}>
        {isNormalNotPaid ? (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>{leftSection}</TooltipTrigger>
              <TooltipContent
                side='top'
                className='bg-[#0A0A0A] text-white border-transparent text-xs'
              >
                {t('module.lesson.tooltip.paidExclusive')}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : (
          leftSection
        )}
        <div className={styles.rightSection}>
          {(status_value === LESSON_STATUS_VALUE.LEARNING ||
            status_value === LESSON_STATUS_VALUE.COMPLETED) && (
            // @ts-expect-error EXPECT
            <ResetChapterButton
              onClick={onResetButtonClick}
              chapterId={chapterId}
              chapterName={name}
              className={styles.resetButton}
              lessonId={id}
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default memo(CourseSection);

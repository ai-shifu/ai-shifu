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
import imgLearningCompletedSelected from '@/c-assets/newchat/light/icon16-learning-completed-selected.png';
import imgLearningCompleted from '@/c-assets/newchat/light/icon16-learning-completed.png';
import { LEARNING_PERMISSION } from '@/c-api/studyV2';
import { useUserStore } from '@/store';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useShallow } from 'zustand/react/shallow';

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
      window.location.href = `/login?redirect=${encodeURIComponent(location.pathname)}`;
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
          {/* @ts-expect-error EXPECT */}
          {(status_value === LESSON_STATUS_VALUE.NOT_START ||
            status_value === LESSON_STATUS_VALUE.LOCKED) && (
            <div className={styles.smallIcon}></div>
          )}
          {(status_value === LESSON_STATUS_VALUE.LEARNING ||
            status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING) &&
            (selected ? (
              <Image
                className={styles.bigIcon}
                width={16}
                height={16}
                src={imgLearningSelected.src}
                alt=''
              />
            ) : (
              <Image
                className={styles.bigIcon}
                width={16}
                height={16}
                src={imgLearning.src}
                alt=''
              />
            ))}
          {status_value === LESSON_STATUS_VALUE.COMPLETED &&
            (selected ? (
              <Image
                className={styles.bigIcon}
                width={16}
                height={16}
                src={imgLearningCompletedSelected.src}
                alt=''
              />
            ) : (
              <Image
                className={styles.bigIcon}
                width={16}
                height={16}
                src={imgLearningCompleted.src}
                alt=''
              />
            ))}
        </div>
        <div className={styles.bottomLine}></div>
      </div>
      <div className={styles.textArea}>
        <div className={styles.leftSection}>
          <div className={styles.courseTitle}>{name}</div>
        </div>
        <div className={styles.rightSection}>
          {(status_value === LESSON_STATUS_VALUE.LEARNING ||
            status_value === LESSON_STATUS_VALUE.COMPLETED) && (
            // @ts-expect-error EXPECT
            <ResetChapterButton
              onClick={onResetButtonClick}
              chapterId={id}
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

import classNames from 'classnames';
import styles from './CourseSection.module.scss';
import { useCallback } from 'react';
import { memo } from 'react';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';

import imgLearningSelected from '@/c-assets/newchat/light/icon16-learning-selected.png'
import imgLearning from '@/c-assets/newchat/light/icon16-learning.png'
import imgLearningCompletedSelected from '@/c-assets/newchat/light/icon16-learning-completed-selected.png'
import imgLearningCompleted from '@/c-assets/newchat/light/icon16-learning-completed.png'

export const CourseSection = ({
  id,
  name = '',
  status = '',
  status_value = LESSON_STATUS_VALUE.LEARNING,
  selected,
  canLearning = false,
  onSelect = ({ id }) => {},
  onTrySelect= ({ id }) => {},
}) => {
  const genIconClassName = () => {
    switch (status_value) {
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
    if (status_value === LESSON_STATUS_VALUE.NOT_START || status_value === LESSON_STATUS_VALUE.LOCKED) {
      return;
    }

    onSelect?.({ id });
  }, [onTrySelect, id, status_value, onSelect]);

  return (
    <div
      className={classNames(
        styles.courseSection,
        selected && styles.selected,
        canLearning ? styles.available : styles.unavailable
      )}
      onClick={onSectionClick}
    >
      <div className={classNames(styles.iconWrapper, genIconClassName())}>
        <div className={styles.topLine}></div>
        <div className={styles.icon}>
          {(status_value === LESSON_STATUS_VALUE.NOT_START ||
            status_value === LESSON_STATUS_VALUE.LOCKED) && (
            <div className={styles.smallIcon}></div>
          )}
          {(status_value === LESSON_STATUS_VALUE.LEARNING ||
            status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING) &&
            (selected ? (
              <img
                className={styles.bigIcon}
                src={imgLearningSelected.src}
                alt=""
              />
            ) : (
              <img
                className={styles.bigIcon}
                src={imgLearning.src}
                alt=""
              />
            ))}
          {status_value === LESSON_STATUS_VALUE.COMPLETED &&
            (selected ? (
              <img
                className={styles.bigIcon}
                src={imgLearningCompletedSelected.src}
                alt=""
              />
            ) : (
              <img
                className={styles.bigIcon}
                src={imgLearningCompleted.src}
                alt=""
              />
            ))}
        </div>
        <div className={styles.bottomLine}></div>
      </div>
      <div className={styles.textArea}>
        <div className={styles.courseTitle}>{name}</div>
      </div>
    </div>
  );
};

export default memo(CourseSection);

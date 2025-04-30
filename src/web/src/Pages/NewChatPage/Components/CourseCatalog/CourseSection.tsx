import classNames from 'classnames';
import styles from './CourseSection.module.scss';
import { useCallback } from 'react';
import { memo } from 'react';
import { LESSON_STATUS_VALUE } from 'constants/courseConstants';

export const CourseSection = ({
  id,
  name = '',
  status = '',
  status_value = LESSON_STATUS_VALUE.LEARNING,
  selected,
  canLearning = false,
  onSelect = ({ id }) => {},
  onTrySelect = ({ id }) => {},
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
    if (
      status_value === LESSON_STATUS_VALUE.NOT_START ||
      status_value === LESSON_STATUS_VALUE.LOCKED
    ) {
      return;
    }

    onSelect?.({ id });
  }, [onTrySelect, id, status_value, onSelect]);

  return (
    <div
      className={classNames(
        styles.courseSection,
        selected && styles.selected,
        canLearning ? styles.available : styles.unavailable,
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
                src={require('@Assets/newchat/light/icon16-learning-selected.png')}
                alt=""
              />
            ) : (
              <img
                className={styles.bigIcon}
                src={require('@Assets/newchat/light/icon16-learning.png')}
                alt=""
              />
            ))}
          {status_value === LESSON_STATUS_VALUE.COMPLETED &&
            (selected ? (
              <img
                className={styles.bigIcon}
                src={require('@Assets/newchat/light/icon16-learning-completed-selected.png')}
                alt=""
              />
            ) : (
              <img
                className={styles.bigIcon}
                src={require('@Assets/newchat/light/icon16-learning-completed.png')}
                alt=""
              />
            ))}
        </div>
        <div className={styles.bottomLine}></div>
      </div>
      <div className={styles.textArea}>
        <div className={styles.label}>{status}</div>
        <div className={styles.courseTitle}>{name}</div>
      </div>
    </div>
  );
};

export default memo(CourseSection);

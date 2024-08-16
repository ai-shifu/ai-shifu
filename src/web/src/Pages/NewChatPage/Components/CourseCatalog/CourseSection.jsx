import classNames from "classnames";
import styles from "./CourseSection.module.scss";
import { LESSON_STATUS } from "constants/courseConstants.js";

export const CourseSection = ({
  id,
  name = '',
  status = LESSON_STATUS.LEARNING,
  selected,
  canLearning = false,
  onSelect = ({ id }) => {},
}) => {
  const genIconClassName = () => {
    switch (status) {
      case LESSON_STATUS.NOT_START:
      case LESSON_STATUS.LOCKED:
        return styles.small;
      case LESSON_STATUS.PREPARE_LEARNING:
      case LESSON_STATUS.LEARNING:
      case LESSON_STATUS.COMPLETED:
        return "";
      default:
        return styles.small;
    }
  };

  return (
    <div
      className={classNames(
        styles.courseSection,
        selected && styles.selected,
        canLearning ? styles.available : styles.unavailable
      )}
      onClick={() => onSelect({ id })}
    >
      <div className={classNames(styles.iconWrapper, genIconClassName())}>
        <div className={styles.topLine}></div>
        <div className={styles.icon}>
          {(status === LESSON_STATUS.NOT_START ||
            status === LESSON_STATUS.LOCKED) && (
            <div className={styles.smallIcon}></div>
          )}
          {(status === LESSON_STATUS.LEARNING || status === LESSON_STATUS.PREPARE_LEARNING) &&
            (selected ? (
              <img
                className={styles.bigIcon}
                src={require("@Assets/newchat/light/icon16-learning-selected.png")}
                alt=""
              />
            ) : (
              <img
                className={styles.bigIcon}
                src={require("@Assets/newchat/light/icon16-learning.png")}
                alt=""
              />
            ))}
          {status === LESSON_STATUS.COMPLETED &&
            (selected ? (
              <img
                className={styles.bigIcon}
                src={require("@Assets/newchat/light/icon16-learning-completed-selected.png")}
                alt=""
              />
            ) : (
              <img
                className={styles.bigIcon}
                src={require("@Assets/newchat/light/icon16-learning-completed.png")}
                alt=""
              />
            ))}
        </div>
        <div className={styles.bottomLine}></div>
      </div>
      <div className={styles.textArea}>
        <div className={styles.label}>{status}</div>
        <div className={styles.courseTitle}>
          {name}
        </div>
      </div>
    </div>
  );
};

export default CourseSection;

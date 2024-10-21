import classNames from 'classnames';
import styles from './CourseSection.module.scss';
import { SECTION_STATUS } from 'constants/courseContants.js';
import style from 'react-syntax-highlighter/dist/esm/styles/hljs/a11y-dark';

export const CourseSection = ({ status = SECTION_STATUS.learning, selected }) => {
  const genIconClassName = () => {
    switch (status) {
      case SECTION_STATUS.notStart:
      case SECTION_STATUS.unavailable:
        return styles.small;
      case SECTION_STATUS.learning:
      case SECTION_STATUS.completed:
        return '';
      default:
        return styles.small;
    }
  }

  return (<div className={styles.courseSection}>
    <div className={classNames(styles.iconWrapper, genIconClassName())}>
      <div className={styles.topLine}></div>
      <div className={styles.icon} >
        {
          (status === SECTION_STATUS.notStart || status === SECTION_STATUS.unavailable)
          && <div className={styles.smallIcon}></div>
        }
        { status === SECTION_STATUS.learning
          && <img className={styles.bigIcon} src={require('@Assets/newchat/light/icon16-learning.png')} alt="" /> }
        { status === SECTION_STATUS.completed
          && <img className={styles.bigIcon} src={require('@Assets/newchat/light/icon16-learning-completed.png')} alt="" /> }
      </div>
      <div className={styles.bottomLine}></div>
    </div>
    <div className={styles.textArea}>
      <div className={styles.label}>正在学</div>
      <div className={styles.courseTitle}>1.1 课程标题课程标题课程标题课程标题课程标题课程标</div>
    </div>
  </div>);
}

export default CourseSection;

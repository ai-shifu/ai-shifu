import classNames from 'classnames';
import { AppContext } from 'Components/AppContext';
import CourseSection from './CourseSection';
import styles from './CourseCatalog.module.scss';
import { memo, useContext, useCallback } from 'react';
import ResetChapterButton from './ResetChapterButton';
import { LESSON_STATUS_VALUE } from 'constants/courseConstants';

export const CourseCatalog = ({
  id = 0,
  name = '',
  status,
  lessons = [],
  collapse = false,
  selectedLessonId = '',
  onCollapse = ({ id }) => {},
  onLessonSelect = ({ id }) => {},
  onTrySelect = ({ chapterId, lessonId }) => {},
}) => {
  const _onTrySelect = useCallback(
    ({ id: lessonId }) => {
      onTrySelect?.({ chapterId: id, lessonId });
    },
    [id, onTrySelect],
  );

  const onResetButtonClick = useCallback((e) => {
    e.stopPropagation();
  }, []);

  const onTitleRowClick = useCallback(() => {
    onCollapse?.({ id });
  }, [id, onCollapse]);

  const { mobileStyle } = useContext(AppContext);

  return (
    <div
      className={classNames(
        styles.courseCatalog,
        collapse && styles.collapse,
        mobileStyle && styles.mobile,
      )}
    >
      <div className={styles.titleRow} onClick={onTitleRowClick}>
        <div className={styles.leftSection}>{name}</div>
        <div className={styles.rightSection}>
          {(status === LESSON_STATUS_VALUE.LEARNING ||
            status === LESSON_STATUS_VALUE.COMPLETED) && (
            <ResetChapterButton
              onClick={onResetButtonClick}
              chapterId={id}
              className={styles.resetButton}
              lessonId={lessons?.[0]?.id}
            />
          )}
          <img
            className={styles.collapseBtn}
            src={require('@Assets/newchat/light/icon16-arrow-down.png')}
            alt=""
          />
        </div>
      </div>
      <div className={styles.sectionList}>
        {lessons.map((e) => {
          return (
            <CourseSection
              key={e.id}
              id={e.id}
              name={e.name}
              status={e.status}
              status_value={e.status_value}
              selected={e.id === selectedLessonId}
              canLearning={e.canLearning}
              onSelect={onLessonSelect}
              onTrySelect={_onTrySelect}
            />
          );
        })}
      </div>
    </div>
  );
};

export default memo(CourseCatalog);

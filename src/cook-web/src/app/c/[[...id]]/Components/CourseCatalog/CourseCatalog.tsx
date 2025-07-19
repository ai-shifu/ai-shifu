import { memo, useContext, useCallback } from 'react';

import { AppContext } from '@/c-components/AppContext';
import CourseSection from './CourseSection';
import styles from './CourseCatalog.module.scss';

import ResetChapterButton from './ResetChapterButton';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';

import { cn } from '@/lib/utils';

import { ChevronDownIcon } from 'lucide-react'

export const CourseCatalog = ({
  id = 0,
  name = '',
  status,
  lessons = [],
  collapse = false,
  selectedLessonId = '',
  onCollapse,
  onLessonSelect = () => {},
  onTrySelect,
}) => {

  const _onTrySelect = useCallback(
    ({ id: lessonId }) => {
      onTrySelect?.({ chapterId: id, lessonId });
    },
    [id, onTrySelect]
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
      className={cn(
        styles.courseCatalog,
        collapse && styles.collapse,
        mobileStyle && styles.mobile
      )}
    >
      <div className={styles.titleRow} onClick={onTitleRowClick}>
        <div className={styles.leftSection}>{name}</div>
        <div className={styles.rightSection}>
          {status === LESSON_STATUS_VALUE.LEARNING || status === LESSON_STATUS_VALUE.COMPLETED ? (
            // @ts-expect-error EXPECT
            <ResetChapterButton
              onClick={onResetButtonClick}
              chapterId={id}
              className={styles.resetButton}
              // @ts-expect-error EXPECT
              lessonId={lessons?.[0]?.id}
            />
          ) : null }
          <ChevronDownIcon className={styles.collapseBtn} />
        </div>
      </div>
      <div className={styles.sectionList}>
        {lessons.map((e) => {
          return (
            <CourseSection
            // @ts-expect-error EXPECT
              key={e.id}
              // @ts-expect-error EXPECT
              id={e.id}
              // @ts-expect-error EXPECT
              name={e.name}
              // @ts-expect-error EXPECT
              status={e.status}
              // @ts-expect-error EXPECT
              status_value={e.status_value}
              // @ts-expect-error EXPECT
              selected={e.id === selectedLessonId}
              // @ts-expect-error EXPECT
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

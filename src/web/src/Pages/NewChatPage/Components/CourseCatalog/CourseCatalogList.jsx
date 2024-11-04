// 课程目录
import { memo } from 'react';
import CourseCatalog from './CourseCatalog.jsx';
import styles from './CourseCatalogList.module.scss';
import { useTranslation } from 'react-i18next';

export const CourseCatalogList = ({
  catalogs = [],
  catalogCount = 0,
  lessonCount = 0,
  onChapterCollapse = ({ id }) => {},
  onLessonSelect = ({ id }) => {},
  onTryLessonSelect = ({ chapterId, lessonId}) => {},
}) => {
  const { t } = useTranslation();
  return (
    <div className={styles.courseCatalogList}>
      <div className={styles.titleRow}>
        <div className={styles.titleArea}>
          <img
            className={styles.icon}
            src={require('@Assets/newchat/light/icon16-course-list.png')}
            alt={t('navigation.courseList')}
          />
          <div className={styles.titleName}>{t('navigation.courseList')}</div>
        </div>
        <div className={styles.chapterCount}>
          {lessonCount}{t('navigation.theLesson')}/{catalogCount}{t('navigation.theChapter')}
        </div>
      </div>
      <div className={styles.listRow}>
        {catalogs.map((catalog) => {
          return (
            <CourseCatalog
              key={catalog.id}
              id={catalog.id}
              name={catalog.name}
              status={catalog.status_value}
              lessons={catalog.lessons}
              collapse={catalog.collapse}
              onCollapse={onChapterCollapse}
              onLessonSelect={onLessonSelect}
              onTrySelect={onTryLessonSelect}
            />
          );
        })}
      </div>
    </div>
  );
};

export default memo(CourseCatalogList);

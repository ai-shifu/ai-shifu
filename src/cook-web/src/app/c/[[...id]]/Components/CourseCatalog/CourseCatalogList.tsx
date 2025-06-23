// 课程目录
import { memo, useCallback, useState, useEffect } from 'react';
import styles from './CourseCatalogList.module.scss';
import { useTranslation } from 'react-i18next';
import { shifu } from '@/c-service/Shifu';
import TrialNodeBottomArea from './TrialNodeBottomArea';
import CourseCatalog from './CourseCatalog';
import { TRAIL_NODE_POSITION } from './TrialNodeBottomArea';
import TrialNodeOuter from './TrialNodeOuter';

// TODO: 替换成 lucide icon
import imgCourseList from '@/c-assets/newchat/light/icon16-course-list.png'


export const CourseCatalogList = ({
  courseName = '',
  catalogs = [],
  containerScrollTop = 0,
  containerHeight = 0,
  onChapterCollapse = ({ id }) => {},
  onLessonSelect = ({ id }) => {},
  onTryLessonSelect = ({ chapterId, lessonId }) => {},
  selectedLessonId = '',
  bannerInfo = null,
}) => {
  const { t } = useTranslation();
  const [trialNodePosition, setTrialNodePosition] = useState(
    TRAIL_NODE_POSITION.NORMAL
  );
  const [trialNodePayload, setTrialNodePayload] = useState(null);

  const getRightAreaControl = useCallback(() => {
    const Control = shifu.getControl(
      shifu.ControlTypes.NAVIGATOR_TITLE_RIGHT_AREA
    );

    return Control && bannerInfo ? <Control payload={bannerInfo} /> : <></>;
  }, [bannerInfo]);

  useEffect(() => {
    setTrialNodePayload(
      catalogs.find((c) => !!c.bannerInfo)?.bannerInfo || null
    );
  }, [catalogs]);

  const onNodePositionChange = (position) => {
    setTrialNodePosition(position);
  }

  return (
    <>
      <div className={styles.courseCatalogList}>
        <div className={styles.titleRow}>
          <div className={styles.titleArea}>
            <img
              className={styles.icon}
              src={imgCourseList.src}
              alt={t('navigation.courseList')}
            />
            <div className={styles.titleName}>{courseName}</div>
          </div>
          {getRightAreaControl()}
        </div>
        <div className={styles.listRow}>
          {catalogs.map((catalog) => {
            return (
              <div key={catalog.id}>
                <CourseCatalog
                  key={catalog.id}
                  id={catalog.id}
                  name={catalog.name}
                  status={catalog.status_value}
                  selectedLessonId={selectedLessonId}
                  lessons={catalog.lessons}
                  collapse={catalog.collapse}
                  onCollapse={onChapterCollapse}
                  onLessonSelect={onLessonSelect}
                  onTrySelect={onTryLessonSelect}
                />
                {catalog.bannerInfo && (
                  <TrialNodeBottomArea
                    containerHeight={containerHeight}
                    containerScrollTop={containerScrollTop}
                    payload={catalog.bannerInfo}
                    onNodePositionChange={onNodePositionChange}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
      {trialNodePosition !== TRAIL_NODE_POSITION.NORMAL && (
        <TrialNodeOuter
          nodePosition={trialNodePosition}
          payload={trialNodePayload}
          containerScrollTop={containerScrollTop}
        />
      )}
    </>
  );
};

export default memo(CourseCatalogList);

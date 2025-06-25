// 课程目录
import { memo, useCallback, useState, useEffect } from 'react';
import styles from './CourseCatalogList.module.scss';
import { useTranslation } from 'react-i18next';
import { shifu } from '@/c-service/Shifu';
import TrialNodeBottomArea from './TrialNodeBottomArea';
import CourseCatalog from './CourseCatalog';
import { TRAIL_NODE_POSITION } from './TrialNodeBottomArea';
import TrialNodeOuter from './TrialNodeOuter';

import Image from 'next/image';
import imgCourseList from '@/c-assets/newchat/light/icon16-course-list.png'

export const CourseCatalogList = ({
  courseName = '',
  catalogs = [],
  containerScrollTop = 0,
  containerHeight = 0,
  onChapterCollapse,
  onLessonSelect,
  onTryLessonSelect,
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
      // @ts-expect-error EXPECT
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
            <Image
              className={styles.icon}
              width={16}
              height={16}
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
              // @ts-expect-error EXPECT
              <div key={catalog.id}>
                <CourseCatalog
                // @ts-expect-error EXPECT
                  key={catalog.id}
                  // @ts-expect-error EXPECT
                  id={catalog.id}
                  // @ts-expect-error EXPECT
                  name={catalog.name}
                  // @ts-expect-error EXPECT
                  status={catalog.status_value}
                  selectedLessonId={selectedLessonId}
                  // @ts-expect-error EXPECT
                  lessons={catalog.lessons}
                  // @ts-expect-error EXPECT
                  collapse={catalog.collapse}
                  onCollapse={onChapterCollapse}
                  onLessonSelect={onLessonSelect}
                  onTrySelect={onTryLessonSelect}
                />
                {/* @ts-expect-error EXPECT */}
                {catalog.bannerInfo && (
                  <TrialNodeBottomArea
                    containerHeight={containerHeight}
                    containerScrollTop={containerScrollTop}
                    // @ts-expect-error EXPECT
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
          // @ts-expect-error EXPECT
          containerScrollTop={containerScrollTop}
        />
      )}
    </>
  );
};

export default memo(CourseCatalogList);

// Course catalog
import { memo, useState, useEffect } from 'react';
import styles from './CourseCatalogList.module.scss';
import { cn } from '@/lib/utils';
import TrialNodeBottomArea from './TrialNodeBottomArea';
import CourseCatalog from './CourseCatalog';
import { TRAIL_NODE_POSITION } from './TrialNodeBottomArea';
import TrialNodeOuter from './TrialNodeOuter';
import CourseHeaderSummary from '../CourseHeaderSummary';
export const CourseCatalogList = ({
  courseName = '',
  courseAvatar = '',
  catalogs = [],
  containerScrollTop = 0,
  containerHeight = 0,
  onChapterCollapse,
  onLessonSelect,
  onTryLessonSelect,
  selectedLessonId = '',
  hideCourseHeader = false,
}) => {
  const [trialNodePosition, setTrialNodePosition] = useState(
    TRAIL_NODE_POSITION.NORMAL,
  );
  const [trialNodePayload, setTrialNodePayload] = useState(null);

  useEffect(() => {
    setTrialNodePayload(
      // @ts-expect-error EXPECT
      catalogs.find(c => !!c.bannerInfo)?.bannerInfo || null,
    );
  }, [catalogs]);

  const onNodePositionChange = position => {
    setTrialNodePosition(position);
  };

  return (
    <>
      <div className={styles.courseCatalogList}>
        {!hideCourseHeader ? (
          <div className={styles.titleRow}>
            <CourseHeaderSummary
              courseAvatar={courseAvatar}
              courseName={courseName}
              className={styles.titleArea}
            />
          </div>
        ) : null}
        <div
          className={cn(
            styles.listRow,
            hideCourseHeader ? styles.listRowWithoutHeader : '',
          )}
        >
          {catalogs.map(catalog => {
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

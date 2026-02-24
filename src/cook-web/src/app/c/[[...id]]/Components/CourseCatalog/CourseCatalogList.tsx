// Course catalog
import { memo, useState, useEffect } from 'react';
import styles from './CourseCatalogList.module.scss';
import TrialNodeBottomArea from './TrialNodeBottomArea';
import CourseCatalog from './CourseCatalog';
import { TRAIL_NODE_POSITION } from './TrialNodeBottomArea';
import TrialNodeOuter from './TrialNodeOuter';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';
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
        <div className={styles.titleRow}>
          <div className={styles.titleArea}>
            {courseAvatar && (
              <Avatar className='w-8 h-8 mr-3'>
                <AvatarImage src={courseAvatar} />
              </Avatar>
            )}
            <div className={styles.titleName}>{courseName}</div>
          </div>
        </div>
        <div className={styles.listRow}>
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

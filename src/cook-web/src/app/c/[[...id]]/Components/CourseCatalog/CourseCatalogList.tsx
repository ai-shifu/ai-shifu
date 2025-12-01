// Course catalog
import { memo, useCallback, useState, useEffect, useContext } from 'react';
import styles from './CourseCatalogList.module.scss';
import { useTranslation } from 'react-i18next';
import { shifu } from '@/c-service/Shifu';
import TrialNodeBottomArea from './TrialNodeBottomArea';
import CourseCatalog from './CourseCatalog';
import { TRAIL_NODE_POSITION } from './TrialNodeBottomArea';
import TrialNodeOuter from './TrialNodeOuter';
import { AppContext } from '../AppContext';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
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
  bannerInfo = null,
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
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className={styles.titleName}>{courseName}</div>
                </TooltipTrigger>
                <TooltipContent
                  side='top'
                  className='bg-[#0A0A0A] text-white border-transparent text-xs'
                >
                  {courseName}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
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

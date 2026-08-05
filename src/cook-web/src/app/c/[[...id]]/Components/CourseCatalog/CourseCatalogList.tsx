// Course catalog
import { memo, useState, useEffect } from 'react';
import type { LessonTreeCatalog } from '../../hooks/useLessonTree';
import styles from './CourseCatalogList.module.scss';
import { cn } from '@/lib/utils';
import TrialNodeBottomArea from './TrialNodeBottomArea';
import CourseCatalog from './CourseCatalog';
import {
  TRAIL_NODE_POSITION,
  type TrialNodePosition,
} from './TrialNodeBottomArea';
import TrialNodeOuter from './TrialNodeOuter';
import CourseHeaderSummary from '../CourseHeaderSummary';
type CourseCatalogListCatalog = LessonTreeCatalog & { bannerInfo?: unknown };

type CourseCatalogListProps = {
  courseName?: string;
  courseAvatar?: string;
  catalogs?: CourseCatalogListCatalog[];
  containerScrollTop?: number;
  containerHeight?: number;
  onChapterCollapse?: (id: string) => void;
  onLessonSelect?: (params: { id: string }) => void;
  onTryLessonSelect?: (params: { chapterId: string; lessonId: string }) => void;
  selectedLessonId?: string;
  hideCourseHeader?: boolean;
};

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
}: CourseCatalogListProps) => {
  const [trialNodePosition, setTrialNodePosition] = useState<TrialNodePosition>(
    TRAIL_NODE_POSITION.NORMAL,
  );
  const [trialNodePayload, setTrialNodePayload] = useState<unknown>(null);

  useEffect(() => {
    setTrialNodePayload(catalogs.find(c => !!c.bannerInfo)?.bannerInfo || null);
  }, [catalogs]);

  const onNodePositionChange = (position: TrialNodePosition) => {
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
                {Boolean(catalog.bannerInfo) && (
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
        />
      )}
    </>
  );
};

export default memo(CourseCatalogList);

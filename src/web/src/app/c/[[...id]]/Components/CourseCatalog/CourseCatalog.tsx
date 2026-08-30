import { memo, useContext, useCallback } from 'react';
import type { LessonTreeLesson } from '../../hooks/useLessonTree';

import { AppContext } from '../AppContext';
import CourseSection from './CourseSection';
import styles from './CourseCatalog.module.scss';

import { cn } from '@/lib/utils';

import { ChevronDownIcon, ChevronUpIcon } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

type CourseCatalogProps = {
  id?: string;
  name?: string;
  status?: string;
  lessons?: LessonTreeLesson[];
  collapse?: boolean;
  selectedLessonId?: string;
  onCollapse?: (id: string) => void;
  onLessonSelect?: (params: { id: string }) => void;
  onTrySelect?: (params: { chapterId: string; lessonId: string }) => void;
};

export const CourseCatalog = ({
  id = '',
  name = '',
  lessons = [],
  collapse = false,
  selectedLessonId = '',
  onCollapse,
  onLessonSelect = () => {},
  onTrySelect,
}: CourseCatalogProps) => {
  const _onTrySelect = useCallback(
    ({ id: lessonId }: { id: string }) => {
      onTrySelect?.({ chapterId: id, lessonId });
    },
    [id, onTrySelect],
  );

  const onTitleRowClick = useCallback(() => {
    onCollapse?.(id);
  }, [id, onCollapse]);

  const { mobileStyle } = useContext(AppContext);
  return (
    <div
      className={cn(
        styles.courseCatalog,
        collapse && styles.collapse,
        mobileStyle && styles.mobile,
      )}
    >
      <div
        className={styles.titleRow}
        onClick={onTitleRowClick}
      >
        <div className={styles.leftSection}>
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className={styles.leftSectionText}>{name}</span>
              </TooltipTrigger>
              <TooltipContent
                side='top'
                className='max-w-[260px] whitespace-pre-wrap break-words'
              >
                {name}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <div className={styles.rightSection}>
          {collapse ? (
            <ChevronDownIcon className={styles.collapseBtn} />
          ) : (
            <ChevronUpIcon className={styles.collapseBtn} />
          )}
        </div>
      </div>
      <div className={styles.sectionList}>
        {lessons.map(e => {
          return (
            <CourseSection
              key={e.id}
              id={e.id}
              name={e.name}
              status_value={e.status_value}
              selected={e.id === selectedLessonId}
              type={e.type}
              is_paid={e.is_paid}
              canLearning={e.canLearning}
              chapterId={id}
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

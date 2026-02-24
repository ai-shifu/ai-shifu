import { memo, useContext, useCallback } from 'react';

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

export const CourseCatalog = ({
  id = 0,
  name = '',
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
              type={e.type}
              // @ts-expect-error EXPECT
              is_paid={e.is_paid}
              // @ts-expect-error EXPECT
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

'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { TooltipProvider } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { buildAdminOperationsCourseDetailUrl } from '../../operation-course-routes';
import type { AdminOperationUserCourseItem } from '../../operation-user-types';

const DEFAULT_VISIBLE_COURSE_COUNT = 10;

type UserCoursesTabProps = {
  title: string;
  courses: AdminOperationUserCourseItem[];
  emptyText: string;
  courseNameLabel: string;
  courseIdLabel: string;
  valueLabel: string;
  emptyValue: string;
  renderValue: (course: AdminOperationUserCourseItem) => string;
  courseNameAlign?: 'left' | 'center';
};

export default function UserCoursesTab({
  title,
  courses,
  emptyText,
  courseNameLabel,
  courseIdLabel,
  valueLabel,
  emptyValue,
  renderValue,
  courseNameAlign = 'center',
}: UserCoursesTabProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const shouldShowToggle = courses.length > DEFAULT_VISIBLE_COURSE_COUNT;
  const visibleCourses = expanded
    ? courses
    : courses.slice(0, DEFAULT_VISIBLE_COURSE_COUNT);
  const toggleLabel = `${expanded ? t('common.core.collapse') : t('common.core.expand')} ${title}`;

  useEffect(() => {
    if (!shouldShowToggle && expanded) {
      setExpanded(false);
    }
  }, [expanded, shouldShowToggle]);

  useEffect(() => {
    setExpanded(false);
  }, [courses, title]);

  return (
    <Card className='shadow-sm'>
      <CardContent className='space-y-3 pt-6'>
        <TooltipProvider delayDuration={150}>
          <Table className='table-fixed'>
            <colgroup>
              <col className='w-[38%]' />
              <col className='w-[42%]' />
              <col className='w-[20%]' />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead
                  className={cn(
                    courseNameAlign === 'left' ? 'text-left' : 'text-center',
                  )}
                >
                  {courseNameLabel}
                </TableHead>
                <TableHead className='text-center'>{courseIdLabel}</TableHead>
                <TableHead className='text-center'>{valueLabel}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {courses.length ? (
                visibleCourses.map(course => {
                  const courseDetailUrl = buildAdminOperationsCourseDetailUrl(
                    course.shifu_bid,
                  );

                  return (
                    <TableRow key={`${title}-${course.shifu_bid}`}>
                      <TableCell
                        className={cn(
                          'max-w-0 overflow-hidden text-ellipsis whitespace-nowrap',
                          courseNameAlign === 'left'
                            ? 'text-left'
                            : 'text-center',
                        )}
                      >
                        {courseDetailUrl ? (
                          <Link
                            href={courseDetailUrl}
                            className={cn(
                              'inline-block max-w-full text-primary transition-colors hover:text-primary/80 hover:underline',
                              courseNameAlign === 'left' && 'align-top',
                            )}
                          >
                            <AdminTooltipText
                              text={course.course_name}
                              emptyValue={emptyValue}
                            />
                          </Link>
                        ) : (
                          <AdminTooltipText
                            text={course.course_name}
                            emptyValue={emptyValue}
                          />
                        )}
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={course.shifu_bid}
                          emptyValue={emptyValue}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={renderValue(course)}
                          emptyValue={emptyValue}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })
              ) : (
                <TableEmpty colSpan={3}>{emptyText}</TableEmpty>
              )}
            </TableBody>
          </Table>
        </TooltipProvider>

        {shouldShowToggle ? (
          <div className='flex justify-end'>
            <Button
              type='button'
              variant='link'
              size='sm'
              className='h-auto px-0 py-0 text-sm'
              aria-label={toggleLabel}
              title={toggleLabel}
              onClick={() => setExpanded(previous => !previous)}
            >
              {expanded ? t('common.core.collapse') : t('common.core.expand')}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

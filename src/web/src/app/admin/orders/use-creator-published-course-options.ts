'use client';

import { useEffect, useMemo, useState } from 'react';
import api from '@/api';
import type { Shifu } from '@/types/shifu';

const MAX_COURSE_PAGES = 50;

type TranslationFn = (key: string, options?: Record<string, unknown>) => string;

export const useCreatorPublishedCourseOptions = ({
  open,
  t,
}: {
  open: boolean;
  t: TranslationFn;
}) => {
  const [courses, setCourses] = useState<Shifu[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [coursesError, setCoursesError] = useState('');
  const [coursesWarning, setCoursesWarning] = useState('');

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    let canceled = false;
    const loadCourses = async () => {
      setCoursesLoading(true);
      setCoursesError(current => (current ? '' : current));
      setCoursesWarning(current => (current ? '' : current));
      try {
        const pageSize = 100;
        let pageIndex = 1;
        let reachedLimit = false;
        const collected: Shifu[] = [];
        const seen = new Set<string>();

        while (!canceled && pageIndex <= MAX_COURSE_PAGES) {
          const response = (await api.getAdminOrderShifus({
            page_index: pageIndex,
            page_size: pageSize,
            published: true,
          })) as { items?: Shifu[] };
          const pageItems = response.items || [];
          pageItems.forEach(course => {
            if (course?.bid && !seen.has(course.bid)) {
              seen.add(course.bid);
              collected.push(course);
            }
          });
          if (pageItems.length < pageSize) {
            break;
          }
          pageIndex += 1;
        }
        if (pageIndex > MAX_COURSE_PAGES) {
          reachedLimit = true;
        }

        if (!canceled) {
          setCourses(collected);
          if (reachedLimit) {
            setCoursesWarning(t('module.order.redemptionCodes.tooManyCourses'));
          }
        }
      } catch (error) {
        if (!canceled) {
          setCourses([]);
          setCoursesError(
            (error as Error).message ||
              t('module.order.redemptionCodes.loadCoursesFailed'),
          );
        }
      } finally {
        if (!canceled) {
          setCoursesLoading(false);
        }
      }
    };

    void loadCourses();
    return () => {
      canceled = true;
    };
  }, [open, t]);

  const courseOptions = useMemo(
    () => courses.filter(course => Boolean(String(course.bid || '').trim())),
    [courses],
  );

  return {
    courseOptions,
    coursesError,
    coursesLoading,
    coursesWarning,
  };
};

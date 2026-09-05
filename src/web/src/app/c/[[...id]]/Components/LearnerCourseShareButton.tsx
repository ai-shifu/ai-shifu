'use client';

import { useCallback } from 'react';
import { useParams } from 'next/navigation';
import { useShallow } from 'zustand/react/shallow';

import { useEnvStore } from '@/store/envStore';
import { useCourseStore } from '@/store/useCourseStore';
import { useSystemStore } from '@/store/useSystemStore';
import { buildCoursePageUrl } from '@/lib/urlUtils';
import {
  CourseShareButton,
  type CourseShareButtonProps,
  type CourseShareSurface,
} from '@/components/course-share';

type LearnerCourseShareSurface = Exclude<CourseShareSurface, 'teacher_header'>;

export type LearnerCourseShareButtonProps = Pick<
  CourseShareButtonProps,
  'showLabel' | 'variant' | 'size' | 'className' | 'tooltipSide'
> & {
  surface: LearnerCourseShareSurface;
};

export default function LearnerCourseShareButton({
  surface,
  showLabel,
  variant,
  size,
  className,
  tooltipSide,
}: LearnerCourseShareButtonProps) {
  const routeParams = useParams();
  const routeCourseId = Array.isArray(routeParams?.id) ? routeParams.id[0] : '';
  const shifuBid = useEnvStore(state => state.courseId);
  const previewMode = useSystemStore(state => state.previewMode);
  const { courseName, courseDescription, courseSettingsCourseId } =
    useCourseStore(
      useShallow(state => ({
        courseName: state.courseName,
        courseDescription: state.courseDescription,
        courseSettingsCourseId: state.courseSettingsCourseId,
      })),
    );
  const resolveShareUrl = useCallback(() => {
    if (typeof window === 'undefined') {
      return null;
    }

    return buildCoursePageUrl(window.location.href) || null;
  }, []);

  if (
    previewMode ||
    !routeCourseId ||
    routeCourseId !== shifuBid ||
    courseSettingsCourseId !== routeCourseId
  ) {
    return null;
  }

  return (
    <CourseShareButton
      courseTitle={courseName}
      courseDescription={courseDescription}
      shifuBid={shifuBid}
      resolveShareUrl={resolveShareUrl}
      surface={surface}
      showLabel={showLabel}
      variant={variant}
      size={size}
      className={className}
      tooltipSide={tooltipSide}
    />
  );
}

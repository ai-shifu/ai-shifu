import { useEffect, useRef } from 'react';
import { useTracking } from '@/c-common/hooks/useTracking';

export const COURSE_VISITOR_METRIC_SHOWN_EVENT =
  'operator_course_visitor_metric_shown';

type CourseVisitMetricExposureParams = {
  isOperatorReady: boolean;
  routeCourseId: string;
  loadedCourseId: string;
};

const normalizeCourseId = (value: string) => String(value || '').trim();

export const resolveCourseVisitMetricExposure = ({
  isOperatorReady,
  routeCourseId,
  loadedCourseId,
}: CourseVisitMetricExposureParams) => {
  const normalizedRouteCourseId = normalizeCourseId(routeCourseId);
  const normalizedLoadedCourseId = normalizeCourseId(loadedCourseId);

  if (
    !isOperatorReady ||
    !normalizedRouteCourseId ||
    normalizedLoadedCourseId !== normalizedRouteCourseId
  ) {
    return null;
  }

  return normalizedRouteCourseId;
};

export const useCourseVisitMetricExposure = (
  params: CourseVisitMetricExposureParams,
) => {
  const { trackEvent } = useTracking();
  const lastObservedRouteIdRef = useRef('');
  const routeVisitSequenceRef = useRef(0);
  const trackedRouteVisitSequenceRef = useRef(-1);
  const courseId = resolveCourseVisitMetricExposure(params);

  useEffect(() => {
    const normalizedRouteCourseId = normalizeCourseId(params.routeCourseId);
    if (lastObservedRouteIdRef.current !== normalizedRouteCourseId) {
      lastObservedRouteIdRef.current = normalizedRouteCourseId;
      routeVisitSequenceRef.current += 1;
    }

    if (
      !courseId ||
      trackedRouteVisitSequenceRef.current === routeVisitSequenceRef.current
    ) {
      return;
    }

    trackedRouteVisitSequenceRef.current = routeVisitSequenceRef.current;
    try {
      void Promise.resolve(
        trackEvent(COURSE_VISITOR_METRIC_SHOWN_EVENT, {
          shifu_bid: courseId,
        }),
      ).catch(() => undefined);
    } catch {
      // Product analytics must never change the operator page result.
    }
  }, [courseId, params.routeCourseId, trackEvent]);
};

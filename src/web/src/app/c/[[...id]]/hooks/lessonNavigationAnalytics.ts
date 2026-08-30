export const LESSON_NAVIGATION_EVENT = 'nav_section_switch';

type LessonNavigationAnalyticsInput = {
  shifuBid?: string | null;
  fromLessonId?: string | null;
  toLessonId?: string | null;
};

type LessonNavigationEligibilityInput = {
  previewMode: boolean;
  fromLessonId?: string | null;
  toLessonId?: string | null;
};

export const shouldTrackLessonNavigation = ({
  previewMode,
  fromLessonId,
  toLessonId,
}: LessonNavigationEligibilityInput) =>
  !previewMode &&
  Boolean(fromLessonId) &&
  Boolean(toLessonId) &&
  fromLessonId !== toLessonId;

export const buildLessonNavigationAnalytics = ({
  shifuBid,
  fromLessonId,
  toLessonId,
}: LessonNavigationAnalyticsInput) => ({
  shifu_bid: shifuBid || '',
  from_lesson_id: fromLessonId || '',
  to_lesson_id: toLessonId || '',
});

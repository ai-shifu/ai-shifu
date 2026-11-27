export const OUTLINE_CREATE_EVENT = 'creator_outline_create';

type OutlineCreateAnalyticsInput = {
  shifuBid?: string | null;
  outlineBid?: string | null;
  parentBid?: string | null;
};

export const buildOutlineCreateAnalytics = ({
  shifuBid,
  outlineBid,
  parentBid,
}: OutlineCreateAnalyticsInput) => ({
  shifu_bid: shifuBid || '',
  outline_bid: outlineBid || '',
  parent_bid: parentBid || '',
});

export const COURSE_REMOTE_CHANGE_APPLIED_EVENT =
  'creator_course_remote_change_applied';

type CourseRemoteChangeAnalyticsInput = {
  shifuBid: string;
  courseSettingsChanged: boolean;
  outlineChanged: boolean;
  selectionCleared: boolean;
};

// Contract: docs/references/frontend-product-analytics.md, "Course editor
// remote change sync". Keep this an explicit allowlist.
export const buildCourseRemoteChangeAnalytics = ({
  shifuBid,
  courseSettingsChanged,
  outlineChanged,
  selectionCleared,
}: CourseRemoteChangeAnalyticsInput) => ({
  shifu_bid: shifuBid,
  course_settings_changed: courseSettingsChanged,
  outline_changed: outlineChanged,
  selection_cleared: selectionCleared,
});

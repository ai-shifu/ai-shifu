export const COURSE_CREATION_EVENTS = {
  ATTEMPT: 'creator_course_create_attempt',
  RESULT: 'creator_course_create_result',
  CANCEL: 'creator_course_create_cancel',
} as const;

export type CourseCreationPath = 'manual' | 'ai_assistant';
export type CourseCreationFailureCategory = 'request_failed';

export const buildCourseCreationAttemptAnalytics = (
  creationPath: CourseCreationPath,
) => ({
  creation_path: creationPath,
});

export const buildCourseCreationResultAnalytics = ({
  creationPath,
  outcome,
  shifuBid,
  failureCategory,
}: {
  creationPath: CourseCreationPath;
  outcome: 'success' | 'failed';
  shifuBid?: string;
  failureCategory?: CourseCreationFailureCategory;
}) => ({
  creation_path: creationPath,
  outcome,
  ...(outcome === 'success' && shifuBid ? { shifu_bid: shifuBid } : {}),
  ...(outcome === 'failed' && failureCategory
    ? { failure_category: failureCategory }
    : {}),
});

export const buildCourseCreationCancelAnalytics = (
  creationPath: CourseCreationPath,
) => ({
  creation_path: creationPath,
});

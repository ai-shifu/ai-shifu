export const COURSE_CREATION_EVENTS = {
  AI_ENTRY_IMPRESSION: 'creator_ai_course_entry_impression',
  AI_ENTRY_CLICK: 'creator_ai_course_entry_click',
  AI_PROMPT_COPY_ATTEMPT: 'creator_ai_course_prompt_copy_attempt',
  AI_PROMPT_COPY_RESULT: 'creator_ai_course_prompt_copy_result',
  ATTEMPT: 'creator_course_create_attempt',
  RESULT: 'creator_course_create_result',
  CANCEL: 'creator_course_create_cancel',
} as const;

export const AI_COURSE_ENTRY_ANALYTICS = {
  surface: 'admin_course_list',
  presentation: 'creation_choice_modal',
} as const;

export const buildAiCourseEntryAnalytics = () => ({
  ...AI_COURSE_ENTRY_ANALYTICS,
});

export const buildAiCoursePromptCopyResultAnalytics = (
  outcome: 'success' | 'failed',
) => ({
  ...AI_COURSE_ENTRY_ANALYTICS,
  outcome,
});

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

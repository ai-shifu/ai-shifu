import { LESSON_FEEDBACK_INTERACTION_MARKER } from '@/c-api/studyV2';

export const isLessonFeedbackInteractionContent = (
  content?: string | null,
) => Boolean(content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER));

import { LESSON_FEEDBACK_INTERACTION_MARKER } from '@/api/learning';

export const isLessonFeedbackInteractionContent = (content?: string | null) =>
  Boolean(content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER));

import { LESSON_FEEDBACK_INTERACTION_MARKER } from '@/c-api/studyV2';
import { parseLessonFeedbackUserInput } from '@/c-utils/interaction-user-input';
import type { InteractionDefaultValueOptions } from 'markdown-flow-ui/renderer';

export const lessonFeedbackInteractionDefaultValueOptions: InteractionDefaultValueOptions =
  {
    resolveDefaultValues: ({ content, rawValue }) => {
      if (
        !content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER) ||
        !rawValue?.trim()
      ) {
        return null;
      }

      const parsed = parseLessonFeedbackUserInput(rawValue);

      return {
        buttonText: parsed.scoreText || undefined,
        inputText: parsed.commentText || undefined,
      };
    },
  };

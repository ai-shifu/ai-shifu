import { isLessonFeedbackInteractionContent } from '@/lib/lesson-feedback-interaction';
import { parseLessonFeedbackUserInput } from '@/lib/interaction-user-input';
import type { InteractionDefaultValueOptions } from 'markdown-flow-ui/renderer';

export const lessonFeedbackInteractionDefaultValueOptions: InteractionDefaultValueOptions =
  {
    resolveDefaultValues: ({ content, rawValue }) => {
      if (!isLessonFeedbackInteractionContent(content) || !rawValue?.trim()) {
        return null;
      }

      const parsed = parseLessonFeedbackUserInput(rawValue);

      return {
        buttonText: parsed.scoreText || undefined,
        inputText: parsed.commentText || undefined,
      };
    },
  };

import type { OnSendContentParams } from 'markdown-flow-ui/renderer';

export interface ResolvedInteractionSubmission {
  values: string[];
  userInput: string;
}

export const resolveInteractionSubmission = (
  content: OnSendContentParams,
): ResolvedInteractionSubmission => {
  const values = [
    ...(content.selectedValues ?? []),
    content.inputText?.trim() ?? '',
    content.buttonText?.trim() ?? '',
  ].filter(Boolean);

  return {
    values,
    userInput: values.join(', '),
  };
};

export const buildLessonFeedbackUserInput = (
  scoreText?: string | number | null,
  commentText?: string | null,
) => {
  const normalizedScore = `${scoreText ?? ''}`.trim();
  const normalizedComment = commentText?.trim() ?? '';

  if (!normalizedScore && !normalizedComment) {
    return '';
  }

  return JSON.stringify({
    score: normalizedScore,
    comment: normalizedComment,
  });
};

export const parseLessonFeedbackUserInput = (raw?: string | null) => {
  if (!raw) {
    return {
      scoreText: '',
      commentText: '',
    };
  }

  try {
    const parsed = JSON.parse(raw) as {
      score?: string | number;
      comment?: unknown;
    };

    return {
      scoreText: `${parsed?.score ?? ''}`.trim(),
      commentText: typeof parsed?.comment === 'string' ? parsed.comment : '',
    };
  } catch {
    return {
      scoreText: `${raw}`.trim(),
      commentText: '',
    };
  }
};

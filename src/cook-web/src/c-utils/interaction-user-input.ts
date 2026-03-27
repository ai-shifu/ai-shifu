import type { OnSendContentParams } from 'markdown-flow-ui/renderer';

export interface ResolvedInteractionSubmission {
  values: string[];
  userInput: string;
}

const getUniqueSubmissionValues = (
  content: OnSendContentParams,
): string[] => {
  const rawValues = [
    ...(content.selectedValues ?? []),
    content.inputText ?? '',
    content.buttonText ?? '',
  ];

  const uniqueValues: string[] = [];
  const valueSet = new Set<string>();
  rawValues.forEach(rawValue => {
    const normalizedValue = `${rawValue ?? ''}`.trim();
    if (!normalizedValue || valueSet.has(normalizedValue)) {
      return;
    }
    valueSet.add(normalizedValue);
    uniqueValues.push(normalizedValue);
  });

  return uniqueValues;
};

export const resolveInteractionSubmission = (
  content: OnSendContentParams,
): ResolvedInteractionSubmission => {
  const values = getUniqueSubmissionValues(content);

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

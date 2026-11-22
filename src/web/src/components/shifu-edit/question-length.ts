import { extractVariableNames } from 'remark-flow';
import { QUESTION_NAME_MAX_LENGTH } from '@/constants/ui-constants';

export const QUESTION_PREVIEW_LENGTH = 20;

export type OverlongQuestion = {
  name: string;
  length: number;
};

/** Count Unicode code points so the limit matches the backend's len(). */
export const countQuestionLength = (name: string): number =>
  Array.from(name).length;

/** Truncate by code points so a preview never splits a surrogate pair. */
export const previewQuestion = (name: string): string =>
  Array.from(name).slice(0, QUESTION_PREVIEW_LENGTH).join('');

/** Return every distinct {{ }} question longer than the publish limit. */
export const findOverlongQuestions = (
  content: string,
  maxLength: number = QUESTION_NAME_MAX_LENGTH,
): OverlongQuestion[] =>
  extractVariableNames(content || '')
    .map(name => ({ name, length: countQuestionLength(name) }))
    .filter(question => question.length > maxLength);

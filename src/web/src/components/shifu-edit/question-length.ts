import { extractVariableNames } from 'remark-flow';
import { QUESTION_NAME_MAX_LENGTH } from '@/constants/ui-constants';

export const QUESTION_PREVIEW_LENGTH = 20;

export type OverlongQuestion = {
  name: string;
  length: number;
};

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})/;
const HTML_COMMENT = /<!--[\s\S]*?-->/g;

/** Count Unicode code points so the limit matches the backend's len(). */
export const countQuestionLength = (name: string): number =>
  Array.from(name).length;

/** Truncate by code points so a preview never splits a surrogate pair. */
export const previewQuestion = (name: string): string =>
  Array.from(name).slice(0, QUESTION_PREVIEW_LENGTH).join('');

/**
 * Drop fenced code blocks and HTML comments, which the backend document
 * preprocessor removes before publish validation. This is a close
 * approximation of that preprocessor, not a full CommonMark parser.
 */
export const stripLiteralRegions = (content: string): string => {
  const kept: string[] = [];
  let fence: { char: string; length: number } | null = null;
  for (const line of content.split('\n')) {
    if (fence) {
      const close = line.match(/^ {0,3}(`{3,}|~{3,})\s*$/);
      if (
        close &&
        close[1][0] === fence.char &&
        close[1].length >= fence.length
      ) {
        fence = null;
      }
      kept.push('');
      continue;
    }
    const open = line.match(FENCE_OPEN);
    if (open) {
      fence = { char: open[1][0], length: open[1].length };
      kept.push('');
      continue;
    }
    kept.push(line);
  }
  return kept.join('\n').replace(HTML_COMMENT, '');
};

/** Return every distinct {{ }} question longer than the publish limit. */
export const findOverlongQuestions = (
  content: string,
  maxLength: number = QUESTION_NAME_MAX_LENGTH,
): OverlongQuestion[] =>
  extractVariableNames(stripLiteralRegions(content || ''))
    .map(name => ({ name, length: countQuestionLength(name) }))
    .filter(question => question.length > maxLength);

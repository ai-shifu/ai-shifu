import { findDocumentVariableMarkers } from 'remark-flow';
import { QUESTION_NAME_MAX_LENGTH } from '@/constants/ui-constants';

export const QUESTION_PREVIEW_LENGTH = 20;

export type OverlongQuestion = {
  name: string;
  length: number;
};

type Range = { start: number; end: number };
type Marker = { start: number; end: number; name: string | null };

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})/;
const FENCE_CLOSE = /^ {0,3}(`{3,}|~{3,})\s*$/;
const COMMENT_OPEN = '<!--';
const COMMENT_CLOSE = '-->';

/** Count Unicode code points so the limit matches the backend's len(). */
export const countQuestionLength = (name: string): number =>
  Array.from(name).length;

/** Truncate by code points so a preview never splits a surrogate pair. */
export const previewQuestion = (name: string): string =>
  Array.from(name).slice(0, QUESTION_PREVIEW_LENGTH).join('');

const isInside = (at: number, ranges: Range[]): boolean =>
  ranges.some(range => at >= range.start && at < range.end);

/** Find the next index of `token`, skipping over whole {{ }} markers. */
const indexOutsideMarkers = (
  content: string,
  token: string,
  from: number,
  markers: Marker[],
): number => {
  let at = content.indexOf(token, from);
  while (at >= 0) {
    const covering = markers.find(
      marker => at >= marker.start && at < marker.end,
    );
    if (!covering) {
      return at;
    }
    at = content.indexOf(token, covering.end);
  }
  return -1;
};

/**
 * Locate fenced code blocks and HTML comments in one source-order pass, the
 * way the backend preprocessor does: a fence cannot open inside a comment,
 * a comment cannot open inside a fence, and complete {{ }} markers are
 * protected so comment syntax inside a question neither opens nor closes one.
 */
const findLiteralRanges = (content: string, markers: Marker[]): Range[] => {
  const ranges: Range[] = [];
  let fence: { char: string; length: number; start: number } | null = null;
  let commentStart = -1;
  let offset = 0;
  const findInLine = (token: string, from: number, lineEnd: number) => {
    const at = indexOutsideMarkers(content, token, from, markers);
    return at >= 0 && at + token.length <= lineEnd ? at : -1;
  };
  for (const line of content.split('\n')) {
    const lineEnd = offset + line.length;
    if (fence) {
      const close = line.match(FENCE_CLOSE);
      if (
        close &&
        close[1][0] === fence.char &&
        close[1].length >= fence.length
      ) {
        ranges.push({ start: fence.start, end: lineEnd });
        fence = null;
      }
      offset = lineEnd + 1;
      continue;
    }
    if (commentStart < 0) {
      const open = line.match(FENCE_OPEN);
      if (open) {
        fence = { char: open[1][0], length: open[1].length, start: offset };
        offset = lineEnd + 1;
        continue;
      }
    }
    let at = offset;
    while (at < lineEnd) {
      if (commentStart >= 0) {
        const close = findInLine(COMMENT_CLOSE, at, lineEnd);
        if (close < 0) {
          break;
        }
        ranges.push({ start: commentStart, end: close + COMMENT_CLOSE.length });
        commentStart = -1;
        at = close + COMMENT_CLOSE.length;
      } else {
        const open = findInLine(COMMENT_OPEN, at, lineEnd);
        if (open < 0) {
          break;
        }
        commentStart = open;
        at = open + COMMENT_OPEN.length;
      }
    }
    offset = lineEnd + 1;
  }
  if (fence) {
    ranges.push({ start: fence.start, end: content.length });
  }
  return ranges;
};

/**
 * Return every distinct {{ }} question longer than the publish limit.
 * Questions inside fenced code blocks or HTML comments are skipped, since the
 * backend preprocessor removes those before publish validation. The fence
 * detection is a close, line-based approximation of that preprocessor.
 */
export const findOverlongQuestions = (
  content: string,
  maxLength: number = QUESTION_NAME_MAX_LENGTH,
): OverlongQuestion[] => {
  const text = content || '';
  const markers: Marker[] = findDocumentVariableMarkers(text);
  const literal = findLiteralRanges(text, markers);
  const seen = new Set<string>();
  const overlong: OverlongQuestion[] = [];
  for (const marker of markers) {
    const { name } = marker;
    if (!name || seen.has(name) || isInside(marker.start, literal)) {
      continue;
    }
    seen.add(name);
    const length = countQuestionLength(name);
    if (length > maxLength) {
      overlong.push({ name, length });
    }
  }
  return overlong;
};

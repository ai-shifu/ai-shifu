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

const findFencedRanges = (content: string): Range[] => {
  const ranges: Range[] = [];
  let fence: { char: string; length: number; start: number } | null = null;
  let offset = 0;
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
    } else {
      const open = line.match(FENCE_OPEN);
      if (open) {
        fence = { char: open[1][0], length: open[1].length, start: offset };
      }
    }
    offset = lineEnd + 1;
  }
  if (fence) {
    ranges.push({ start: fence.start, end: content.length });
  }
  return ranges;
};

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
 * Locate HTML comments the way the backend preprocessor does: complete
 * {{ }} markers are protected, so comment syntax inside a question name
 * neither opens nor closes a comment.
 */
const findCommentRanges = (
  content: string,
  markers: Marker[],
  fenced: Range[],
): Range[] => {
  const ranges: Range[] = [];
  let at = 0;
  while (at < content.length) {
    const open = indexOutsideMarkers(content, COMMENT_OPEN, at, markers);
    if (open < 0) {
      break;
    }
    if (isInside(open, fenced)) {
      at = open + COMMENT_OPEN.length;
      continue;
    }
    const close = indexOutsideMarkers(
      content,
      COMMENT_CLOSE,
      open + COMMENT_OPEN.length,
      markers,
    );
    if (close < 0) {
      break;
    }
    ranges.push({ start: open, end: close + COMMENT_CLOSE.length });
    at = close + COMMENT_CLOSE.length;
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
  const fenced = findFencedRanges(text);
  const literal = [...fenced, ...findCommentRanges(text, markers, fenced)];
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

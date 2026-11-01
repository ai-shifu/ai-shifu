/**
 * Display helpers shared by the course follow-up and rating pages on both
 * the teacher dashboard and the operator admin surfaces.
 */
import type { LoginIdentifierType } from '@/lib/login-identifiers';

export type CourseFeedbackErrorState = { message: string; code?: number };

export const formatDisplayValue = (
  value: string | undefined | null,
  emptyValue: string,
) => {
  const normalizedValue = value?.trim() || '';
  return normalizedValue || emptyValue;
};

/**
 * Resolves the account shown for a learner: the configured login identifier
 * first, then the other identifier, then the user id.
 */
export const resolvePrimaryAccount = ({
  mobile,
  email,
  userBid,
  displayIdentifierType,
  emptyValue,
}: {
  mobile?: string;
  email?: string;
  userBid?: string;
  displayIdentifierType: LoginIdentifierType;
  emptyValue: string;
}) => {
  const primaryIdentifier = displayIdentifierType === 'email' ? email : mobile;
  const alternateIdentifier =
    displayIdentifierType === 'email' ? mobile : email;
  return formatDisplayValue(
    primaryIdentifier || alternateIdentifier || userBid,
    emptyValue,
  );
};

export const resolvePrimaryLessonDisplay = ({
  lessonTitle,
  chapterTitle,
  emptyValue,
}: {
  lessonTitle?: string;
  chapterTitle?: string;
  emptyValue: string;
}) => formatDisplayValue(lessonTitle || chapterTitle, emptyValue);

/**
 * Returns the chapter title only when it adds information beyond the lesson
 * title; otherwise an empty string so callers can skip the secondary line.
 */
export const resolveSecondaryChapterDisplay = ({
  chapterTitle,
  lessonTitle,
}: {
  chapterTitle?: string;
  lessonTitle?: string;
}) => {
  const normalizedChapterTitle = chapterTitle?.trim() || '';
  const normalizedLessonTitle = lessonTitle?.trim() || '';
  if (
    !normalizedChapterTitle ||
    normalizedChapterTitle === normalizedLessonTitle
  ) {
    return '';
  }
  return normalizedChapterTitle;
};

export const hasDistinctChapterTitle = (item: {
  chapter_title?: string;
  lesson_title?: string;
}) => {
  const chapterTitle = item.chapter_title?.trim() || '';
  const lessonTitle = item.lesson_title?.trim() || '';
  return !!chapterTitle && !!lessonTitle && chapterTitle !== lessonTitle;
};

export const hasChapterHierarchy = (
  rows: Array<{ chapter_title?: string; lesson_title?: string }>,
) => rows.some(hasDistinctChapterTitle);

/**
 * Splits a formatted timestamp into date and time parts for two-line display.
 */
export const splitTimestampValue = (value: string) => {
  const normalizedValue = value
    .replace(/[,. ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!normalizedValue) {
    return [];
  }

  const [datePart, timePart, ...rest] = normalizedValue.split(' ');
  if (!timePart || rest.length > 0) {
    return [normalizedValue];
  }

  return [datePart, timePart];
};

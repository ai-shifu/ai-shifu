import type { LearningMode } from '@/c-types/store';

export const PUBLISH_LEARNING_MODES = [
  'read',
  'listen',
  'classroom',
] as const satisfies readonly LearningMode[];

export const isPublishLearningModeAvailable = ({
  mode,
  ttsEnabled,
}: {
  mode: LearningMode;
  ttsEnabled?: boolean | null;
}) => mode !== 'listen' || ttsEnabled !== false;

export const buildCourseLearningUrl = (
  courseId: string,
  publishedUrl?: string | null,
) => {
  const normalizedUrl = publishedUrl?.trim();
  if (normalizedUrl) {
    return normalizedUrl;
  }

  return `/c/${encodeURIComponent(courseId)}`;
};

const ABSOLUTE_URL_PATTERN = /^[a-zA-Z][a-zA-Z\d+\-.]*:/;

const getDefaultOrigin = () =>
  typeof window !== 'undefined' ? window.location.origin : 'http://localhost';

const buildCourseUrl = (
  courseUrl: string,
  {
    mode,
    origin = getDefaultOrigin(),
  }: {
    mode?: LearningMode;
    origin?: string;
  } = {},
) => {
  const normalizedUrl = courseUrl.trim();
  if (!normalizedUrl) {
    return '';
  }

  const url = new URL(normalizedUrl, origin);
  url.username = '';
  url.password = '';
  url.search = '';
  url.hash = '';

  if (mode) {
    url.searchParams.set('mode', mode);
    return url.toString();
  }

  if (ABSOLUTE_URL_PATTERN.test(normalizedUrl)) {
    return url.toString();
  }

  return url.pathname;
};

export const buildParameterlessCourseUrl = (
  courseUrl: string,
  origin?: string,
) => buildCourseUrl(courseUrl, { origin });

export const buildLearningModeUrl = (
  courseUrl: string,
  mode: LearningMode,
  origin?: string,
) => buildCourseUrl(courseUrl, { mode, origin });

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

export const buildLearningModeUrl = (
  courseUrl: string,
  mode: LearningMode,
  origin = typeof window !== 'undefined'
    ? window.location.origin
    : 'http://localhost',
) => {
  const url = new URL(courseUrl, origin);
  url.searchParams.set('mode', mode);
  url.searchParams.delete('listen');
  return url.toString();
};

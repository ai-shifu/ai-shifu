// Increment this schema version only when persisted checkpoint semantics become
// incompatible with prior releases.
const STORAGE_PREFIX = 'course_listen_playback_checkpoint:v1';
const MINIMUM_POSITION_MS = 2_000;

export type ListenPlaybackCheckpoint = {
  audioKey: string;
  timeMs: number;
};

type LessonScope = {
  courseId: string;
  lessonId: string;
};

const getStorageKey = ({ courseId, lessonId }: LessonScope) =>
  [STORAGE_PREFIX, courseId, lessonId]
    .map(value => encodeURIComponent(value))
    .join(':');

const canUseStorage = ({ courseId, lessonId }: LessonScope) =>
  typeof window !== 'undefined' && Boolean(courseId.trim() && lessonId.trim());

export const readListenPlaybackCheckpoint = (scope: LessonScope) => {
  if (!canUseStorage(scope)) {
    return null;
  }

  try {
    const rawValue = window.localStorage.getItem(getStorageKey(scope));
    const value = rawValue
      ? (JSON.parse(rawValue) as Partial<ListenPlaybackCheckpoint>)
      : null;
    if (
      !value ||
      typeof value.audioKey !== 'string' ||
      !value.audioKey ||
      typeof value.timeMs !== 'number' ||
      !Number.isFinite(value.timeMs) ||
      value.timeMs < MINIMUM_POSITION_MS
    ) {
      return null;
    }

    return { audioKey: value.audioKey, timeMs: value.timeMs };
  } catch {
    return null;
  }
};

export const writeListenPlaybackCheckpoint = (
  scope: LessonScope,
  checkpoint: ListenPlaybackCheckpoint,
) => {
  if (!canUseStorage(scope) || checkpoint.timeMs < MINIMUM_POSITION_MS) {
    return;
  }

  try {
    window.localStorage.setItem(
      getStorageKey(scope),
      JSON.stringify(checkpoint),
    );
  } catch {
    // Storage is intentionally best-effort.
  }
};

export const clearListenPlaybackCheckpoint = (scope: LessonScope) => {
  if (!canUseStorage(scope)) {
    return;
  }

  try {
    window.localStorage.removeItem(getStorageKey(scope));
  } catch {
    // Storage is intentionally best-effort.
  }
};

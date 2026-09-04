const LISTEN_PLAYBACK_POSITION_STORAGE_PREFIX =
  'course_listen_playback_position:v1';
const LISTEN_LESSON_PLAYBACK_STORAGE_PREFIX =
  'course_listen_playback_lesson:v1';

const MINIMUM_RESUMABLE_POSITION_SECONDS = 2;

export type ListenPlaybackPositionScope = {
  courseId: string;
  lessonId: string;
  elementBid: string;
  source: string;
};

type StoredListenPlaybackPosition = {
  positionSeconds: number;
  source: string;
};

export type ListenLessonPlaybackTarget = Pick<
  ListenPlaybackPositionScope,
  'elementBid' | 'source'
>;

const isBrowser = () => typeof window !== 'undefined';

const isValidScope = (scope: ListenPlaybackPositionScope) =>
  Boolean(
    scope.courseId.trim() &&
    scope.lessonId.trim() &&
    scope.elementBid.trim() &&
    scope.source.trim(),
  );

const getListenPlaybackPositionStorageKey = (
  scope: ListenPlaybackPositionScope,
) =>
  [
    LISTEN_PLAYBACK_POSITION_STORAGE_PREFIX,
    scope.courseId,
    scope.lessonId,
    scope.elementBid,
  ]
    .map(value => encodeURIComponent(value))
    .join(':');

const getListenLessonPlaybackStorageKey = (
  scope: Pick<ListenPlaybackPositionScope, 'courseId' | 'lessonId'>,
) =>
  [LISTEN_LESSON_PLAYBACK_STORAGE_PREFIX, scope.courseId, scope.lessonId]
    .map(value => encodeURIComponent(value))
    .join(':');

const clearLessonPlaybackTargetIfMatching = (
  scope: ListenPlaybackPositionScope,
) => {
  const lessonStorageKey = getListenLessonPlaybackStorageKey(scope);
  try {
    const storedValue = window.localStorage.getItem(lessonStorageKey);
    const storedTarget = storedValue
      ? (JSON.parse(storedValue) as Partial<ListenLessonPlaybackTarget>)
      : null;
    if (
      storedTarget?.elementBid === scope.elementBid &&
      storedTarget.source === scope.source
    ) {
      window.localStorage.removeItem(lessonStorageKey);
    }
  } catch {
    // Storage access and malformed legacy values are best-effort.
  }
};

export const normalizeListenPlaybackSource = (source: string) => {
  const normalizedSource = source.trim();
  if (!normalizedSource) {
    return '';
  }

  try {
    const parsedSource = new URL(
      normalizedSource,
      isBrowser() ? window.location.origin : 'https://listen.invalid',
    );
    return `${parsedSource.origin}${parsedSource.pathname}`;
  } catch {
    return normalizedSource.split(/[?#]/, 1)[0] ?? '';
  }
};

export const isResumableListenPlaybackPosition = ({
  positionSeconds,
  durationSeconds,
}: {
  positionSeconds: number;
  durationSeconds: number;
}) =>
  Number.isFinite(positionSeconds) &&
  Number.isFinite(durationSeconds) &&
  durationSeconds > MINIMUM_RESUMABLE_POSITION_SECONDS * 2 &&
  positionSeconds >= MINIMUM_RESUMABLE_POSITION_SECONDS &&
  positionSeconds <= durationSeconds - MINIMUM_RESUMABLE_POSITION_SECONDS;

export const readListenPlaybackPositionFromStorage = (
  scope: ListenPlaybackPositionScope,
) => {
  if (!isBrowser() || !isValidScope(scope)) {
    return null;
  }

  const storageKey = getListenPlaybackPositionStorageKey(scope);
  let storedValue: string | null;
  try {
    storedValue = window.localStorage.getItem(storageKey);
  } catch {
    // localStorage can be unavailable in private mode or embedded contexts.
    return null;
  }

  if (!storedValue) {
    return null;
  }

  try {
    const parsedValue = JSON.parse(
      storedValue,
    ) as Partial<StoredListenPlaybackPosition> | null;
    const positionSeconds = parsedValue?.positionSeconds;
    if (
      !parsedValue ||
      parsedValue.source !== scope.source ||
      typeof positionSeconds !== 'number' ||
      !Number.isFinite(positionSeconds) ||
      positionSeconds < MINIMUM_RESUMABLE_POSITION_SECONDS
    ) {
      window.localStorage.removeItem(storageKey);
      return null;
    }

    return positionSeconds;
  } catch {
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      // localStorage can be unavailable in private mode or embedded contexts.
    }
    return null;
  }
};

export const readListenLessonPlaybackTargetFromStorage = ({
  courseId,
  lessonId,
}: Pick<ListenPlaybackPositionScope, 'courseId' | 'lessonId'>) => {
  if (!isBrowser() || !courseId.trim() || !lessonId.trim()) {
    return null;
  }

  const storageKey = getListenLessonPlaybackStorageKey({ courseId, lessonId });
  try {
    const storedValue = window.localStorage.getItem(storageKey);
    const parsedValue = storedValue
      ? (JSON.parse(storedValue) as Partial<ListenLessonPlaybackTarget>)
      : null;
    if (
      !parsedValue ||
      typeof parsedValue.elementBid !== 'string' ||
      !parsedValue.elementBid.trim() ||
      typeof parsedValue.source !== 'string' ||
      !parsedValue.source.trim()
    ) {
      window.localStorage.removeItem(storageKey);
      return null;
    }

    return {
      elementBid: parsedValue.elementBid,
      source: parsedValue.source,
    } satisfies ListenLessonPlaybackTarget;
  } catch {
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      // localStorage can be unavailable in private mode or embedded contexts.
    }
    return null;
  }
};

export const writeListenPlaybackPositionToStorage = ({
  scope,
  positionSeconds,
  durationSeconds,
}: {
  scope: ListenPlaybackPositionScope;
  positionSeconds: number;
  durationSeconds: number;
}) => {
  if (!isBrowser() || !isValidScope(scope)) {
    return;
  }

  const storageKey = getListenPlaybackPositionStorageKey(scope);
  try {
    if (
      !isResumableListenPlaybackPosition({ positionSeconds, durationSeconds })
    ) {
      window.localStorage.removeItem(storageKey);
      clearLessonPlaybackTargetIfMatching(scope);
      return;
    }

    window.localStorage.setItem(
      storageKey,
      JSON.stringify({
        positionSeconds,
        source: scope.source,
      } satisfies StoredListenPlaybackPosition),
    );
    window.localStorage.setItem(
      getListenLessonPlaybackStorageKey(scope),
      JSON.stringify({
        elementBid: scope.elementBid,
        source: scope.source,
      } satisfies ListenLessonPlaybackTarget),
    );
  } catch {
    // localStorage can be unavailable in private mode or embedded contexts.
  }
};

export const clearListenPlaybackPositionFromStorage = (
  scope: ListenPlaybackPositionScope,
) => {
  if (!isBrowser() || !isValidScope(scope)) {
    return;
  }

  try {
    window.localStorage.removeItem(getListenPlaybackPositionStorageKey(scope));
    clearLessonPlaybackTargetIfMatching(scope);
  } catch {
    // localStorage can be unavailable in private mode or embedded contexts.
  }
};

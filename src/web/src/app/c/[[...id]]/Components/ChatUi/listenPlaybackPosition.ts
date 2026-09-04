const LISTEN_PLAYBACK_POSITION_STORAGE_PREFIX =
  'course_listen_playback_position:v1';

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
  try {
    const storedValue = window.localStorage.getItem(storageKey);
    if (!storedValue) {
      return null;
    }

    const parsedValue = JSON.parse(storedValue) as StoredListenPlaybackPosition;
    if (
      parsedValue.source !== scope.source ||
      !Number.isFinite(parsedValue.positionSeconds) ||
      parsedValue.positionSeconds < MINIMUM_RESUMABLE_POSITION_SECONDS
    ) {
      window.localStorage.removeItem(storageKey);
      return null;
    }

    return parsedValue.positionSeconds;
  } catch {
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
      return;
    }

    window.localStorage.setItem(
      storageKey,
      JSON.stringify({
        positionSeconds,
        source: scope.source,
      } satisfies StoredListenPlaybackPosition),
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
  } catch {
    // localStorage can be unavailable in private mode or embedded contexts.
  }
};

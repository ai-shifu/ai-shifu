export const LISTEN_PLAYBACK_SPEED_OPTIONS = [0.75, 1, 1.25, 1.5, 2] as const;

export type ListenPlaybackSpeed =
  (typeof LISTEN_PLAYBACK_SPEED_OPTIONS)[number];

export const DEFAULT_LISTEN_PLAYBACK_SPEED: ListenPlaybackSpeed = 1;

const LISTEN_PLAYBACK_SPEED_STORAGE_PREFIX = 'course_listen_playback_speed';

const getListenPlaybackSpeedStorageKey = (courseId: string) =>
  `${LISTEN_PLAYBACK_SPEED_STORAGE_PREFIX}:${courseId}`;

const isListenPlaybackSpeed = (value: number): value is ListenPlaybackSpeed =>
  LISTEN_PLAYBACK_SPEED_OPTIONS.some(option => option === value);

const normalizeListenPlaybackSpeed = (
  value: string | null,
): ListenPlaybackSpeed => {
  if (value === null) {
    return DEFAULT_LISTEN_PLAYBACK_SPEED;
  }

  const parsedValue = Number(value);
  if (!Number.isFinite(parsedValue) || !isListenPlaybackSpeed(parsedValue)) {
    return DEFAULT_LISTEN_PLAYBACK_SPEED;
  }

  return parsedValue;
};

export const formatListenPlaybackSpeed = (
  speed: ListenPlaybackSpeed | number,
) => `${Number.isInteger(speed) ? speed.toFixed(0) : String(speed)}x`;

export const readListenPlaybackSpeedFromStorage = (
  courseId: string,
): ListenPlaybackSpeed => {
  if (!courseId || typeof window === 'undefined') {
    return DEFAULT_LISTEN_PLAYBACK_SPEED;
  }

  try {
    return normalizeListenPlaybackSpeed(
      window.localStorage.getItem(getListenPlaybackSpeedStorageKey(courseId)),
    );
  } catch {
    return DEFAULT_LISTEN_PLAYBACK_SPEED;
  }
};

export const writeListenPlaybackSpeedToStorage = (
  courseId: string,
  speed: ListenPlaybackSpeed,
) => {
  if (!courseId || typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(
      getListenPlaybackSpeedStorageKey(courseId),
      String(speed),
    );
  } catch {
    // localStorage can be unavailable in private mode or embedded contexts.
  }
};

export const applyListenPlaybackSpeedToAudioElement = (
  audioElement: HTMLAudioElement,
  speed: ListenPlaybackSpeed,
) => {
  audioElement.defaultPlaybackRate = speed;
  audioElement.playbackRate = speed;
};

import {
  DEFAULT_LISTEN_PLAYBACK_SPEED,
  LISTEN_PLAYBACK_SPEED_OPTIONS,
  formatListenPlaybackSpeed,
  readListenPlaybackSpeedFromStorage,
  writeListenPlaybackSpeedToStorage,
} from './listenPlaybackSpeed';

describe('listenPlaybackSpeed', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('defines the supported listen playback speed options and display labels', () => {
    expect(LISTEN_PLAYBACK_SPEED_OPTIONS).toEqual([0.75, 1, 1.25, 1.5, 2]);
    expect(DEFAULT_LISTEN_PLAYBACK_SPEED).toBe(1);
    expect(formatListenPlaybackSpeed(0.75)).toBe('0.75x');
    expect(formatListenPlaybackSpeed(1)).toBe('1x');
    expect(formatListenPlaybackSpeed(1.25)).toBe('1.25x');
    expect(formatListenPlaybackSpeed(1.5)).toBe('1.5x');
    expect(formatListenPlaybackSpeed(2)).toBe('2x');
  });

  it('reads the default when storage is empty or contains an invalid value', () => {
    expect(readListenPlaybackSpeedFromStorage('course-1')).toBe(1);

    window.localStorage.setItem('course_listen_playback_speed:course-1', '3');
    expect(readListenPlaybackSpeedFromStorage('course-1')).toBe(1);

    window.localStorage.setItem(
      'course_listen_playback_speed:course-1',
      'fast',
    );
    expect(readListenPlaybackSpeedFromStorage('course-1')).toBe(1);
  });

  it('reads and writes playback speed by course', () => {
    writeListenPlaybackSpeedToStorage('course-1', 1.5);
    writeListenPlaybackSpeedToStorage('course-2', 2);

    expect(readListenPlaybackSpeedFromStorage('course-1')).toBe(1.5);
    expect(readListenPlaybackSpeedFromStorage('course-2')).toBe(2);
  });

  it('does not write unscoped storage values', () => {
    writeListenPlaybackSpeedToStorage('', 1.5);

    expect(window.localStorage.length).toBe(0);
    expect(readListenPlaybackSpeedFromStorage('')).toBe(1);
  });

  it('falls back safely when window is unavailable', () => {
    const windowDescriptor = Object.getOwnPropertyDescriptor(
      globalThis,
      'window',
    );
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: undefined,
    });

    try {
      expect(readListenPlaybackSpeedFromStorage('course-1')).toBe(1);
      expect(() =>
        writeListenPlaybackSpeedToStorage('course-1', 1.5),
      ).not.toThrow();
    } finally {
      if (windowDescriptor) {
        Object.defineProperty(globalThis, 'window', windowDescriptor);
      }
    }
  });

  it('falls back safely when localStorage access fails', () => {
    jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readListenPlaybackSpeedFromStorage('course-1')).toBe(1);

    jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() =>
      writeListenPlaybackSpeedToStorage('course-1', 1.5),
    ).not.toThrow();
  });
});

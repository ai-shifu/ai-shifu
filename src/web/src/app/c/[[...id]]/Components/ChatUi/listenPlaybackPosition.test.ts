import {
  clearListenPlaybackPositionFromStorage,
  isResumableListenPlaybackPosition,
  normalizeListenPlaybackSource,
  readListenPlaybackPositionFromStorage,
  writeListenPlaybackPositionToStorage,
  type ListenPlaybackPositionScope,
} from './listenPlaybackPosition';

const scope: ListenPlaybackPositionScope = {
  courseId: 'course-1',
  lessonId: 'lesson-1',
  elementBid: 'element-1',
  source: 'https://audio.example.com/audio-1.mp3',
};

describe('listenPlaybackPosition', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('normalizes URL source identities without volatile query or hash values', () => {
    expect(
      normalizeListenPlaybackSource(
        'https://audio.example.com/audio-1.mp3?token=secret#chapter-1',
      ),
    ).toBe('https://audio.example.com/audio-1.mp3');
  });

  it('writes and reads a position scoped to the course, lesson, element, and source', () => {
    writeListenPlaybackPositionToStorage({
      scope,
      positionSeconds: 24,
      durationSeconds: 60,
    });

    expect(readListenPlaybackPositionFromStorage(scope)).toBe(24);
    expect(
      readListenPlaybackPositionFromStorage({
        ...scope,
        source: 'https://audio.example.com/audio-2.mp3',
      }),
    ).toBeNull();
  });

  it('does not persist positions near the beginning or the completed end', () => {
    expect(
      isResumableListenPlaybackPosition({
        positionSeconds: 1.9,
        durationSeconds: 60,
      }),
    ).toBe(false);
    expect(
      isResumableListenPlaybackPosition({
        positionSeconds: 58.1,
        durationSeconds: 60,
      }),
    ).toBe(false);

    writeListenPlaybackPositionToStorage({
      scope,
      positionSeconds: 1,
      durationSeconds: 60,
    });
    expect(readListenPlaybackPositionFromStorage(scope)).toBeNull();
  });

  it('clears the stored position explicitly and handles storage failures', () => {
    writeListenPlaybackPositionToStorage({
      scope,
      positionSeconds: 24,
      durationSeconds: 60,
    });
    clearListenPlaybackPositionFromStorage(scope);
    expect(readListenPlaybackPositionFromStorage(scope)).toBeNull();

    jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() =>
      writeListenPlaybackPositionToStorage({
        scope,
        positionSeconds: 24,
        durationSeconds: 60,
      }),
    ).not.toThrow();
  });
});

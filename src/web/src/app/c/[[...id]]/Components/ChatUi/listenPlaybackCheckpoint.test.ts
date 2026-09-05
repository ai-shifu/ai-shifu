import {
  clearListenPlaybackCheckpoint,
  readListenPlaybackCheckpoint,
  writeListenPlaybackCheckpoint,
} from './listenPlaybackCheckpoint';

const scope = { courseId: 'course-1', lessonId: 'lesson-1' };

describe('listen playback checkpoints', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('stores a logical audio key independently from its temporary source URL', () => {
    writeListenPlaybackCheckpoint(scope, {
      audioKey: 'second-stream-element',
      timeMs: 5_500,
    });

    expect(readListenPlaybackCheckpoint(scope)).toEqual({
      audioKey: 'second-stream-element',
      timeMs: 5_500,
    });
  });

  it('does not retain completed or near-zero checkpoints', () => {
    writeListenPlaybackCheckpoint(scope, {
      audioKey: 'first-stream-element',
      timeMs: 1_000,
    });

    expect(readListenPlaybackCheckpoint(scope)).toBeNull();

    writeListenPlaybackCheckpoint(scope, {
      audioKey: 'first-stream-element',
      timeMs: 4_000,
    });
    clearListenPlaybackCheckpoint(scope);

    expect(readListenPlaybackCheckpoint(scope)).toBeNull();
  });
});

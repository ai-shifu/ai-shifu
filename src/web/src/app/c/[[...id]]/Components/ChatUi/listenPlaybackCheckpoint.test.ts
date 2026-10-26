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

  it('discards an older audio checkpoint when a replacement starts near zero', () => {
    writeListenPlaybackCheckpoint(scope, {
      audioKey: 'previous-stream-element',
      timeMs: 4_000,
    });
    writeListenPlaybackCheckpoint(scope, {
      audioKey: 'first-stream-element',
      timeMs: 1_000,
    });

    expect(readListenPlaybackCheckpoint(scope)).toBeNull();
  });

  it('keeps the saved position when teardown reports the same audio near zero', () => {
    writeListenPlaybackCheckpoint(scope, {
      audioKey: 'first-stream-element',
      timeMs: 4_000,
    });
    writeListenPlaybackCheckpoint(scope, {
      audioKey: 'first-stream-element',
      timeMs: 0,
    });

    expect(readListenPlaybackCheckpoint(scope)).toEqual({
      audioKey: 'first-stream-element',
      timeMs: 4_000,
    });
  });

  it('clears a checkpoint explicitly after its logical audio completes', () => {
    writeListenPlaybackCheckpoint(scope, {
      audioKey: 'first-stream-element',
      timeMs: 4_000,
    });

    clearListenPlaybackCheckpoint(scope);

    expect(readListenPlaybackCheckpoint(scope)).toBeNull();
  });
});

import {
  isAudioQueueType,
  isVisualQueueType,
  pickNextListenQueueIndex,
} from '@/c-utils/listen-queue';

describe('listen queue selection', () => {
  test('prioritizes audio events when available', () => {
    const queue = [
      { response: { type: 'content' } },
      { response: { type: 'audio_segment' } },
      { response: { type: 'outline_item_update' } },
    ];
    const index = pickNextListenQueueIndex({
      queue,
      pendingAudioCount: 0,
      isInteractionBlocked: false,
    });
    expect(index).toBe(1);
  });

  test('gates visual head while pending audio exists', () => {
    const queue = [
      { response: { type: 'content' } },
      { response: { type: 'audio_complete' } },
    ];
    const index = pickNextListenQueueIndex({
      queue,
      pendingAudioCount: 2,
      isInteractionBlocked: false,
    });
    expect(index).toBe(1);
  });

  test('returns blocked when visual head waits but no audio event can unblock', () => {
    const queue = [
      { response: { type: 'content' } },
      { response: { type: 'outline_item_update' } },
    ];
    const index = pickNextListenQueueIndex({
      queue,
      pendingAudioCount: 1,
      isInteractionBlocked: false,
    });
    expect(index).toBe(-1);
  });

  test('pauses queue while interaction is blocked and resumes after unblock', () => {
    const queue = [{ response: { type: 'audio_segment' } }];
    const blockedIndex = pickNextListenQueueIndex({
      queue,
      pendingAudioCount: 0,
      isInteractionBlocked: true,
    });
    const resumedIndex = pickNextListenQueueIndex({
      queue,
      pendingAudioCount: 0,
      isInteractionBlocked: false,
    });
    expect(blockedIndex).toBe(-1);
    expect(resumedIndex).toBe(0);
  });
});

describe('listen queue type guards', () => {
  test('detects audio queue type', () => {
    expect(isAudioQueueType('audio_segment')).toBe(true);
    expect(isAudioQueueType('audio_complete')).toBe(true);
    expect(isAudioQueueType('content')).toBe(false);
  });

  test('detects visual queue type', () => {
    expect(isVisualQueueType('content')).toBe(true);
    expect(isVisualQueueType('done')).toBe(true);
    expect(isVisualQueueType('audio_segment')).toBe(false);
  });
});

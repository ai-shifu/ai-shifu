import {
  ListenQueueManager,
  buildQueueItemId,
  type QueueEvent,
  type VisualQueueItem,
  type AudioQueueItem,
  type AudioSegmentData,
} from '@/c-utils/listen-mode/queue-manager';
import type { ChatContentItem } from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';

describe('buildQueueItemId', () => {
  it('should build visual ID with position', () => {
    const id = buildQueueItemId({
      type: 'visual',
      bid: 'block-123',
      position: 0,
    });
    expect(id).toBe('visual:block-123:0');
  });

  it('should build audio ID with position', () => {
    const id = buildQueueItemId({
      type: 'audio',
      bid: 'block-456',
      position: 1,
    });
    expect(id).toBe('audio:block-456:1');
  });

  it('should normalize position to integer', () => {
    const id = buildQueueItemId({
      type: 'visual',
      bid: 'block-123',
      position: 1.7,
    });
    expect(id).toBe('visual:block-123:1');
  });

  it('should build interaction ID without position', () => {
    const id = buildQueueItemId({
      type: 'interaction',
      bid: 'block-789',
    });
    expect(id).toBe('interaction:block-789');
  });

  it('should handle missing position (default to 0)', () => {
    const id = buildQueueItemId({
      type: 'visual',
      bid: 'block-123',
    });
    expect(id).toBe('visual:block-123:0');
  });
});

describe('ListenQueueManager', () => {
  let manager: ListenQueueManager;
  let sessionIdRef: React.MutableRefObject<number>;

  beforeEach(() => {
    sessionIdRef = { current: 1 };
    manager = new ListenQueueManager({
      audioWaitTimeout: 15000,
      silentVisualDuration: 5000,
      sessionIdRef,
    });
  });

  afterEach(() => {
    // Use destroy() to clean up both queue state AND listeners
    manager.destroy();
    jest.clearAllTimers();
  });

  describe('enqueueVisual', () => {
    it('should enqueue visual item with correct ID', () => {
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      });

      expect(manager.getQueueLength()).toBe(1);
      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].id).toBe('visual:block-1:0');
      expect(snapshot[0].status).toBe('pending');
    });

    it('should not enqueue duplicate visual', () => {
      const visualData = {
        type: 'visual' as const,
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      };

      manager.enqueueVisual(visualData);
      manager.enqueueVisual(visualData);

      expect(manager.getQueueLength()).toBe(1);
    });

    it('should enqueue multiple different visuals', () => {
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-2:0',
      });

      expect(manager.getQueueLength()).toBe(2);
    });
  });

  describe('enqueueInteraction', () => {
    it('should enqueue interaction item', () => {
      const mockContentItem = {
        type: 'interaction' as const,
        generated_block_bid: 'block-int',
      } as ChatContentItem;

      manager.enqueueInteraction({
        type: 'interaction',
        generatedBlockBid: 'block-int',
        page: 1,
        contentItem: mockContentItem,
      });

      expect(manager.getQueueLength()).toBe(1);
      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].id).toBe('interaction:block-int');
    });
  });

  describe('upsertAudio - out-of-order handling', () => {
    it('should insert audio after existing visual', () => {
      // Enqueue visual first
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      });

      expect(manager.getQueueLength()).toBe(1);

      // Audio arrives
      const audioData: AudioSegmentData = {
        audio_segment: 'base64data',
        is_final: false,
      };
      manager.upsertAudio('block-1', 0, audioData);

      // Should have visual + audio
      expect(manager.getQueueLength()).toBe(2);
      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].id).toBe('visual:block-1:0');
      expect(snapshot[1].id).toBe('audio:block-1:0');
      expect((snapshot[1] as AudioQueueItem).segments).toHaveLength(1);
    });

    it('should handle audio arriving before visual', () => {
      // Audio arrives first
      const audioData: AudioSegmentData = {
        audio_url: 'https://oss.example.com/audio.mp3',
        is_final: true,
      };
      manager.upsertAudio('block-1', 0, audioData);

      // Audio should be enqueued as pending
      expect(manager.getQueueLength()).toBe(1);
      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].id).toBe('audio:block-1:0');
      expect(snapshot[0].status).toBe('pending');
    });

    it('should handle audio arriving after subsequent visual (out-of-order)', () => {
      // Enqueue: Visual A → Visual B
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-a',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-a:0',
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-b',
        position: 0,
        page: 2,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-b:0',
      });

      expect(manager.getQueueLength()).toBe(2);

      // Audio for A arrives (after B was enqueued)
      const audioDataA: AudioSegmentData = {
        audio_url: 'https://oss.example.com/audio-a.mp3',
        is_final: true,
      };
      manager.upsertAudio('block-a', 0, audioDataA);

      // Should insert audio after visual A
      expect(manager.getQueueLength()).toBe(3);
      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].id).toBe('visual:block-a:0');
      expect(snapshot[1].id).toBe('audio:block-a:0'); // Inserted here
      expect(snapshot[2].id).toBe('visual:block-b:0');
    });

    it('should update existing audio with streaming segments', () => {
      // Initial audio segment
      const segment1: AudioSegmentData = {
        audio_segment: 'segment1',
        is_final: false,
      };
      manager.upsertAudio('block-1', 0, segment1);

      expect(manager.getQueueLength()).toBe(1);
      let snapshot = manager.getQueueSnapshot();
      expect((snapshot[0] as AudioQueueItem).segments).toHaveLength(1);
      expect((snapshot[0] as AudioQueueItem).isStreaming).toBe(true);

      // Second segment
      const segment2: AudioSegmentData = {
        audio_segment: 'segment2',
        is_final: false,
      };
      manager.upsertAudio('block-1', 0, segment2);

      expect(manager.getQueueLength()).toBe(1); // Still 1 item
      snapshot = manager.getQueueSnapshot();
      expect((snapshot[0] as AudioQueueItem).segments).toHaveLength(2);

      // Final segment
      const segment3: AudioSegmentData = {
        audio_url: 'https://oss.example.com/final.mp3',
        is_final: true,
      };
      manager.upsertAudio('block-1', 0, segment3);

      snapshot = manager.getQueueSnapshot();
      expect((snapshot[0] as AudioQueueItem).segments).toHaveLength(3);
      expect((snapshot[0] as AudioQueueItem).isStreaming).toBe(false);
      expect((snapshot[0] as AudioQueueItem).audioUrl).toBe(
        'https://oss.example.com/final.mp3',
      );
    });

    it('should adjust currentIndex when inserting audio before current position', () => {
      // Queue: [V:a, V:b] -> start processing -> advance to V:b (index 1)
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-a',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-a:0',
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-b',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-b:0',
      });

      manager.start();
      manager.advance(); // Now at V:b (index 1)

      const currentBefore = manager.getCurrentItem();
      expect(currentBefore?.id).toBe('visual:block-b:0');

      // Insert audio after V:a (at index 1, which is <= currentIndex)
      manager.upsertAudio('block-a', 0, {
        audio_url: 'https://oss.example.com/audio-a.mp3',
        is_final: true,
      });

      // Queue is now: [V:a, A:a, V:b]
      // currentIndex should have been adjusted from 1 to 2
      const currentAfter = manager.getCurrentItem();
      expect(currentAfter?.id).toBe('visual:block-b:0');
      expect(manager.getQueueLength()).toBe(3);
    });
  });

  describe('FIFO processing order', () => {
    it('should process items in FIFO order', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));
      manager.on('audio:play', event => events.push(event));

      // Enqueue visual + audio + visual + audio
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false, // Silent visual
        expectedAudioId: 'audio:block-1:0',
      });

      manager.upsertAudio('block-1', 0, {
        audio_url: 'https://oss.example.com/audio-1.mp3',
        is_final: true,
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      manager.upsertAudio('block-2', 0, {
        audio_url: 'https://oss.example.com/audio-2.mp3',
        is_final: true,
      });

      // Start processing
      manager.start();

      // Should emit visual:show for first item
      expect(events).toHaveLength(1);
      expect(events[0].type).toBe('visual:show');
      expect(events[0].item.id).toBe('visual:block-1:0');
    });

    it('should wait for audio when hasTextAfterVisual is true', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));
      manager.on('audio:play', event => events.push(event));

      // Enqueue visual with hasTextAfterVisual=true
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();

      // Should show visual in waiting mode
      expect(events).toHaveLength(1);
      expect(events[0].type).toBe('visual:show');
      const visualItem = events[0].item as VisualQueueItem;
      expect(visualItem.status).toBe('waiting');

      // Audio arrives
      manager.upsertAudio('block-1', 0, {
        audio_url: 'https://oss.example.com/audio-1.mp3',
        is_final: true,
      });

      // Should auto-advance to audio
      // Note: advance() is called async, so we need to wait
      return new Promise<void>(resolve => {
        setTimeout(() => {
          expect(events).toHaveLength(2);
          expect(events[1].type).toBe('audio:play');
          expect(events[1].item.id).toBe('audio:block-1:0');
          resolve();
        }, 10);
      });
    });
  });

  describe('audio wait timeout', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('should timeout visual with hasTextAfterVisual after timeout period', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));
      manager.on('queue:error', event => events.push(event));

      // Enqueue visual with hasTextAfterVisual=true
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();

      // Should show visual in waiting mode
      expect(events).toHaveLength(1);
      expect(events[0].type).toBe('visual:show');

      // Advance time by 15 seconds (timeout)
      jest.advanceTimersByTime(15000);

      // Should emit timeout error
      expect(events).toHaveLength(2);
      expect(events[1].type).toBe('queue:error');
      expect(events[1].reason).toBe('audio_timeout');

      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].status).toBe('timeout');
    });

    it('should clear timeout when audio arrives in time', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));
      manager.on('queue:error', event => events.push(event));

      // Enqueue visual
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();

      // Advance time by 10 seconds (before timeout)
      jest.advanceTimersByTime(10000);

      // Audio arrives
      manager.upsertAudio('block-1', 0, {
        audio_url: 'https://oss.example.com/audio-1.mp3',
        is_final: true,
      });

      // Advance time by another 10 seconds (past original timeout)
      jest.advanceTimersByTime(10000);

      // Should NOT emit timeout error
      const errorEvents = events.filter(e => e.type === 'queue:error');
      expect(errorEvents).toHaveLength(0);
    });

    it('should timeout non-ready audio and skip', () => {
      const events: QueueEvent[] = [];
      manager.on('audio:play', event => events.push(event));
      manager.on('queue:error', event => events.push(event));

      // Audio arrives early (pending, no visual yet)
      manager.upsertAudio('block-1', 0, {
        audio_segment: 'partial',
        is_final: false,
      });

      // Change status to pending to simulate early arrival
      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].status).toBe('pending');

      manager.start();

      // Audio should enter 'waiting' state since it's not ready
      const current = manager.getCurrentItem() as AudioQueueItem;
      expect(current.status).toBe('waiting');

      // Advance time past timeout
      jest.advanceTimersByTime(15000);

      // Should emit error and skip
      const errorEvents = events.filter(e => e.type === 'queue:error');
      expect(errorEvents).toHaveLength(1);
      expect(errorEvents[0].reason).toBe('audio_not_ready_timeout');
    });
  });

  describe('pause/resume/reset', () => {
    it('should pause queue processing', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      expect(events).toHaveLength(1);

      // Pause
      manager.pause();

      // Enqueue another item
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      // Should not process new item
      expect(events).toHaveLength(1);
    });

    it('should resume queue processing', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      manager.pause();

      expect(events).toHaveLength(1);

      // Advance to next item (simulate completion)
      manager.advance();

      // Should not process (paused)
      expect(events).toHaveLength(1);

      // Resume
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      manager.resume();

      // Should process next item
      return new Promise<void>(resolve => {
        setTimeout(() => {
          expect(events).toHaveLength(2);
          resolve();
        }, 10);
      });
    });

    it('should reset queue and clear all state', () => {
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();

      expect(manager.getQueueLength()).toBe(1);
      expect(manager.getCurrentItem()).toBeTruthy();

      manager.reset();

      expect(manager.getQueueLength()).toBe(0);
      expect(manager.getCurrentItem()).toBeNull();
    });

    it('should preserve listeners after reset', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      // First cycle
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      expect(events).toHaveLength(1);

      // Reset
      manager.reset();

      // Second cycle - listeners should still work
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      manager.start();
      expect(events).toHaveLength(2);
      expect(events[1].item.id).toBe('visual:block-2:0');
    });

    it('should clear listeners only on destroy', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      expect(events).toHaveLength(1);

      // Destroy (clears listeners)
      manager.destroy();

      // Re-create manager to verify
      manager = new ListenQueueManager({
        audioWaitTimeout: 15000,
        silentVisualDuration: 5000,
        sessionIdRef,
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      manager.start();
      // Old listener should NOT fire (was on the old manager instance)
      expect(events).toHaveLength(1);
    });
  });

  describe('advance', () => {
    it('should mark current item as completed and move to next', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      manager.start();

      const snapshot1 = manager.getQueueSnapshot();
      expect(snapshot1[0].status).toBe('playing');

      manager.advance();

      const snapshot2 = manager.getQueueSnapshot();
      expect(snapshot2[0].status).toBe('completed');
      expect(snapshot2[1].status).toBe('playing');
    });

    it('should emit queue:completed when queue finishes', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));
      manager.on('queue:completed', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      manager.advance(); // Complete first item

      const completedEvents = events.filter(e => e.type === 'queue:completed');
      expect(completedEvents).toHaveLength(1);
    });

    it('should not emit queue:completed twice even with extra advance calls', () => {
      const events: QueueEvent[] = [];
      manager.on('queue:completed', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      manager.advance(); // Complete first item -> triggers completed
      manager.advance(); // Extra advance
      manager.advance(); // Extra advance

      expect(events).toHaveLength(1);
    });

    it('should not re-trigger queue:completed after new items are enqueued post-completion', () => {
      const events: QueueEvent[] = [];
      manager.on('queue:completed', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      manager.advance(); // Complete -> triggers completed

      expect(events).toHaveLength(1);

      // Enqueue new item after completion
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      // Should not trigger another completed
      expect(events).toHaveLength(1);
    });
  });

  describe('session isolation', () => {
    it('should use current session ID in events', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      sessionIdRef.current = 42;

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();

      expect(events[0].sessionId).toBe(42);
    });

    it('should reset queue when session changes', () => {
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      expect(manager.getQueueLength()).toBe(1);

      // Simulate session change
      sessionIdRef.current = 2;
      manager.reset();

      expect(manager.getQueueLength()).toBe(0);

      // Enqueue new items for new session
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      expect(manager.getQueueLength()).toBe(1);
      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].id).toBe('visual:block-2:0');
    });
  });

  describe('event listeners', () => {
    it('should register and trigger event listeners', () => {
      const visualShowListener = jest.fn();
      manager.on('visual:show', visualShowListener);

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();

      expect(visualShowListener).toHaveBeenCalledTimes(1);
      expect(visualShowListener).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'visual:show',
          sessionId: 1,
        }),
      );
    });

    it('should remove event listeners with off()', () => {
      const listener = jest.fn();
      manager.on('visual:show', listener);

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      expect(listener).toHaveBeenCalledTimes(1);

      manager.off('visual:show', listener);
      manager.reset();

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      manager.start();
      expect(listener).toHaveBeenCalledTimes(1); // Still 1, not called again
    });
  });

  describe('getCurrentIndex', () => {
    it('should return -1 before processing starts', () => {
      expect(manager.getCurrentIndex()).toBe(-1);
    });

    it('should return current index during processing', () => {
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      manager.start();
      expect(manager.getCurrentIndex()).toBe(0);

      manager.advance();
      expect(manager.getCurrentIndex()).toBe(1);
    });
  });

  describe('startFromIndex', () => {
    it('should start processing from specified index', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-3',
        position: 0,
        page: 3,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-3:0',
      });

      // Start from index 2 (third item)
      manager.startFromIndex(2);

      expect(events).toHaveLength(1);
      expect(events[0].item.id).toBe('visual:block-3:0');
      expect(manager.getCurrentIndex()).toBe(2);

      // Items before index 2 should be marked completed
      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].status).toBe('completed');
      expect(snapshot[1].status).toBe('completed');
      expect(snapshot[2].status).toBe('playing');
    });

    it('should clamp index to valid range', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      // Index beyond range should clamp to last item
      manager.startFromIndex(999);
      expect(events).toHaveLength(1);
      expect(events[0].item.id).toBe('visual:block-1:0');
    });

    it('should clamp negative index to 0', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.startFromIndex(-5);
      expect(events).toHaveLength(1);
      expect(events[0].item.id).toBe('visual:block-1:0');
    });

    it('should not process on empty queue', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.startFromIndex(0);
      expect(events).toHaveLength(0);
    });

    it('should re-process a previously completed item', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      // Start normally
      manager.start();
      manager.advance(); // Complete first, move to second
      expect(events).toHaveLength(2);

      // Go back to first item
      manager.startFromIndex(0);
      expect(events).toHaveLength(3);
      expect(events[2].item.id).toBe('visual:block-1:0');
    });
  });

  describe('updateVisualExpectation', () => {
    it('should update hasTextAfterVisual flag', () => {
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      const snapshotBefore = manager.getQueueSnapshot();
      expect((snapshotBefore[0] as VisualQueueItem).hasTextAfterVisual).toBe(
        false,
      );

      manager.updateVisualExpectation('block-1', 0, true);

      const snapshotAfter = manager.getQueueSnapshot();
      expect((snapshotAfter[0] as VisualQueueItem).hasTextAfterVisual).toBe(
        true,
      );
      expect((snapshotAfter[0] as VisualQueueItem).expectedAudioId).toBe(
        'audio:block-1:0',
      );
    });

    it('should not update if value is the same', () => {
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      });

      // Should be a no-op
      manager.updateVisualExpectation('block-1', 0, true);

      const snapshot = manager.getQueueSnapshot();
      expect((snapshot[0] as VisualQueueItem).hasTextAfterVisual).toBe(true);
    });

    it('should do nothing for non-existent visual', () => {
      // Should not throw
      manager.updateVisualExpectation('nonexistent', 0, true);
      expect(manager.getQueueLength()).toBe(0);
    });
  });

  describe('remapPages', () => {
    it('should remap queue item pages in place', () => {
      const mockContentItem = {
        type: 'interaction' as const,
        generated_block_bid: 'block-int',
      } as ChatContentItem;

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 0,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      });
      manager.upsertAudio('block-1', 0, {
        audio_url: 'https://oss.example.com/audio-1.mp3',
        is_final: true,
      });
      manager.enqueueInteraction({
        type: 'interaction',
        generatedBlockBid: 'block-int',
        page: 0,
        contentItem: mockContentItem,
      });

      manager.remapPages(page => (page === 0 ? 1 : page));

      const snapshot = manager.getQueueSnapshot();
      expect(snapshot.every(item => item.page === 1)).toBe(true);
    });

    it('should ignore invalid remap values', () => {
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.remapPages(() => Number.NaN);
      manager.remapPages(() => -1);

      const snapshot = manager.getQueueSnapshot();
      expect(snapshot[0].page).toBe(2);
    });
  });

  describe('hasCompleted auto-reset', () => {
    it('should auto-reset hasCompleted when enqueuing visual after completion', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));
      manager.on('queue:completed', event => events.push(event));

      // Enqueue and complete
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      manager.advance(); // Complete -> triggers queue:completed

      const completedEvents = events.filter(e => e.type === 'queue:completed');
      expect(completedEvents).toHaveLength(1);

      // Enqueue new item after completion — hasCompleted should auto-reset
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-2',
        position: 0,
        page: 2,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-2:0',
      });

      // Resume processing — should process the new item
      manager.resume();

      // queue:completed should fire again when the new item completes
      manager.advance();

      const allCompleted = events.filter(e => e.type === 'queue:completed');
      expect(allCompleted).toHaveLength(2);
    });

    it('should auto-reset hasCompleted when enqueuing interaction after completion', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));
      manager.on('interaction:show', event => events.push(event));
      manager.on('queue:completed', event => events.push(event));

      const mockContentItem = {
        type: 'interaction' as const,
        generated_block_bid: 'block-int',
      } as ChatContentItem;

      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: false,
        expectedAudioId: 'audio:block-1:0',
      });

      manager.start();
      manager.advance(); // Complete visual -> triggers queue:completed

      expect(events.filter(e => e.type === 'queue:completed')).toHaveLength(1);

      // Enqueue interaction after completion
      manager.enqueueInteraction({
        type: 'interaction',
        generatedBlockBid: 'block-int',
        page: 1,
        contentItem: mockContentItem,
      });

      // Resume processing
      manager.resume();

      // Should show interaction (hasCompleted was reset)
      const interactionEvents = events.filter(
        e => e.type === 'interaction:show',
      );
      expect(interactionEvents).toHaveLength(1);
    });
  });

  describe('visual item with audio already ready', () => {
    it('should emit visual:show with playing status (cloned) then auto-advance', () => {
      const events: QueueEvent[] = [];
      manager.on('visual:show', event => events.push(event));
      manager.on('audio:play', event => events.push(event));

      // Enqueue visual with hasTextAfterVisual=true
      manager.enqueueVisual({
        type: 'visual',
        generatedBlockBid: 'block-1',
        position: 0,
        page: 1,
        hasTextAfterVisual: true,
        expectedAudioId: 'audio:block-1:0',
      });

      // Audio arrives BEFORE processing starts
      manager.upsertAudio('block-1', 0, {
        audio_url: 'https://oss.example.com/audio-1.mp3',
        is_final: true,
      });

      manager.start();

      // visual:show should have been emitted with status 'playing' (cloned)
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].type).toBe('visual:show');
      // The emitted item should be a clone, so its status won't be mutated
      expect((events[0].item as VisualQueueItem).status).toBe('playing');

      // After setTimeout(0), audio:play should fire
      return new Promise<void>(resolve => {
        setTimeout(() => {
          expect(events.some(event => event.type === 'audio:play')).toBe(true);
          resolve();
        }, 10);
      });
    });
  });
});

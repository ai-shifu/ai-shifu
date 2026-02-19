import { normalizeListenAudioPosition } from '@/c-utils/listen-orchestrator';
import type { ChatContentItem } from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';

// Queue item types
export type QueueItemType = 'visual' | 'audio' | 'interaction';

// Queue item status lifecycle
export type QueueItemStatus =
  | 'pending' // Enqueued, waiting for dependencies
  | 'waiting' // Active, waiting for resource (e.g., audio)
  | 'ready' // Ready to play
  | 'playing' // Currently playing
  | 'completed' // Finished
  | 'timeout' // Timed out waiting
  | 'error'; // Error state

// Base queue item interface
export interface BaseQueueItem {
  id: string; // Unique ID: "visual:{bid}:{position}" | "audio:{bid}:{position}" | "interaction:{bid}"
  type: QueueItemType;
  status: QueueItemStatus;
  generatedBlockBid: string;
  position?: number; // For content items with multi-position audio
  page: number; // Slide page number
  enqueuedAt: number; // Timestamp when enqueued
}

// Visual queue item (represents a slide/visual element)
export interface VisualQueueItem extends BaseQueueItem {
  type: 'visual';
  visualKind?: string; // 'svg', 'table', 'video', etc.
  hasTextAfterVisual: boolean; // If true, audio is guaranteed (must wait)
  expectedAudioId: string; // ID of expected audio item
  waitingStartedAt?: number; // Timestamp when started waiting for audio
}

// Audio segment data from SSE
export interface AudioSegmentData {
  audio_segment?: string; // Base64 encoded audio data
  audio_url?: string; // Final OSS URL
  is_final?: boolean; // Whether this is the final segment
}

// Audio queue item
export interface AudioQueueItem extends BaseQueueItem {
  type: 'audio';
  audioUrl?: string; // OSS URL after completion
  segments: AudioSegmentData[]; // Streaming segments
  isStreaming: boolean; // TTS still streaming
  durationMs?: number;
  audioPosition: number; // Normalized position
}

// Interaction queue item
export interface InteractionQueueItem extends BaseQueueItem {
  type: 'interaction';
  contentItem: ChatContentItem; // Original interaction data
  nextIndex: number | null; // Index to resume after interaction
}

export type QueueItem = VisualQueueItem | AudioQueueItem | InteractionQueueItem;

// Queue event types
export type QueueEventType =
  | 'visual:show'
  | 'audio:play'
  | 'interaction:show'
  | 'queue:completed'
  | 'queue:error';

export interface QueueEvent {
  type: QueueEventType;
  item: QueueItem;
  sessionId: number;
  reason?: string; // For error events
}

// Event listener type
export type QueueEventListener = (event: QueueEvent) => void;

// Configuration for queue manager
export interface ListenQueueManagerConfig {
  audioWaitTimeout: number; // Default 15000ms
  silentVisualDuration: number; // Default 5000ms — auto-advance delay for silent visuals
  sessionIdRef: React.MutableRefObject<number>;
}

/**
 * Build stable queue item ID
 * Format: "type:bid:position" for content items, "type:bid" for interactions
 */
export function buildQueueItemId(params: {
  type: QueueItemType;
  bid: string;
  position?: number;
}): string {
  if (params.type === 'visual' || params.type === 'audio') {
    const pos = normalizeListenAudioPosition(params.position);
    return `${params.type}:${params.bid}:${pos}`;
  }
  return `${params.type}:${params.bid}`;
}

/**
 * ListenQueueManager - FIFO queue manager for listen mode
 *
 * Manages the strict sequential playback of visual-audio pairs:
 * - Enqueues visual and audio items as SSE events arrive
 * - Handles out-of-order audio arrival (inserts into correct position)
 * - Waits for expected audio when hasTextAfterVisual is true
 * - Auto-advances silent visuals after viewing period
 * - Emits events for UI synchronization
 */
export class ListenQueueManager {
  private queue: QueueItem[] = [];
  private currentIndex: number = -1;
  private sessionIdRef: React.MutableRefObject<number>;
  private processingTimer: NodeJS.Timeout | null = null;
  private audioWaitTimeout: number;
  private silentVisualDuration: number;
  private isProcessing: boolean = false;
  private isPaused: boolean = false;
  private hasCompleted: boolean = false;
  private listeners: Map<QueueEventType, Set<QueueEventListener>> = new Map();

  constructor(config: ListenQueueManagerConfig) {
    this.sessionIdRef = config.sessionIdRef;
    this.audioWaitTimeout = config.audioWaitTimeout;
    this.silentVisualDuration = config.silentVisualDuration;
  }

  // ============================================================================
  // Event Emitter Methods
  // ============================================================================

  on(eventType: QueueEventType, listener: QueueEventListener): void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(listener);
  }

  off(eventType: QueueEventType, listener: QueueEventListener): void {
    const listeners = this.listeners.get(eventType);
    if (listeners) {
      listeners.delete(listener);
    }
  }

  private emit(event: QueueEvent): void {
    const listeners = this.listeners.get(event.type);
    if (listeners) {
      listeners.forEach(listener => listener(event));
    }
  }

  // ============================================================================
  // Queue Operations
  // ============================================================================

  /**
   * Enqueue a visual item (slide/visual element)
   */
  enqueueVisual(
    item: Omit<VisualQueueItem, 'id' | 'status' | 'enqueuedAt'>,
  ): void {
    const id = buildQueueItemId({
      type: 'visual',
      bid: item.generatedBlockBid,
      position: item.position,
    });

    // Check for duplicate
    const existing = this.queue.find(i => i.id === id);
    if (existing) {
      console.warn(`[Queue] Visual ${id} already enqueued, skipping`);
      return;
    }

    // Allow new items to be processed after queue was previously completed
    if (this.hasCompleted) {
      this.hasCompleted = false;
    }

    const queueItem: VisualQueueItem = {
      ...item,
      id,
      type: 'visual',
      status: 'pending',
      enqueuedAt: Date.now(),
    };

    this.queue.push(queueItem);
    console.log(`[Queue] Enqueued visual: ${id}, page: ${item.page}`);

    // Note: Don't auto-trigger processing here. Use start() to begin processing.
  }

  /**
   * Enqueue an audio item
   * Note: Audio usually arrives via upsertAudio, not this method
   */
  enqueueAudio(
    item: Omit<AudioQueueItem, 'id' | 'status' | 'enqueuedAt'>,
  ): void {
    const id = buildQueueItemId({
      type: 'audio',
      bid: item.generatedBlockBid,
      position: item.position,
    });

    const queueItem: AudioQueueItem = {
      ...item,
      id,
      type: 'audio',
      status: 'ready',
      enqueuedAt: Date.now(),
    };

    this.queue.push(queueItem);
    console.log(`[Queue] Enqueued audio: ${id}`);
  }

  /**
   * Enqueue an interaction item
   */
  enqueueInteraction(
    item: Omit<InteractionQueueItem, 'id' | 'status' | 'enqueuedAt'>,
  ): void {
    const id = buildQueueItemId({
      type: 'interaction',
      bid: item.generatedBlockBid,
    });

    // Check for duplicate
    const existing = this.queue.find(i => i.id === id);
    if (existing) {
      console.warn(`[Queue] Interaction ${id} already enqueued, skipping`);
      return;
    }

    // Allow new items to be processed after queue was previously completed
    if (this.hasCompleted) {
      this.hasCompleted = false;
    }

    const queueItem: InteractionQueueItem = {
      ...item,
      id,
      type: 'interaction',
      status: 'pending',
      enqueuedAt: Date.now(),
    };

    this.queue.push(queueItem);
    console.log(`[Queue] Enqueued interaction: ${id}`);
  }

  /**
   * Upsert audio data (handles out-of-order arrival)
   * This is the primary method for adding/updating audio items as SSE events arrive
   */
  upsertAudio(
    blockBid: string,
    position: number,
    audioData: AudioSegmentData,
  ): void {
    const audioId = buildQueueItemId({
      type: 'audio',
      bid: blockBid,
      position,
    });

    // Find existing audio item
    const existingAudioIdx = this.queue.findIndex(item => item.id === audioId);

    if (existingAudioIdx >= 0) {
      // Update existing audio item (streaming segments)
      const existing = this.queue[existingAudioIdx] as AudioQueueItem;
      const wasWaiting = existing.status === 'waiting';
      existing.segments = [...existing.segments, audioData];
      existing.isStreaming = audioData.is_final === false;
      if (audioData.audio_url) {
        existing.audioUrl = audioData.audio_url;
      }
      // Only promote to 'ready' from early states — never regress 'playing' or 'completed'
      if (existing.status === 'pending' || existing.status === 'waiting') {
        existing.status = 'ready';
      }
      console.log(
        `[Queue] Updated audio: ${audioId}, segments: ${existing.segments.length}, final: ${!existing.isStreaming}`,
      );

      // If this audio item was the current item waiting for data, trigger
      // processing so it can now play.
      if (
        wasWaiting &&
        !this.isPaused &&
        this.currentIndex === existingAudioIdx
      ) {
        this.clearTimers();
        setTimeout(() => {
          this.processQueue();
        }, 0);
      }
    } else {
      // Audio arrived - find corresponding visual or insert at correct position
      const visualId = buildQueueItemId({
        type: 'visual',
        bid: blockBid,
        position,
      });
      const visualIdx = this.queue.findIndex(item => item.id === visualId);

      // Derive page number from visual or next item
      let page = 0;
      if (visualIdx >= 0) {
        page = this.queue[visualIdx].page;
      } else if (this.queue.length > 0) {
        // Use page from last item
        page = this.queue[this.queue.length - 1].page;
      }

      const audioItem: AudioQueueItem = {
        id: audioId,
        type: 'audio',
        status: 'ready',
        generatedBlockBid: blockBid,
        position,
        audioPosition: normalizeListenAudioPosition(position),
        page,
        enqueuedAt: Date.now(),
        segments: [audioData],
        isStreaming: audioData.is_final === false,
        audioUrl: audioData.audio_url,
      };

      if (visualIdx >= 0) {
        const insertIdx = visualIdx + 1;

        // Adjust currentIndex before splice: if the insertion point is at or
        // before currentIndex, all items after the insertion point shift by +1.
        if (this.currentIndex >= insertIdx) {
          this.currentIndex++;
        }

        // Insert audio right after its visual
        this.queue.splice(insertIdx, 0, audioItem);
        console.log(
          `[Queue] Inserted audio after visual: ${audioId} at index ${insertIdx}`,
        );

        // If visual is waiting for this audio, mark it as completed and trigger processing
        const visual = this.queue[visualIdx] as VisualQueueItem;
        if (visual.status === 'waiting') {
          visual.status = 'completed';
          this.clearTimers(); // Clear audio wait timeout

          // When the visual was the current item (currentIndex === visualIdx),
          // the index was NOT adjusted above (visualIdx < insertIdx), so we
          // advance past the completed visual to the newly inserted audio.
          if (!this.isPaused && this.currentIndex === visualIdx) {
            setTimeout(() => {
              this.currentIndex++;
              this.processQueue();
            }, 0);
          }
        }
      } else {
        // Visual not enqueued yet - audio arrived early
        // Enqueue and mark pending (will be processed when visual arrives)
        audioItem.status = 'pending';
        this.queue.push(audioItem);
        console.log(`[Queue] Audio arrived early: ${audioId}, marked pending`);
      }
    }
  }

  // ============================================================================
  // Queue Control
  // ============================================================================

  /**
   * Start queue processing
   */
  start(): void {
    console.log('[Queue] Starting queue processing');
    this.isPaused = false;
    this.hasCompleted = false;
    this.processQueue();
  }

  /**
   * Pause queue processing
   */
  pause(): void {
    console.log('[Queue] Pausing queue processing');
    this.isPaused = true;
    this.clearTimers();
  }

  /**
   * Resume queue processing
   */
  resume(): void {
    console.log('[Queue] Resuming queue processing');
    this.isPaused = false;
    this.processQueue();
  }

  /**
   * Reset queue (clear all items and state)
   */
  reset(): void {
    console.log('[Queue] Resetting queue');
    this.queue = [];
    this.currentIndex = -1;
    this.isProcessing = false;
    this.isPaused = false;
    this.hasCompleted = false;
    this.clearTimers();
    // Note: Do NOT clear listeners here. Event subscriptions are managed by
    // the React hook lifecycle (use-queue-manager.ts) and must survive resets.
  }

  /**
   * Remove all event listeners. Only call this on unmount, not on reset.
   */
  destroy(): void {
    this.reset();
    this.listeners.clear();
  }

  /**
   * Advance to next item in queue
   * Called when current item completes (audio ends, interaction resolves, etc.)
   */
  advance(): void {
    console.log(`[Queue] Advancing from index ${this.currentIndex}`);

    if (this.currentIndex >= 0 && this.currentIndex < this.queue.length) {
      const current = this.queue[this.currentIndex];
      // Only mark as completed if not already in a terminal state (completed, timeout, error)
      if (
        current.status !== 'completed' &&
        current.status !== 'timeout' &&
        current.status !== 'error'
      ) {
        current.status = 'completed';
      }
    }

    this.clearTimers();
    this.currentIndex++;

    if (!this.isPaused) {
      this.processQueue();
    }
  }

  // ============================================================================
  // State Queries
  // ============================================================================

  getCurrentItem(): QueueItem | null {
    if (this.currentIndex >= 0 && this.currentIndex < this.queue.length) {
      return this.queue[this.currentIndex];
    }
    return null;
  }

  getCurrentIndex(): number {
    return this.currentIndex;
  }

  getQueueLength(): number {
    return this.queue.length;
  }

  getQueueSnapshot(): QueueItem[] {
    return [...this.queue];
  }

  /**
   * Start processing from a specific index (used for prev/next navigation)
   */
  startFromIndex(index: number): void {
    const clampedIndex = Math.max(0, Math.min(index, this.queue.length - 1));
    if (this.queue.length === 0) {
      console.warn('[Queue] Cannot startFromIndex on empty queue');
      return;
    }

    console.log(`[Queue] Starting from index ${clampedIndex}`);
    this.currentIndex = clampedIndex;
    this.isPaused = false;
    this.hasCompleted = false;
    this.clearTimers();

    // Mark all items before the target as completed
    for (let i = 0; i < clampedIndex; i++) {
      if (
        this.queue[i].status !== 'completed' &&
        this.queue[i].status !== 'error' &&
        this.queue[i].status !== 'timeout'
      ) {
        this.queue[i].status = 'completed';
      }
    }

    // Reset the target item to pending so it gets processed
    const targetItem = this.queue[clampedIndex];
    if (targetItem && targetItem.status === 'completed') {
      targetItem.status = 'pending';
    }

    this.processQueue();
  }

  /**
   * Update the hasTextAfterVisual flag for an already-enqueued visual item.
   * Used when a silent visual is upgraded to audio-backed (isSilentVisual flips).
   */
  updateVisualExpectation(
    bid: string,
    position: number,
    hasTextAfterVisual: boolean,
  ): void {
    const visualId = buildQueueItemId({ type: 'visual', bid, position });
    const item = this.queue.find(i => i.id === visualId);
    if (!item || item.type !== 'visual') {
      return;
    }

    const visual = item as VisualQueueItem;
    if (visual.hasTextAfterVisual === hasTextAfterVisual) {
      return;
    }

    console.log(
      `[Queue] Updating visual expectation: ${visualId}, hasTextAfterVisual: ${hasTextAfterVisual}`,
    );
    visual.hasTextAfterVisual = hasTextAfterVisual;

    // Update the expected audio ID
    if (hasTextAfterVisual) {
      visual.expectedAudioId = buildQueueItemId({
        type: 'audio',
        bid,
        position,
      });
    }
  }

  // ============================================================================
  // Internal Processing
  // ============================================================================

  /**
   * Process queue - FIFO sequential processing
   */
  private processQueue(): void {
    if (this.isPaused || this.isProcessing) {
      return;
    }

    // Initialize current index if needed
    if (this.currentIndex < 0 && this.queue.length > 0) {
      this.currentIndex = 0;
    }

    // Check if queue is completed
    if (this.currentIndex >= this.queue.length) {
      if (this.queue.length > 0 && !this.hasCompleted) {
        console.log('[Queue] Queue completed');
        this.hasCompleted = true;
        this.emit({
          type: 'queue:completed',
          item: this.queue[this.queue.length - 1],
          sessionId: this.sessionIdRef.current,
        });
      }
      return;
    }

    // Get current item
    const currentItem = this.queue[this.currentIndex];
    if (!currentItem) {
      return;
    }

    // Skip already completed items
    if (currentItem.status === 'completed') {
      this.currentIndex++;
      this.processQueue();
      return;
    }

    this.isProcessing = true;

    try {
      // Process based on item type
      if (currentItem.type === 'visual') {
        this.handleVisualItem(currentItem);
      } else if (currentItem.type === 'audio') {
        this.handleAudioItem(currentItem);
      } else if (currentItem.type === 'interaction') {
        this.handleInteractionItem(currentItem);
      }
    } finally {
      this.isProcessing = false;
    }
  }

  /**
   * Handle visual item
   */
  private handleVisualItem(item: VisualQueueItem): void {
    console.log(
      `[Queue] Processing visual: ${item.id}, hasTextAfter: ${item.hasTextAfterVisual}`,
    );

    // Only process if not already in playing/waiting state
    if (item.status === 'playing' || item.status === 'waiting') {
      return;
    }

    if (item.hasTextAfterVisual) {
      // Check if audio is already available
      const audioIdx = this.queue.findIndex(
        i => i.id === item.expectedAudioId && i.status === 'ready',
      );

      if (audioIdx >= 0) {
        // Audio ready, show visual briefly then advance to audio
        item.status = 'playing';
        this.emit({
          type: 'visual:show',
          item: { ...item }, // Clone to prevent mutation after emit
          sessionId: this.sessionIdRef.current,
        });
        // Mark as completed and auto-advance to audio
        item.status = 'completed';
        setTimeout(() => {
          if (!this.isPaused) {
            this.currentIndex++;
            this.processQueue();
          }
        }, 0);
      } else {
        // Wait for audio
        item.status = 'waiting';
        item.waitingStartedAt = Date.now();
        this.emit({
          type: 'visual:show',
          item,
          sessionId: this.sessionIdRef.current,
        });
        this.startAudioWaitTimeout(item);
      }
    } else {
      // Silent visual - no audio expected
      item.status = 'playing';
      this.emit({
        type: 'visual:show',
        item,
        sessionId: this.sessionIdRef.current,
      });
      // Auto-advance after viewing period (managed internally)
      this.clearTimers();
      this.processingTimer = setTimeout(() => {
        if (!this.isPaused) {
          this.advance();
        }
      }, this.silentVisualDuration);
    }
  }

  /**
   * Handle audio item
   */
  private handleAudioItem(item: AudioQueueItem): void {
    console.log(`[Queue] Processing audio: ${item.id}, status: ${item.status}`);

    // Guard: if already playing (e.g., after resume), don't re-emit
    if (item.status === 'playing') {
      return;
    }

    if (item.status === 'ready') {
      item.status = 'playing';
      this.emit({
        type: 'audio:play',
        item,
        sessionId: this.sessionIdRef.current,
      });
      // Audio will call advance() when playback ends
      return;
    }

    // Audio not ready (e.g., arrived early as 'pending' before its visual).
    // Start a wait timeout: if the audio doesn't become ready within the
    // timeout period, skip it to prevent the queue from freezing.
    console.warn(
      `[Queue] Audio ${item.id} not ready (${item.status}), waiting...`,
    );
    item.status = 'waiting';
    this.clearTimers();
    this.processingTimer = setTimeout(() => {
      if (item.status === 'ready') {
        // Audio became ready while waiting
        item.status = 'playing';
        this.emit({
          type: 'audio:play',
          item,
          sessionId: this.sessionIdRef.current,
        });
        return;
      }
      // Audio still not ready, skip it
      console.warn(`[Queue] Audio ${item.id} wait timeout, skipping`);
      item.status = 'timeout';
      this.emit({
        type: 'queue:error',
        item,
        sessionId: this.sessionIdRef.current,
        reason: 'audio_not_ready_timeout',
      });
      this.advance();
    }, this.audioWaitTimeout);
  }

  /**
   * Handle interaction item
   */
  private handleInteractionItem(item: InteractionQueueItem): void {
    console.log(`[Queue] Processing interaction: ${item.id}`);

    item.status = 'playing';
    this.emit({
      type: 'interaction:show',
      item,
      sessionId: this.sessionIdRef.current,
    });
    // Interaction will call advance() when user completes it
  }

  /**
   * Start audio wait timeout for visual with hasTextAfterVisual
   */
  private startAudioWaitTimeout(item: VisualQueueItem): void {
    this.clearTimers();
    this.processingTimer = setTimeout(() => {
      console.warn(
        `[Queue] Audio wait timeout for visual ${item.id} after ${this.audioWaitTimeout}ms`,
      );
      item.status = 'timeout';
      this.emit({
        type: 'queue:error',
        item,
        sessionId: this.sessionIdRef.current,
        reason: 'audio_timeout',
      });
      // Auto-advance to prevent queue freeze
      this.advance();
    }, this.audioWaitTimeout);
  }

  /**
   * Clear all timers
   */
  private clearTimers(): void {
    if (this.processingTimer) {
      clearTimeout(this.processingTimer);
      this.processingTimer = null;
    }
  }
}

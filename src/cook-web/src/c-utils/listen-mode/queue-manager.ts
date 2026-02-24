import { normalizeListenAudioPosition } from '@/c-utils/listen-orchestrator';
import type { ChatContentItem } from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';

// Queue item types
type QueueItemType = 'visual' | 'audio' | 'interaction';

// Queue item status lifecycle
type QueueItemStatus =
  | 'pending' // Enqueued, waiting for dependencies
  | 'waiting' // Active, waiting for resource (e.g., audio)
  | 'ready' // Ready to play
  | 'playing' // Currently playing
  | 'completed' // Finished
  | 'timeout'; // Timed out waiting

// Base queue item interface
interface BaseQueueItem {
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
  hasTextAfterVisual: boolean; // If true, audio is guaranteed (must wait)
  expectedAudioId: string; // ID of expected audio item
}

// Audio segment data from SSE
export interface AudioSegmentData {
  audio_segment?: string; // Base64 encoded audio data
  audio_url?: string; // Final OSS URL
  is_final?: boolean; // Whether this is the final segment
  duration_ms?: number; // Segment or final clip duration in ms
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
}

type QueueItem = VisualQueueItem | AudioQueueItem | InteractionQueueItem;

// Queue event types
type QueueEventType =
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

// Configuration for queue manager
interface ListenQueueManagerConfig {
  audioWaitTimeout: number; // Default 15000ms
  silentVisualDuration: number; // Default 5000ms — auto-advance delay for silent visuals
  sessionIdRef: { current: number };
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
  private sessionIdRef: { current: number };
  private processingTimer: NodeJS.Timeout | null = null;
  private audioWaitTimeout: number;
  private silentVisualDuration: number;
  private isProcessing: boolean = false;
  private pendingProcess: boolean = false;
  private isPaused: boolean = false;
  private hasCompleted: boolean = false;
  private listeners: Map<QueueEventType, Set<(event: QueueEvent) => void>> =
    new Map();

  constructor(config: ListenQueueManagerConfig) {
    this.sessionIdRef = config.sessionIdRef;
    this.audioWaitTimeout = config.audioWaitTimeout;
    this.silentVisualDuration = config.silentVisualDuration;
  }

  // ============================================================================
  // Event Emitter Methods
  // ============================================================================

  on(eventType: QueueEventType, listener: (event: QueueEvent) => void): void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(listener);
  }

  off(eventType: QueueEventType, listener: (event: QueueEvent) => void): void {
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
    item: Omit<VisualQueueItem, 'id' | 'status' | 'enqueuedAt' | 'type'>,
  ): void {
    const id = buildQueueItemId({
      type: 'visual',
      bid: item.generatedBlockBid,
      position: item.position,
    });

    // Check for duplicate
    const existing = this.queue.find(i => i.id === id);
    if (existing) {
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

    // Note: Don't auto-trigger processing here. Use start() to begin processing.
  }

  /**
   * Enqueue an interaction item
   */
  enqueueInteraction(
    item: Omit<InteractionQueueItem, 'id' | 'status' | 'enqueuedAt' | 'type'>,
  ): void {
    const id = buildQueueItemId({
      type: 'interaction',
      bid: item.generatedBlockBid,
    });

    // Check for duplicate
    const existing = this.queue.find(i => i.id === id);
    if (existing) {
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
      if (
        Number.isFinite(audioData.duration_ms) &&
        Number(audioData.duration_ms) > 0
      ) {
        existing.durationMs = Number(audioData.duration_ms);
      }
      // Only promote to 'ready' from early states — never regress 'playing' or 'completed'
      if (existing.status === 'pending' || existing.status === 'waiting') {
        existing.status = 'ready';
      }

      // If this audio item was the current item waiting for data, trigger
      // processing so it can now play.
      if (
        wasWaiting &&
        !this.isPaused &&
        this.currentIndex === existingAudioIdx
      ) {
        this.clearTimers();
        this.processQueue();
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
        durationMs:
          Number.isFinite(audioData.duration_ms) &&
          Number(audioData.duration_ms) > 0
            ? Number(audioData.duration_ms)
            : undefined,
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

        // If visual is waiting for this audio, mark it as completed and trigger processing
        const visual = this.queue[visualIdx] as VisualQueueItem;
        if (visual.status === 'waiting') {
          visual.status = 'completed';
          this.clearTimers(); // Clear audio wait timeout

          // When the visual was the current item (currentIndex === visualIdx),
          // the index was NOT adjusted above (visualIdx < insertIdx), so we
          // advance past the completed visual to the newly inserted audio.
          if (!this.isPaused && this.currentIndex === visualIdx) {
            this.currentIndex++;
            this.processQueue();
          }
        }
      } else {
        // Visual not enqueued yet - audio arrived early
        // Enqueue and mark pending (will be processed when visual arrives)
        audioItem.status = 'pending';
        this.queue.push(audioItem);
      }
    }
  }

  // ============================================================================
  // Queue Control
  // ============================================================================

  /**
   * Pause queue processing
   */
  pause(): void {
    this.isPaused = true;
    this.clearTimers();
  }

  /**
   * Resume queue processing
   */
  resume(): void {
    this.isPaused = false;
    this.processQueue();
  }

  /**
   * Reset queue (clear all items and state)
   */
  reset(): void {
    this.queue = [];
    this.currentIndex = -1;
    this.isProcessing = false;
    this.pendingProcess = false;
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
    if (this.currentIndex >= 0 && this.currentIndex < this.queue.length) {
      const current = this.queue[this.currentIndex];
      // Only mark as completed if not already in a terminal state (completed, timeout)
      if (current.status !== 'completed' && current.status !== 'timeout') {
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

  getCurrentIndex(): number {
    return this.currentIndex;
  }

  getQueueSnapshot(): QueueItem[] {
    return [...this.queue];
  }

  /**
   * Remap queue item pages in-place.
   * Used when runtime rendering prunes empty visual slides and playback should
   * target the nearest effective page instead of stale pre-render indices.
   */
  remapPages(mapper: (page: number) => number): void {
    this.queue = this.queue.map(item => {
      const nextPage = mapper(item.page);
      if (!Number.isFinite(nextPage) || nextPage < 0) {
        return item;
      }
      if (nextPage === item.page) {
        return item;
      }
      return {
        ...item,
        page: nextPage,
      };
    });
  }

  /**
   * Start processing from a specific index (used for prev/next navigation)
   */
  startFromIndex(index: number): void {
    const clampedIndex = Math.max(0, Math.min(index, this.queue.length - 1));
    if (this.queue.length === 0) {
      return;
    }

    this.currentIndex = clampedIndex;
    this.isPaused = false;
    this.hasCompleted = false;
    this.clearTimers();

    // Mark all items before the target as completed
    for (let i = 0; i < clampedIndex; i++) {
      if (
        this.queue[i].status !== 'completed' &&
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

    const visual = item;
    if (visual.hasTextAfterVisual === hasTextAfterVisual) {
      return;
    }
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
    if (this.isPaused) {
      return;
    }
    if (this.isProcessing) {
      this.pendingProcess = true;
      return;
    }

    // Initialize current index if needed
    if (this.currentIndex < 0 && this.queue.length > 0) {
      this.currentIndex = 0;
    }

    // Check if queue is completed
    if (this.currentIndex >= this.queue.length) {
      if (this.queue.length > 0 && !this.hasCompleted) {
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
      if (this.pendingProcess && !this.isPaused) {
        this.pendingProcess = false;
        this.processQueue();
      }
    }
  }

  /**
   * Handle visual item
   */
  private handleVisualItem(item: VisualQueueItem): void {
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
        if (!this.isPaused) {
          this.currentIndex++;
          this.processQueue();
        }
      } else {
        // Wait for audio
        item.status = 'waiting';
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

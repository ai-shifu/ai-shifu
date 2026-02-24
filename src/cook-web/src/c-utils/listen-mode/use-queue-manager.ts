import { useRef, useCallback, useEffect, useMemo } from 'react';
import {
  ListenQueueManager,
  buildQueueItemId,
  type QueueEvent,
  type AudioSegmentData,
} from './queue-manager';
import type { ChatContentItem } from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';

interface UseQueueManagerParams {
  onVisualShow: (event: QueueEvent) => void;
  onAudioPlay: (event: QueueEvent) => void;
  onInteractionShow: (event: QueueEvent) => void;
  onQueueCompleted: (event: QueueEvent) => void;
}

interface QueueManagerActions {
  enqueueVisual: (params: {
    generatedBlockBid: string;
    position?: number;
    page: number;
    hasTextAfterVisual: boolean;
  }) => void;

  upsertAudio: (
    blockBid: string,
    position: number,
    audioData: AudioSegmentData,
  ) => void;

  enqueueInteraction: (params: {
    generatedBlockBid: string;
    page: number;
    contentItem: ChatContentItem;
  }) => void;

  pause: () => void;
  resume: () => void;
  reset: () => void;
  advance: () => void;
  startFromIndex: (index: number) => void;
  updateVisualExpectation: (
    bid: string,
    position: number,
    hasTextAfterVisual: boolean,
  ) => void;
  remapPages: (mapper: (page: number) => number) => void;

  getQueueSnapshot: () => ReturnType<ListenQueueManager['getQueueSnapshot']>;
  getCurrentIndex: () => number;
}

/**
 * Custom hook to manage ListenQueueManager lifecycle and provide actions
 *
 * This hook creates and manages a queue manager instance, handles event subscriptions,
 * and provides a clean API for queue operations.
 */
export function useQueueManager(
  params: UseQueueManagerParams,
): QueueManagerActions {
  const { onVisualShow, onAudioPlay, onInteractionShow, onQueueCompleted } =
    params;

  const sessionIdRef = useRef(1);
  const queueManagerRef = useRef<ListenQueueManager | null>(null);

  // Initialize queue manager and ensure timers/listeners are cleaned on unmount.
  useEffect(() => {
    const manager = new ListenQueueManager({
      audioWaitTimeout: 15000,
      silentVisualDuration: 5000,
      sessionIdRef,
    });
    queueManagerRef.current = manager;

    return () => {
      manager.destroy();
      if (queueManagerRef.current === manager) {
        queueManagerRef.current = null;
      }
    };
  }, []);

  // Subscribe to events (re-subscribe when handlers change)
  useEffect(() => {
    if (!queueManagerRef.current) {
      return;
    }

    const manager = queueManagerRef.current;

    manager.on('visual:show', onVisualShow);
    manager.on('audio:play', onAudioPlay);
    manager.on('interaction:show', onInteractionShow);
    manager.on('queue:completed', onQueueCompleted);

    return () => {
      manager.off('visual:show', onVisualShow);
      manager.off('audio:play', onAudioPlay);
      manager.off('interaction:show', onInteractionShow);
      manager.off('queue:completed', onQueueCompleted);
    };
  }, [onVisualShow, onAudioPlay, onInteractionShow, onQueueCompleted]);

  // Queue actions
  const enqueueVisual = useCallback(
    (params: Parameters<QueueManagerActions['enqueueVisual']>[0]) => {
      if (!queueManagerRef.current) {
        return;
      }

      const expectedAudioId = buildQueueItemId({
        type: 'audio',
        bid: params.generatedBlockBid,
        position: params.position,
      });

      queueManagerRef.current.enqueueVisual({
        generatedBlockBid: params.generatedBlockBid,
        position: params.position ?? 0,
        page: params.page,
        hasTextAfterVisual: params.hasTextAfterVisual,
        expectedAudioId,
      });
    },
    [],
  );

  const upsertAudio = useCallback(
    (blockBid: string, position: number, audioData: AudioSegmentData) => {
      if (!queueManagerRef.current) {
        return;
      }

      queueManagerRef.current.upsertAudio(blockBid, position, audioData);
    },
    [],
  );

  const enqueueInteraction = useCallback(
    (params: Parameters<QueueManagerActions['enqueueInteraction']>[0]) => {
      if (!queueManagerRef.current) {
        return;
      }

      queueManagerRef.current.enqueueInteraction({
        generatedBlockBid: params.generatedBlockBid,
        page: params.page,
        contentItem: params.contentItem,
      });
    },
    [],
  );

  const pause = useCallback(() => {
    if (!queueManagerRef.current) {
      return;
    }
    queueManagerRef.current.pause();
  }, []);

  const resume = useCallback(() => {
    if (!queueManagerRef.current) {
      return;
    }
    queueManagerRef.current.resume();
  }, []);

  const reset = useCallback(() => {
    if (!queueManagerRef.current) {
      return;
    }
    sessionIdRef.current += 1;
    queueManagerRef.current.reset();
  }, []);

  const advance = useCallback(() => {
    if (!queueManagerRef.current) {
      return;
    }
    queueManagerRef.current.advance();
  }, []);

  const startFromIndex = useCallback((index: number) => {
    if (!queueManagerRef.current) {
      return;
    }
    sessionIdRef.current += 1;
    queueManagerRef.current.startFromIndex(index);
  }, []);

  const updateVisualExpectation = useCallback(
    (bid: string, position: number, hasTextAfterVisual: boolean) => {
      if (!queueManagerRef.current) {
        return;
      }
      queueManagerRef.current.updateVisualExpectation(
        bid,
        position,
        hasTextAfterVisual,
      );
    },
    [],
  );

  const remapPages = useCallback(
    (mapper: Parameters<QueueManagerActions['remapPages']>[0]) => {
      if (!queueManagerRef.current) {
        return;
      }
      queueManagerRef.current.remapPages(mapper);
    },
    [],
  );

  const getQueueSnapshot = useCallback(() => {
    if (!queueManagerRef.current) {
      return [];
    }
    return queueManagerRef.current.getQueueSnapshot();
  }, []);

  const getCurrentIndex = useCallback(() => {
    if (!queueManagerRef.current) {
      return -1;
    }
    return queueManagerRef.current.getCurrentIndex();
  }, []);

  return useMemo(
    () => ({
      enqueueVisual,
      upsertAudio,
      enqueueInteraction,
      pause,
      resume,
      reset,
      advance,
      startFromIndex,
      updateVisualExpectation,
      remapPages,
      getQueueSnapshot,
      getCurrentIndex,
    }),
    [
      enqueueVisual,
      upsertAudio,
      enqueueInteraction,
      pause,
      resume,
      reset,
      advance,
      startFromIndex,
      updateVisualExpectation,
      remapPages,
      getQueueSnapshot,
      getCurrentIndex,
    ],
  );
}

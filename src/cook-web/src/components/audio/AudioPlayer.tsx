'use client';

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Volume2, Pause, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import type { AudioSegment } from '@/c-utils/audio-utils';
import { emitListenDebugAlert } from '@/c-utils/listen-debug';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export interface AudioPlayerProps {
  /** OSS URL when audio is complete */
  audioUrl?: string;
  /** Base64 audio segments during streaming */
  streamingSegments?: AudioSegment[];
  /** Whether audio is still streaming */
  isStreaming?: boolean;
  /** Optional playlist for sequential playback */
  playlist?: AudioPlaylistItem[];
  /** Start index within playlist */
  playlistStartIndex?: number;
  /** Auto-play next item in playlist */
  isAutoPlayNext?: boolean;
  /** Whether the current page is in preview mode (e.g. `?preview=true`) */
  previewMode?: boolean;
  /** Keep the control visible even when no audio is available yet */
  alwaysVisible?: boolean;
  /** Disable the player */
  disabled?: boolean;
  /** Request TTS synthesis when no audio is available yet */
  onRequestAudio?: () => Promise<any>;
  /** Icon size */
  size?: number;
  /** Additional CSS classes */
  className?: string;
  /** Callback when play state changes */
  onPlayStateChange?: (isPlaying: boolean) => void;
  /** Callback when playback reaches the natural end */
  onEnded?: () => void;
  /** Auto-play when new audio content arrives */
  autoPlay?: boolean;
  /** Content identifier for resetting internal state between items */
  contentKey?: string | null;
  /** Notify when playlist item changes */
  onPlaylistItemChange?: (
    index: number,
    item: AudioPlaylistItem | null,
  ) => void;
}

export interface AudioPlayerHandle {
  togglePlay: () => void;
  play: () => void;
  pause: (options?: { traceId?: string }) => void;
}

export type AudioPlaylistItem = {
  audioUrl?: string;
  streamingSegments?: AudioSegment[];
  isStreaming?: boolean;
  contentKey?: string | null;
  itemId?: string;
};

/**
 * Audio player component for TTS playback.
 *
 * Supports two modes:
 * 1. Streaming mode: Plays base64-encoded audio segments as they arrive
 * 2. Complete mode: Plays from OSS URL after all segments are uploaded
 */
function AudioPlayerBase(
  {
    audioUrl,
    streamingSegments = [],
    isStreaming = false,
    playlist,
    playlistStartIndex,
    isAutoPlayNext = true,
    previewMode = false,
    alwaysVisible = false,
    disabled = false,
    onRequestAudio,
    size = 16,
    className,
    onPlayStateChange,
    onEnded,
    autoPlay = false,
    contentKey,
    onPlaylistItemChange,
  }: AudioPlayerProps,
  ref: React.ForwardedRef<AudioPlayerHandle>,
) {
  const { t } = useTranslation();
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  // Track if we're waiting for the next segment during streaming
  const [isWaitingForSegment, setIsWaitingForSegment] = useState(false);
  const [localAudioUrl, setLocalAudioUrl] = useState<string | undefined>(
    undefined,
  );

  const audioRef = useRef<HTMLAudioElement | null>(null);
  // Track how many seconds have been played from streaming segments in this play session.
  const playedSecondsRef = useRef(0);
  const playSessionRef = useRef(0);
  const pendingStreamRef = useRef(false);
  const isPausedRef = useRef(false);
  const pausedAtRef = useRef(0);
  const pausedSegmentIndexRef = useRef(0);
  const segmentStartOffsetRef = useRef(0);
  const playModeRef = useRef<'url' | 'segment' | null>(null);
  const segmentUrlMapRef = useRef<Map<number, string>>(new Map());
  const playerIdRef = useRef(Math.random().toString(36).slice(2, 8));
  const contentKeyRef = useRef(contentKey ?? null);
  const playlistRef = useRef<AudioPlaylistItem[]>([]);
  const playlistIndexRef = useRef(0);
  const playlistItemRef = useRef<AudioPlaylistItem | null>(null);
  const isAutoPlayNextRef = useRef(isAutoPlayNext);
  const playFromUrlRef = useRef<(startAtSeconds?: number) => void>(() => {});
  const playFromSegmentsRef = useRef<(forceStreaming?: boolean) => void>(
    () => {},
  );

  const [playlistIndex, setPlaylistIndex] = useState(
    Math.max(0, playlistStartIndex ?? 0),
  );
  const [playlistItem, setPlaylistItem] = useState<AudioPlaylistItem | null>(
    null,
  );

  const activeAudioUrl = playlistItem?.audioUrl ?? audioUrl;
  const activeStreamingSegments =
    playlistItem?.streamingSegments ?? streamingSegments;
  const activeIsStreaming = Boolean(playlistItem?.isStreaming ?? isStreaming);
  const activeContentKey = playlistItem?.contentKey ?? contentKey ?? null;
  const isPlaylistActive = Boolean(playlist && playlist.length > 0);

  const effectiveAudioUrl = activeAudioUrl || localAudioUrl;

  const audioUrlRef = useRef(effectiveAudioUrl);
  audioUrlRef.current = effectiveAudioUrl;

  // Use refs to track playback state across async callbacks
  const currentSegmentIndexRef = useRef(0);
  const isPlayingRef = useRef(false);
  const segmentsRef = useRef<AudioSegment[]>([]);
  const isStreamingRef = useRef(false);

  // Keep refs in sync with props/state
  segmentsRef.current = activeStreamingSegments;
  isStreamingRef.current = activeIsStreaming;
  isAutoPlayNextRef.current = isAutoPlayNext;

  // Use ref for callback to avoid stale closures
  const onPlayStateChangeRef = useRef(onPlayStateChange);
  onPlayStateChangeRef.current = onPlayStateChange;

  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;

  const onPlaylistItemChangeRef = useRef(onPlaylistItemChange);
  onPlaylistItemChangeRef.current = onPlaylistItemChange;

  // Track auto-play state per content
  const prevAutoPlayRef = useRef(autoPlay);
  const hasAutoPlayedForCurrentContentRef = useRef(false);

  const ensureAudioElement = useCallback(() => {
    if (!audioRef.current) {
      audioRef.current = new Audio();
      audioRef.current.preload = 'auto';
      audioRef.current.setAttribute('playsinline', 'true');
    }
    return audioRef.current;
  }, []);

  const resolveSegmentMime = useCallback((audioData: string) => {
    const head = audioData.slice(0, 8);
    if (
      head.startsWith('SUQz') ||
      head.startsWith('////') ||
      head.startsWith('//uQ')
    ) {
      return 'audio/mpeg';
    }
    if (head.startsWith('UklGR')) {
      return 'audio/wav';
    }
    if (head.startsWith('T2dn')) {
      return 'audio/ogg';
    }
    return 'audio/mpeg';
  }, []);

  const getSegmentUrl = useCallback(
    (segment: AudioSegment) => {
      const key = segment.segmentIndex;
      const cached = segmentUrlMapRef.current.get(key);
      if (cached) {
        return cached;
      }
      const mime = resolveSegmentMime(segment.audioData);
      const binary = atob(segment.audioData);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: mime });
      const url = URL.createObjectURL(blob);
      segmentUrlMapRef.current.set(key, url);
      return url;
    },
    [resolveSegmentMime],
  );

  const revokeSegmentUrls = useCallback(() => {
    segmentUrlMapRef.current.forEach(url => {
      URL.revokeObjectURL(url);
    });
    segmentUrlMapRef.current.clear();
  }, []);

  const getSegmentDurationSeconds = useCallback((segment?: AudioSegment) => {
    if (segment?.durationMs && segment.durationMs > 0) {
      return segment.durationMs / 1000;
    }
    const audio = audioRef.current;
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0) {
      return audio.duration;
    }
    return 0;
  }, []);

  // Check if we have audio to play
  const hasAudio =
    Boolean(effectiveAudioUrl) || activeStreamingSegments.length > 0;

  // Use OSS URL if available and streaming is complete
  const useOssUrl = Boolean(effectiveAudioUrl) && !activeIsStreaming;

  const updatePlaylistItem = useCallback(
    (nextIndex: number, nextItem: AudioPlaylistItem | null) => {
      playlistIndexRef.current = nextIndex;
      setPlaylistIndex(nextIndex);
      playlistItemRef.current = nextItem;
      setPlaylistItem(nextItem);
      emitListenDebugAlert('playlist-item-change', {
        playerId: playerIdRef.current,
        nextIndex,
        itemId: nextItem?.itemId,
        hasUrl: Boolean(nextItem?.audioUrl),
        segments: nextItem?.streamingSegments?.length ?? 0,
        isStreaming: Boolean(nextItem?.isStreaming),
      });
      onPlaylistItemChangeRef.current?.(nextIndex, nextItem);
    },
    [],
  );

  const isPlaylistItemPlayable = useCallback((item?: AudioPlaylistItem | null) => {
    if (!item) {
      return false;
    }
    return Boolean(item.audioUrl) ||
      Boolean(item.streamingSegments && item.streamingSegments.length > 0) ||
      Boolean(item.isStreaming);
  }, []);

  const resetForNextItem = useCallback(() => {
    setLocalAudioUrl(undefined);
    currentSegmentIndexRef.current = 0;
    playedSecondsRef.current = 0;
    isPausedRef.current = false;
    pendingStreamRef.current = false;
    pausedAtRef.current = 0;
    pausedSegmentIndexRef.current = 0;
    segmentStartOffsetRef.current = 0;
    playModeRef.current = null;
    revokeSegmentUrls();
    hasAutoPlayedForCurrentContentRef.current = false;
  }, [revokeSegmentUrls]);

  const startPlaySession = useCallback(() => {
    playSessionRef.current += 1;
    return playSessionRef.current;
  }, []);

  const isSessionActive = useCallback(
    (sessionId: number) => playSessionRef.current === sessionId,
    [],
  );

  // Cleanup audio resources
  const cleanupAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
  }, []);

  const stopPlayback = useCallback(() => {
    playSessionRef.current += 1;
    pendingStreamRef.current = false;
    isPausedRef.current = false;
    pausedAtRef.current = 0;
    pausedSegmentIndexRef.current = 0;
    segmentStartOffsetRef.current = 0;
    playModeRef.current = null;
    revokeSegmentUrls();
    cleanupAudio();
    setIsPlaying(false);
    isPlayingRef.current = false;
    setIsLoading(false);
    setIsWaitingForSegment(false);
    onPlayStateChangeRef.current?.(false);
    releaseExclusive();
  }, [cleanupAudio, releaseExclusive, revokeSegmentUrls]);

  const finalizeTrackState = useCallback(() => {
    setIsPlaying(false);
    isPlayingRef.current = false;
    setIsLoading(false);
    setIsWaitingForSegment(false);
    onPlayStateChangeRef.current?.(false);
  }, []);

  const playNextFromPlaylist = useCallback(() => {
    const list = playlistRef.current;
    if (!list.length) {
      emitListenDebugAlert('playlist-empty', {
        playerId: playerIdRef.current,
      });
      return false;
    }
    const nextIndex = playlistIndexRef.current + 1;
    if (nextIndex >= list.length) {
      emitListenDebugAlert('playlist-end', {
        playerId: playerIdRef.current,
        currentIndex: playlistIndexRef.current,
        listLength: list.length,
      });
      return false;
    }
    const nextItem = list[nextIndex] ?? null;
    const isPlayable = isPlaylistItemPlayable(nextItem);
    emitListenDebugAlert('playlist-next', {
      playerId: playerIdRef.current,
      currentIndex: playlistIndexRef.current,
      nextIndex,
      itemId: nextItem?.itemId,
      hasUrl: Boolean(nextItem?.audioUrl),
      segments: nextItem?.streamingSegments?.length ?? 0,
      isStreaming: Boolean(nextItem?.isStreaming),
      isPlayable,
    });
    updatePlaylistItem(nextIndex, nextItem);
    resetForNextItem();
    cleanupAudio();

    const nextAudioUrl = nextItem?.audioUrl;
    const nextSegments = nextItem?.streamingSegments ?? [];
    const nextIsStreaming = Boolean(nextItem?.isStreaming);

    audioUrlRef.current = nextAudioUrl || undefined;
    segmentsRef.current = nextSegments;
    isStreamingRef.current = nextIsStreaming;

    if (nextAudioUrl && !nextIsStreaming) {
      // Mark as auto-played so the autoPlay effect does not double-trigger.
      hasAutoPlayedForCurrentContentRef.current = true;
      playFromUrlRef.current();
      return true;
    }
    if (nextSegments.length > 0 || nextIsStreaming) {
      // Mark as auto-played so the autoPlay effect does not double-trigger.
      hasAutoPlayedForCurrentContentRef.current = true;
      playFromSegmentsRef.current();
      return true;
    }
    emitListenDebugAlert('playlist-next-pending', {
      playerId: playerIdRef.current,
      nextIndex,
      itemId: nextItem?.itemId,
    });
    releaseExclusive();
    return true;
  }, [
    cleanupAudio,
    isPlaylistItemPlayable,
    releaseExclusive,
    resetForNextItem,
    updatePlaylistItem,
  ]);

  const handleTrackEnded = useCallback(() => {
    emitListenDebugAlert('track-ended', {
      playerId: playerIdRef.current,
      playlistIndex: playlistIndexRef.current,
      isAutoPlayNext: isAutoPlayNextRef.current,
      hasPlaylist: Boolean(playlistRef.current.length),
    });
    if (isAutoPlayNextRef.current && playNextFromPlaylist()) {
      return;
    }
    onEndedRef.current?.();
    releaseExclusive();
  }, [playNextFromPlaylist, releaseExclusive]);

  const pausePlayback = useCallback(
    (options?: { traceId?: string }) => {
      const htmlAudio = audioRef.current;
      const wasHtmlPlaying = Boolean(htmlAudio && !htmlAudio.paused);
      const htmlTime = wasHtmlPlaying ? (htmlAudio?.currentTime ?? 0) : null;
      const shouldPause =
        isPlayingRef.current || wasHtmlPlaying || isWaitingForSegment;
      if (!shouldPause) {
        // console.log('audio-player-pause-skip', {
        //   id: playerIdRef.current,
        //   traceId: options?.traceId,
        //   isPlaying: isPlayingRef.current,
        //   hasSourceNode: Boolean(sourceNodeRef.current),
        //   htmlAudioPaused: audioRef.current?.paused,
        //   audioUrl: audioUrlRef.current,
        //   activeNodes: activeSourceNodesRef.current.size,
        //   wasHtmlPlaying,
        // });
        return;
      }

      // console.log('audio-player-stop-others', {
      //   id: playerIdRef.current,
      //   traceId: options?.traceId,
      //   isPlaying: isPlayingRef.current,
      //   activeNodes: activeSourceNodesRef.current.size,
      // });
      requestExclusive(() => {});

      // console.log('audio-player-pause', {
      //   id: playerIdRef.current,
      //   traceId: options?.traceId,
      //   isPlaying: isPlayingRef.current,
      //   htmlAudioPaused: audioRef.current?.paused,
      //   audioUrl: audioUrlRef.current,
      //   wasHtmlPlaying,
      //   htmlTime,
      // });
      playSessionRef.current += 1;
      isPausedRef.current = true;
      setIsPlaying(false);
      isPlayingRef.current = false;
      setIsLoading(false);
      setIsWaitingForSegment(false);
      onPlayStateChangeRef.current?.(false);

      if (wasHtmlPlaying && htmlAudio) {
        const safeHtmlTime = Number.isFinite(htmlTime as number)
          ? Math.max(0, htmlTime as number)
          : 0;
        pausedAtRef.current = safeHtmlTime;
        htmlAudio.pause();
      } else if (Number.isFinite(htmlTime as number)) {
        pausedAtRef.current = Math.max(0, htmlTime as number);
      }

      pausedSegmentIndexRef.current =
        playModeRef.current === 'segment'
          ? currentSegmentIndexRef.current
          : 0;

      releaseExclusive();
    },
    [isWaitingForSegment, releaseExclusive, requestExclusive],
  );

  // Play audio from OSS URL
  const playFromUrl = useCallback(
    (startAtSeconds: number = 0) => {
      const url = audioUrlRef.current;
      if (!url) return;

      isPausedRef.current = false;
      pausedAtRef.current = 0;
      pausedSegmentIndexRef.current = 0;
      segmentStartOffsetRef.current = 0;
      playModeRef.current = 'url';

      const sessionId = startPlaySession();
      requestExclusive(stopPlayback);

      const audio = ensureAudioElement();
      emitListenDebugAlert('playFromUrl', {
        playerId: playerIdRef.current,
        sessionId,
        url,
        startAtSeconds,
      });
      audio.onended = () => {
        if (!isSessionActive(sessionId)) return;
        emitListenDebugAlert('playFromUrl-ended', {
          playerId: playerIdRef.current,
          sessionId,
          url,
        });
        finalizeTrackState();
        handleTrackEnded();
      };
      audio.onerror = () => {
        if (!isSessionActive(sessionId)) return;
        emitListenDebugAlert('playFromUrl-error', {
          playerId: playerIdRef.current,
          sessionId,
          url,
          errorCode: audio.error?.code,
        });
        setIsPlaying(false);
        isPlayingRef.current = false;
        setIsLoading(false);
        setIsWaitingForSegment(false);
        onPlayStateChangeRef.current?.(false);
        releaseExclusive();
      };
      audio.oncanplay = () => {
        if (!isSessionActive(sessionId)) return;
        setIsLoading(false);
      };

      audio.src = url;
      setIsLoading(true);
      setIsWaitingForSegment(false);

      const seekTarget = Number.isFinite(startAtSeconds)
        ? Math.max(0, startAtSeconds)
        : 0;
      try {
        if (seekTarget > 0) {
          audio.currentTime = seekTarget;
        }
      } catch {
        // Some browsers require metadata before seeking; we'll best-effort seek later.
      }

      audio
        .play()
        .then(() => {
          if (!isSessionActive(sessionId)) return;
          setIsPlaying(true);
          isPlayingRef.current = true;
          onPlayStateChangeRef.current?.(true);
        })
        .catch(err => {
          if (!isSessionActive(sessionId)) return;
          emitListenDebugAlert('playFromUrl-rejected', {
            playerId: playerIdRef.current,
            sessionId,
            url,
            errorName: err?.name,
            errorMessage: err?.message,
          });
          console.error('Failed to play audio:', err);
          setIsPlaying(false);
          isPlayingRef.current = false;
          setIsLoading(false);
          setIsWaitingForSegment(false);
          onPlayStateChangeRef.current?.(false);
          if (err instanceof DOMException && err.name === 'NotAllowedError') {
            isPausedRef.current = true;
          }
          releaseExclusive();
        });
    },
    [
      finalizeTrackState,
      handleTrackEnded,
      isSessionActive,
      releaseExclusive,
      requestExclusive,
      startPlaySession,
      stopPlayback,
    ],
  );

  // Play a single segment by index
  const playSegmentByIndex = useCallback(
    async function playSegmentByIndex(
      index: number,
      sessionId: number,
      startOffsetSeconds: number = 0,
    ) {
      if (!isSessionActive(sessionId)) {
        return;
      }

      const segments = segmentsRef.current;

      // Check if segment is available
      if (index >= segments.length) {
        // Segment not available yet
        if (isStreamingRef.current) {
          // Still streaming, wait for more segments
          setIsWaitingForSegment(true);
          setIsLoading(true);
          setIsPlaying(true);
          isPlayingRef.current = true;
          onPlayStateChangeRef.current?.(true);
          currentSegmentIndexRef.current = index;
          return;
        }
        finalizeTrackState();
        handleTrackEnded();
        return;
      }

      const segment = segments[index];
      const audio = ensureAudioElement();
      playModeRef.current = 'segment';
      currentSegmentIndexRef.current = index;
      segmentStartOffsetRef.current = Number.isFinite(startOffsetSeconds)
        ? Math.max(0, startOffsetSeconds)
        : 0;
      pendingStreamRef.current = false;

      emitListenDebugAlert('playSegment-start', {
        playerId: playerIdRef.current,
        sessionId,
        index,
        segments: segments.length,
        isStreaming: isStreamingRef.current,
      });

      const segmentUrl = getSegmentUrl(segment);
      audio.onended = () => {
        if (!isSessionActive(sessionId)) return;
        emitListenDebugAlert('playSegment-ended', {
          playerId: playerIdRef.current,
          sessionId,
          index,
        });
        const durationSeconds = getSegmentDurationSeconds(segment);
        const offsetSeconds = segmentStartOffsetRef.current;
        playedSecondsRef.current += Math.max(
          0,
          durationSeconds - offsetSeconds,
        );
        segmentStartOffsetRef.current = 0;
        const nextIndex = index + 1;
        currentSegmentIndexRef.current = nextIndex;
        if (nextIndex < segmentsRef.current.length) {
          playSegmentByIndex(nextIndex, sessionId);
          return;
        }
        if (isStreamingRef.current) {
          setIsWaitingForSegment(true);
          setIsLoading(true);
          setIsPlaying(true);
          isPlayingRef.current = true;
          onPlayStateChangeRef.current?.(true);
          return;
        }
        finalizeTrackState();
        handleTrackEnded();
      };
      audio.onerror = () => {
        if (!isSessionActive(sessionId)) return;
        emitListenDebugAlert('playSegment-error', {
          playerId: playerIdRef.current,
          sessionId,
          index,
          errorCode: audio.error?.code,
        });
        console.error('Failed to play audio segment:', audio.error);
        setIsLoading(false);
        setIsWaitingForSegment(false);
        setIsPlaying(false);
        isPlayingRef.current = false;
        onPlayStateChangeRef.current?.(false);
        releaseExclusive();
      };
      audio.oncanplay = () => {
        if (!isSessionActive(sessionId)) return;
        setIsLoading(false);
      };

      try {
        audio.pause();
        audio.src = segmentUrl;
        setIsWaitingForSegment(false);
        setIsLoading(true);
        const seekTarget = Number.isFinite(segmentStartOffsetRef.current)
          ? Math.max(0, segmentStartOffsetRef.current)
          : 0;
        try {
          if (seekTarget > 0) {
            audio.currentTime = seekTarget;
          }
        } catch {
          // Ignore seek errors for streaming segments.
        }
        await audio.play();
        if (!isSessionActive(sessionId)) return;
        setIsPlaying(true);
        isPlayingRef.current = true;
        onPlayStateChangeRef.current?.(true);
      } catch (error) {
        emitListenDebugAlert('playSegment-error', {
          playerId: playerIdRef.current,
          sessionId,
          index,
          errorName: (error as DOMException | Error | undefined)?.name,
          errorMessage: (error as DOMException | Error | undefined)?.message,
        });
        console.error('Failed to play audio segment:', error);
        setIsLoading(false);
        setIsWaitingForSegment(false);
        setIsPlaying(false);
        isPlayingRef.current = false;
        if (error instanceof DOMException && error.name === 'NotAllowedError') {
          isPausedRef.current = true;
          onPlayStateChangeRef.current?.(false);
          releaseExclusive();
          return;
        }
        releaseExclusive();
      }
    },
    [
      ensureAudioElement,
      finalizeTrackState,
      getSegmentDurationSeconds,
      getSegmentUrl,
      handleTrackEnded,
      isSessionActive,
      releaseExclusive,
    ],
  );

  // Start playback from segments
  const playFromSegments = useCallback(
    async (forceStreaming: boolean = false) => {
      const sessionId = startPlaySession();
      requestExclusive(stopPlayback);
      isPausedRef.current = false;
      pausedAtRef.current = 0;
      pausedSegmentIndexRef.current = 0;
      segmentStartOffsetRef.current = 0;
      playModeRef.current = 'segment';

      if (segmentsRef.current.length === 0) {
        if (
          isStreamingRef.current ||
          forceStreaming ||
          pendingStreamRef.current
        ) {
          if (forceStreaming) {
            pendingStreamRef.current = true;
          }
          // No segments yet but streaming, wait
          emitListenDebugAlert('playSegments-wait', {
            playerId: playerIdRef.current,
            sessionId,
            forceStreaming,
          });
          setIsWaitingForSegment(true);
          setIsLoading(true);
          setIsPlaying(true);
          isPlayingRef.current = true;
          currentSegmentIndexRef.current = 0;
          playedSecondsRef.current = 0;
          onPlayStateChangeRef.current?.(true);
          return;
        }
        releaseExclusive();
        return;
      }

      pendingStreamRef.current = false;
      setIsLoading(true);
      currentSegmentIndexRef.current = 0;
      playedSecondsRef.current = 0;
      await playSegmentByIndex(0, sessionId);
    },
    [
      playSegmentByIndex,
      releaseExclusive,
      requestExclusive,
      startPlaySession,
      stopPlayback,
    ],
  );

  useEffect(() => {
    playFromUrlRef.current = playFromUrl;
  }, [playFromUrl]);

  useEffect(() => {
    playFromSegmentsRef.current = playFromSegments;
  }, [playFromSegments]);

  const resumeFromSegments = useCallback(() => {
    const sessionId = startPlaySession();
    requestExclusive(stopPlayback);
    isPausedRef.current = false;
    setIsLoading(true);
    setIsWaitingForSegment(false);
    setIsPlaying(true);
    isPlayingRef.current = true;
    playModeRef.current = 'segment';

    const resumeIndex = pausedSegmentIndexRef.current;
    const segments = segmentsRef.current;

    if (segments.length === 0) {
      if (isStreamingRef.current || pendingStreamRef.current) {
        setIsWaitingForSegment(true);
        return;
      }
      setIsPlaying(false);
      isPlayingRef.current = false;
      setIsLoading(false);
      releaseExclusive();
      return;
    }

    if (resumeIndex >= segments.length) {
      if (isStreamingRef.current) {
        setIsWaitingForSegment(true);
        return;
      }
      setIsPlaying(false);
      isPlayingRef.current = false;
      setIsLoading(false);
      releaseExclusive();
      return;
    }

    playSegmentByIndex(resumeIndex, sessionId, pausedAtRef.current);
  }, [
    playSegmentByIndex,
    releaseExclusive,
    requestExclusive,
    startPlaySession,
    stopPlayback,
  ]);

  // Watch for new segments when waiting
  useEffect(() => {
    if (isWaitingForSegment && isPlayingRef.current) {
      const sessionId = playSessionRef.current;
      if (!isSessionActive(sessionId)) {
        return;
      }
      const nextIndex = currentSegmentIndexRef.current;
      emitListenDebugAlert('segment-wait-tick', {
        playerId: playerIdRef.current,
        sessionId,
        nextIndex,
        segments: activeStreamingSegments.length,
        isStreaming: activeIsStreaming,
      });
      if (nextIndex < activeStreamingSegments.length) {
        // New segment available, continue playback
        pendingStreamRef.current = false;
        playSegmentByIndex(nextIndex, sessionId);
      } else if (!activeIsStreaming) {
        // Streaming finished and no more segments. If final URL exists, continue playback with it.
        if (effectiveAudioUrl) {
          pendingStreamRef.current = false;
          setIsWaitingForSegment(false);
          const startAtSeconds = playedSecondsRef.current;
          playFromUrl(startAtSeconds);
          return;
        }

        if (pendingStreamRef.current) {
          return;
        }

        finalizeTrackState();
        handleTrackEnded();
      }
    }
  }, [
    activeStreamingSegments.length,
    activeIsStreaming,
    isWaitingForSegment,
    isSessionActive,
    playSegmentByIndex,
    effectiveAudioUrl,
    playFromUrl,
    finalizeTrackState,
    handleTrackEnded,
  ]);

  // Handle play/pause toggle
  const togglePlay = useCallback(() => {
    if (isLoading) {
      return;
    }

    if (isPlaying) {
      // Pause
      pausePlayback();
      return;
    } else {
      if (isPausedRef.current) {
        if (playModeRef.current === 'segment') {
          resumeFromSegments();
          return;
        }
        if (useOssUrl && effectiveAudioUrl) {
          playFromUrl(pausedAtRef.current);
          return;
        }
        if (
          activeStreamingSegments.length > 0 ||
          activeIsStreaming ||
          pendingStreamRef.current
        ) {
          resumeFromSegments();
          return;
        }
        if (effectiveAudioUrl) {
          playFromUrl(pausedAtRef.current);
          return;
        }
      }
      // Play
      if (useOssUrl) {
        playFromUrl();
      } else if (
        activeStreamingSegments.length > 0 ||
        activeIsStreaming
      ) {
        playFromSegments();
      } else if (onRequestAudio) {
        pendingStreamRef.current = true;
        const requestSessionId = playSessionRef.current;
        setIsWaitingForSegment(false);
        playFromSegments(true);
        onRequestAudio()
          .then(result => {
            if (playSessionRef.current !== requestSessionId) return;
            const url = result?.audio_url || result?.audioUrl || undefined;
            if (!url) {
              return;
            }
            setLocalAudioUrl(url);
            audioUrlRef.current = url;
          })
          .catch(err => {
            if (playSessionRef.current !== requestSessionId) return;
            console.error('Failed to request audio:', err);
            pendingStreamRef.current = false;
            stopPlayback();
          });
      }
    }
  }, [
    isPlaying,
    isLoading,
    effectiveAudioUrl,
    useOssUrl,
    activeIsStreaming,
    pausePlayback,
    playFromUrl,
    playFromSegments,
    resumeFromSegments,
    activeStreamingSegments.length,
    onRequestAudio,
    stopPlayback,
  ]);

  useImperativeHandle(
    ref,
    () => ({
      togglePlay,
      play: () => {
        if (!isPlayingRef.current) {
          togglePlay();
        }
      },
      pause: (options?: { traceId?: string }) => {
        // console.log('audio-player-ref-pause', {
        //   id: playerIdRef.current,
        //   traceId: options?.traceId,
        //   isPlaying: isPlayingRef.current,
        //   hasSourceNode: Boolean(sourceNodeRef.current),
        //   htmlAudioPaused: audioRef.current?.paused,
        //   audioUrl: audioUrlRef.current,
        //   activeNodes: activeSourceNodesRef.current.size,
        // });
        pausePlayback(options);
      },
    }),
    [pausePlayback, togglePlay],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isPlayingRef.current = false;
      playSessionRef.current += 1;
      pendingStreamRef.current = false;
      cleanupAudio();
      releaseExclusive();
      revokeSegmentUrls();
    };
  }, [cleanupAudio, releaseExclusive, revokeSegmentUrls]);

  useEffect(() => {
    if (!playlist || playlist.length === 0) {
      playlistRef.current = [];
      playlistIndexRef.current = 0;
      updatePlaylistItem(0, null);
      return;
    }

    playlistRef.current = playlist;
    const safeStartIndex = Math.min(
      Math.max(playlistStartIndex ?? playlistIndexRef.current, 0),
      Math.max(playlist.length - 1, 0),
    );
    updatePlaylistItem(safeStartIndex, playlist[safeStartIndex] ?? null);
  }, [playlist, playlistStartIndex, updatePlaylistItem]);

  useEffect(() => {
    if (isPlaylistActive) {
      return;
    }
    const nextKey = contentKey ?? null;
    if (contentKeyRef.current === nextKey) {
      return;
    }
    contentKeyRef.current = nextKey;
    emitListenDebugAlert('contentKey-change', {
      playerId: playerIdRef.current,
      contentKey: nextKey,
    });
    stopPlayback();
    resetForNextItem();
  }, [contentKey, isPlaylistActive, resetForNextItem, stopPlayback]);

  // Auto-play when enabled and audio is available
  useEffect(() => {
    // Reset auto-played flag when autoPlay changes from false to true
    // This allows queue-based playback to trigger
    if (autoPlay && !prevAutoPlayRef.current) {
      hasAutoPlayedForCurrentContentRef.current = false;
    }
    prevAutoPlayRef.current = autoPlay;

    // Auto-play when:
    // 1. autoPlay is true
    // 2. Not currently playing
    // 3. Not disabled
    // 4. Haven't auto-played for this content yet
    // 5. Has audio content or is streaming
    if (
      autoPlay &&
      !isPlaying &&
      !isLoading &&
      !disabled &&
      !hasAutoPlayedForCurrentContentRef.current &&
      !isPausedRef.current
    ) {
      emitListenDebugAlert('autoPlay-trigger', {
        playerId: playerIdRef.current,
        contentKey: activeContentKey,
        useOssUrl,
        hasUrl: Boolean(effectiveAudioUrl),
        isStreaming: activeIsStreaming,
        segments: activeStreamingSegments.length,
        playlistIndex,
      });
      if (useOssUrl && effectiveAudioUrl) {
        hasAutoPlayedForCurrentContentRef.current = true;
        playFromUrl();
      } else if (
        activeStreamingSegments.length > 0 ||
        activeIsStreaming
      ) {
        hasAutoPlayedForCurrentContentRef.current = true;
        playFromSegments();
      }
    }
  }, [
    autoPlay,
    isPlaying,
    isLoading,
    disabled,
    activeStreamingSegments.length,
    activeIsStreaming,
    activeContentKey,
    playlistIndex,
    useOssUrl,
    effectiveAudioUrl,
    playFromSegments,
    playFromUrl,
  ]);

  // Don't render if no audio available and not streaming
  if (!hasAudio && !activeIsStreaming && !alwaysVisible) {
    return null;
  }

  const isButtonDisabled =
    disabled || (!hasAudio && !activeIsStreaming && !onRequestAudio);

  const playLabel = previewMode
    ? t('module.chat.ttsSynthesisPreview')
    : t('module.chat.playAudio');

  const ariaLabel = isLoading
    ? t('module.chat.audioLoading')
    : isPlaying
      ? t('module.chat.pauseAudio')
      : playLabel;

  const button = (
    <button
      type='button'
      aria-label={ariaLabel}
      aria-pressed={isPlaying}
      disabled={isButtonDisabled}
      onClick={togglePlay}
      className={cn(
        'inline-flex items-center justify-center',
        'w-[22px] h-[22px]',
        'rounded',
        'transition-colors duration-200',
        'hover:bg-gray-100',
        isButtonDisabled && 'opacity-50 cursor-not-allowed',
        !isButtonDisabled && 'cursor-pointer',
        className,
      )}
    >
      {isLoading ? (
        <Loader2
          size={size}
          className='animate-spin text-[#55575E]'
        />
      ) : isPlaying ? (
        <Pause
          size={size}
          strokeWidth={2}
          stroke='currentColor'
          fill='currentColor'
          className='text-[#55575E]'
        />
      ) : (
        <Volume2
          size={size}
          strokeWidth={2}
          stroke='currentColor'
          className='text-[#55575E]'
        />
      )}
    </button>
  );

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          {isButtonDisabled ? (
            <span className='inline-flex'>{button}</span>
          ) : (
            button
          )}
        </TooltipTrigger>
        <TooltipContent
          side='top'
          className='bg-black text-white border-none'
        >
          {ariaLabel}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export const AudioPlayer = forwardRef(AudioPlayerBase);

AudioPlayer.displayName = 'AudioPlayer';

export default AudioPlayer;

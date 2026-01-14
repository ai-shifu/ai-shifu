'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Volume2, Pause, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import type { AudioSegment } from '@/c-utils/audio-utils';
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
  /** Auto-play when new audio content arrives */
  autoPlay?: boolean;
}

/**
 * Audio player component for TTS playback.
 *
 * Supports two modes:
 * 1. Streaming mode: Plays base64-encoded audio segments as they arrive
 * 2. Complete mode: Plays from OSS URL after all segments are uploaded
 */
export function AudioPlayer({
  audioUrl,
  streamingSegments = [],
  isStreaming = false,
  previewMode = false,
  alwaysVisible = false,
  disabled = false,
  onRequestAudio,
  size = 16,
  className,
  onPlayStateChange,
  autoPlay = false,
}: AudioPlayerProps) {
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
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  // Track how many seconds have been played from streaming segments in this play session.
  const playedSecondsRef = useRef(0);
  const playSessionRef = useRef(0);
  const pendingStreamRef = useRef(false);

  const effectiveAudioUrl = audioUrl || localAudioUrl;

  const audioUrlRef = useRef(effectiveAudioUrl);
  audioUrlRef.current = effectiveAudioUrl;

  // Use refs to track playback state across async callbacks
  const currentSegmentIndexRef = useRef(0);
  const isPlayingRef = useRef(false);
  const segmentsRef = useRef<AudioSegment[]>([]);
  const isStreamingRef = useRef(false);
  // Lock to prevent concurrent playSegmentByIndex calls
  const isPlayingSegmentRef = useRef(false);

  // Keep refs in sync with props/state
  segmentsRef.current = streamingSegments;
  isStreamingRef.current = isStreaming;

  // Use ref for callback to avoid stale closures
  const onPlayStateChangeRef = useRef(onPlayStateChange);
  onPlayStateChangeRef.current = onPlayStateChange;

  // Check if we have audio to play
  const hasAudio = Boolean(effectiveAudioUrl) || streamingSegments.length > 0;

  // Use OSS URL if available and streaming is complete
  const useOssUrl = Boolean(effectiveAudioUrl) && !isStreaming;

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
    // Release the segment lock
    isPlayingSegmentRef.current = false;
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.stop();
        sourceNodeRef.current.disconnect();
      } catch (e) {
        // Ignore errors when stopping
      }
      sourceNodeRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
  }, []);

  const stopPlayback = useCallback(() => {
    playSessionRef.current += 1;
    pendingStreamRef.current = false;
    cleanupAudio();
    setIsPlaying(false);
    isPlayingRef.current = false;
    setIsLoading(false);
    setIsWaitingForSegment(false);
    onPlayStateChangeRef.current?.(false);
    releaseExclusive();
  }, [cleanupAudio, releaseExclusive]);

  // Play audio from OSS URL
  const playFromUrl = useCallback(
    (startAtSeconds: number = 0) => {
      const url = audioUrlRef.current;
      if (!url) return;

      const sessionId = startPlaySession();
      requestExclusive(stopPlayback);

      if (!audioRef.current) {
        audioRef.current = new Audio();
      }

      const audio = audioRef.current;
      audio.onended = () => {
        if (!isSessionActive(sessionId)) return;
        setIsPlaying(false);
        isPlayingRef.current = false;
        setIsLoading(false);
        setIsWaitingForSegment(false);
        onPlayStateChangeRef.current?.(false);
        releaseExclusive();
      };
      audio.onerror = () => {
        if (!isSessionActive(sessionId)) return;
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
          console.error('Failed to play audio:', err);
          setIsPlaying(false);
          isPlayingRef.current = false;
          setIsLoading(false);
          setIsWaitingForSegment(false);
          releaseExclusive();
        });
    },
    [
      isSessionActive,
      releaseExclusive,
      requestExclusive,
      startPlaySession,
      stopPlayback,
    ],
  );

  // Play a single segment by index
  const playSegmentByIndex = useCallback(
    async function playSegmentByIndex(index: number, sessionId: number) {
      if (!isSessionActive(sessionId)) {
        isPlayingSegmentRef.current = false;
        return;
      }

      // Prevent concurrent calls - if already playing a segment, skip
      if (isPlayingSegmentRef.current) {
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
          currentSegmentIndexRef.current = index;
          return;
        } else {
          // Streaming is complete and we reached the end of the received segments.
          // Do NOT auto-switch to the final URL here: providers may report 0/incorrect
          // `durationMs` per segment, which can cause overlap/replay when seeking.
          setIsPlaying(false);
          isPlayingRef.current = false;
          setIsLoading(false);
          setIsWaitingForSegment(false);
          onPlayStateChangeRef.current?.(false);
          releaseExclusive();
          return;
        }
      }

      // Acquire lock
      pendingStreamRef.current = false;
      isPlayingSegmentRef.current = true;

      try {
        setIsWaitingForSegment(false);
        setIsLoading(true);

        // Initialize AudioContext if needed
        if (!audioContextRef.current) {
          audioContextRef.current = new (
            window.AudioContext || (window as any).webkitAudioContext
          )();
        }

        const audioContext = audioContextRef.current;

        // Resume context if suspended (may fail without user gesture in some browsers)
        if (audioContext.state === 'suspended') {
          await audioContext.resume();
          if (!isSessionActive(sessionId)) {
            isPlayingSegmentRef.current = false;
            return;
          }
        }

        const segment = segments[index];
        currentSegmentIndexRef.current = index;

        // Decode base64 to ArrayBuffer
        const binaryString = atob(segment.audioData);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }

        const audioBuffer = await audioContext.decodeAudioData(
          bytes.buffer.slice(0),
        );
        if (!isSessionActive(sessionId)) {
          isPlayingSegmentRef.current = false;
          return;
        }

        // Create and play source node
        const sourceNode = audioContext.createBufferSource();
        sourceNode.buffer = audioBuffer;
        sourceNode.connect(audioContext.destination);

        sourceNodeRef.current = sourceNode;

        sourceNode.onended = () => {
          if (!isSessionActive(sessionId)) return;
          // Release lock before playing next segment
          isPlayingSegmentRef.current = false;
          playedSecondsRef.current += audioBuffer.duration || 0;
          // Play next segment
          if (isPlayingRef.current) {
            playSegmentByIndex(index + 1, sessionId);
          }
        };

        sourceNode.start();
        setIsLoading(false);
        setIsPlaying(true);
        isPlayingRef.current = true;
        onPlayStateChangeRef.current?.(true);
      } catch (error) {
        console.error('Failed to play audio segment:', error);
        // Release lock so future attempts can proceed.
        isPlayingSegmentRef.current = false;
        setIsLoading(false);
        setIsWaitingForSegment(false);

        // Try next segment when we are already in a play session.
        if (isPlayingRef.current) {
          playSegmentByIndex(index + 1, sessionId);
          return;
        }
        releaseExclusive();
      }
    },
    [isSessionActive, releaseExclusive],
  );

  // Start playback from segments
  const playFromSegments = useCallback(
    async (forceStreaming: boolean = false) => {
      const sessionId = startPlaySession();
      requestExclusive(stopPlayback);

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

  // Watch for new segments when waiting
  useEffect(() => {
    if (isWaitingForSegment && isPlayingRef.current) {
      const sessionId = playSessionRef.current;
      if (!isSessionActive(sessionId)) {
        return;
      }
      const nextIndex = currentSegmentIndexRef.current;
      if (nextIndex < streamingSegments.length) {
        // New segment available, continue playback
        pendingStreamRef.current = false;
        playSegmentByIndex(nextIndex, sessionId);
      } else if (!isStreaming) {
        // Streaming finished and no more segments. If final URL exists, continue playback with it.
        if (effectiveAudioUrl) {
          pendingStreamRef.current = false;
          const startAtSeconds = playedSecondsRef.current;
          cleanupAudio();
          playFromUrl(startAtSeconds);
          return;
        }

        if (pendingStreamRef.current) {
          return;
        }

        setIsPlaying(false);
        isPlayingRef.current = false;
        setIsLoading(false);
        setIsWaitingForSegment(false);
        onPlayStateChangeRef.current?.(false);
        releaseExclusive();
      }
    }
  }, [
    streamingSegments.length,
    isStreaming,
    isWaitingForSegment,
    isSessionActive,
    playSegmentByIndex,
    effectiveAudioUrl,
    cleanupAudio,
    playFromUrl,
    releaseExclusive,
  ]);

  // Handle play/pause toggle
  const togglePlay = useCallback(() => {
    if (isLoading) {
      return;
    }

    if (isPlaying) {
      // Pause
      stopPlayback();
    } else {
      // Play
      if (useOssUrl) {
        playFromUrl();
      } else if (streamingSegments.length > 0 || isStreaming) {
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
    useOssUrl,
    isStreaming,
    playFromUrl,
    playFromSegments,
    streamingSegments.length,
    onRequestAudio,
    stopPlayback,
  ]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isPlayingRef.current = false;
      playSessionRef.current += 1;
      pendingStreamRef.current = false;
      cleanupAudio();
      releaseExclusive();
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, [cleanupAudio, releaseExclusive]);

  // Auto-play when enabled and audio is available
  // Track previous autoPlay value to detect changes
  const prevAutoPlayRef = useRef(autoPlay);
  const hasAutoPlayedForCurrentContentRef = useRef(false);

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
      !hasAutoPlayedForCurrentContentRef.current
    ) {
      if (streamingSegments.length > 0 || isStreaming) {
        hasAutoPlayedForCurrentContentRef.current = true;
        playFromSegments();
      } else if (effectiveAudioUrl) {
        hasAutoPlayedForCurrentContentRef.current = true;
        playFromUrl();
      }
    }
  }, [
    autoPlay,
    isPlaying,
    isLoading,
    disabled,
    streamingSegments.length,
    isStreaming,
    effectiveAudioUrl,
    playFromSegments,
    playFromUrl,
  ]);

  // Don't render if no audio available and not streaming
  if (!hasAudio && !isStreaming && !alwaysVisible) {
    return null;
  }

  const isButtonDisabled =
    disabled || (!hasAudio && !isStreaming && !onRequestAudio);

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

export default AudioPlayer;

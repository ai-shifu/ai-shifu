'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Volume2, Pause, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
}

export interface AudioPlayerProps {
  /** OSS URL when audio is complete */
  audioUrl?: string;
  /** Base64 audio segments during streaming */
  streamingSegments?: AudioSegment[];
  /** Whether audio is still streaming */
  isStreaming?: boolean;
  /** Disable the player */
  disabled?: boolean;
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
  disabled = false,
  size = 16,
  className,
  onPlayStateChange,
  autoPlay = false,
}: AudioPlayerProps) {
  const { t } = useTranslation();
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  // Track if we're waiting for the next segment during streaming
  const [isWaitingForSegment, setIsWaitingForSegment] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);

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
  const hasAudio = Boolean(audioUrl) || streamingSegments.length > 0;

  // Use OSS URL if available and streaming is complete
  const useOssUrl = Boolean(audioUrl) && !isStreaming;

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

  // Play audio from OSS URL
  const playFromUrl = useCallback(() => {
    if (!audioUrl) return;

    if (!audioRef.current) {
      audioRef.current = new Audio();
      audioRef.current.onended = () => {
        setIsPlaying(false);
        isPlayingRef.current = false;
        onPlayStateChangeRef.current?.(false);
      };
      audioRef.current.onerror = () => {
        setIsPlaying(false);
        isPlayingRef.current = false;
        setIsLoading(false);
        onPlayStateChangeRef.current?.(false);
      };
      audioRef.current.oncanplay = () => {
        setIsLoading(false);
      };
    }

    audioRef.current.src = audioUrl;
    setIsLoading(true);
    audioRef.current
      .play()
      .then(() => {
        setIsPlaying(true);
        isPlayingRef.current = true;
        onPlayStateChangeRef.current?.(true);
      })
      .catch(err => {
        console.error('Failed to play audio:', err);
        setIsPlaying(false);
        isPlayingRef.current = false;
        setIsLoading(false);
      });
  }, [audioUrl]);

  // Play a single segment by index
  const playSegmentByIndex = useCallback(async (index: number) => {
    console.log('[AudioPlayer] playSegmentByIndex:', {
      index,
      segmentsCount: segmentsRef.current.length,
    });

    // Prevent concurrent calls - if already playing a segment, skip
    if (isPlayingSegmentRef.current) {
      console.log('[AudioPlayer] Skipping - already playing segment');
      return;
    }

    const segments = segmentsRef.current;

    // Check if segment is available
    if (index >= segments.length) {
      // Segment not available yet
      if (isStreamingRef.current) {
        // Still streaming, wait for more segments
        console.log('[AudioPlayer] Waiting for more segments (streaming)');
        setIsWaitingForSegment(true);
        currentSegmentIndexRef.current = index;
        return;
      } else {
        // Streaming complete, no more segments - playback done
        console.log('[AudioPlayer] All segments played, notifying completion');
        setIsPlaying(false);
        isPlayingRef.current = false;
        setIsLoading(false);
        setIsWaitingForSegment(false);
        onPlayStateChangeRef.current?.(false);
        return;
      }
    }

    // Acquire lock
    isPlayingSegmentRef.current = true;
    setIsWaitingForSegment(false);

    // Initialize AudioContext if needed
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext ||
        (window as any).webkitAudioContext)();
    }

    const audioContext = audioContextRef.current;

    // Resume context if suspended
    if (audioContext.state === 'suspended') {
      await audioContext.resume();
    }

    const segment = segments[index];
    currentSegmentIndexRef.current = index;

    // Decode base64 to ArrayBuffer
    const binaryString = atob(segment.audioData);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    try {
      const audioBuffer = await audioContext.decodeAudioData(
        bytes.buffer.slice(0),
      );

      // Create and play source node
      const sourceNode = audioContext.createBufferSource();
      sourceNode.buffer = audioBuffer;
      sourceNode.connect(audioContext.destination);

      sourceNodeRef.current = sourceNode;

      sourceNode.onended = () => {
        // Release lock before playing next segment
        isPlayingSegmentRef.current = false;
        // Play next segment
        if (isPlayingRef.current) {
          playSegmentByIndex(index + 1);
        }
      };

      sourceNode.start();
      setIsLoading(false);
      setIsPlaying(true);
      isPlayingRef.current = true;
      onPlayStateChangeRef.current?.(true);
    } catch (decodeError) {
      console.error('Failed to decode audio segment:', decodeError);
      // Release lock before trying next segment
      isPlayingSegmentRef.current = false;
      // Try next segment
      if (isPlayingRef.current) {
        playSegmentByIndex(index + 1);
      }
    }
  }, []);

  // Start playback from segments
  const playFromSegments = useCallback(async () => {
    console.log('[AudioPlayer] playFromSegments called:', {
      segmentsCount: segmentsRef.current.length,
      isStreaming: isStreamingRef.current,
      isPlaying: isPlayingRef.current,
    });

    if (segmentsRef.current.length === 0) {
      if (isStreamingRef.current) {
        // No segments yet but streaming, wait
        console.log('[AudioPlayer] No segments yet, waiting for streaming');
        setIsWaitingForSegment(true);
        setIsLoading(true);
        setIsPlaying(true);
        isPlayingRef.current = true;
        currentSegmentIndexRef.current = 0;
        onPlayStateChangeRef.current?.(true);
        return;
      }
      console.log('[AudioPlayer] No segments and not streaming, returning');
      return;
    }

    console.log('[AudioPlayer] Starting playback from segment 0');
    setIsLoading(true);
    currentSegmentIndexRef.current = 0;
    await playSegmentByIndex(0);
  }, [playSegmentByIndex]);

  // Watch for new segments when waiting
  useEffect(() => {
    if (isWaitingForSegment && isPlayingRef.current) {
      const nextIndex = currentSegmentIndexRef.current;
      if (nextIndex < streamingSegments.length) {
        // New segment available, continue playback
        console.log('[AudioPlayer] New segment available, continuing playback');
        playSegmentByIndex(nextIndex);
      } else if (!isStreaming) {
        // Streaming finished and no more segments
        console.log('[AudioPlayer] Streaming finished, completing playback');
        setIsPlaying(false);
        isPlayingRef.current = false;
        setIsLoading(false);
        setIsWaitingForSegment(false);
        onPlayStateChangeRef.current?.(false);
      }
    }
  }, [
    streamingSegments.length,
    isStreaming,
    isWaitingForSegment,
    playSegmentByIndex,
  ]);

  // Timeout mechanism: if waiting for segment for too long, assume streaming is done
  useEffect(() => {
    if (!isWaitingForSegment || !isPlayingRef.current) {
      return;
    }

    // Wait 2 seconds for new segment, if none arrives, assume done
    console.log('[AudioPlayer] Starting wait timeout for next segment');
    const timeoutId = setTimeout(() => {
      if (isWaitingForSegment && isPlayingRef.current) {
        const nextIndex = currentSegmentIndexRef.current;
        if (nextIndex >= streamingSegments.length) {
          console.log(
            '[AudioPlayer] Timeout waiting for segment, completing playback',
          );
          setIsPlaying(false);
          isPlayingRef.current = false;
          setIsLoading(false);
          setIsWaitingForSegment(false);
          onPlayStateChangeRef.current?.(false);
        }
      }
    }, 2000);

    return () => clearTimeout(timeoutId);
  }, [isWaitingForSegment, streamingSegments.length]);

  // Handle play/pause toggle
  const togglePlay = useCallback(() => {
    if (isPlaying) {
      // Pause
      cleanupAudio();
      setIsPlaying(false);
      isPlayingRef.current = false;
      setIsWaitingForSegment(false);
      onPlayStateChangeRef.current?.(false);
    } else {
      // Play
      if (useOssUrl) {
        playFromUrl();
      } else if (streamingSegments.length > 0 || isStreaming) {
        playFromSegments();
      }
    }
  }, [
    isPlaying,
    useOssUrl,
    isStreaming,
    cleanupAudio,
    playFromUrl,
    playFromSegments,
    streamingSegments.length,
  ]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isPlayingRef.current = false;
      cleanupAudio();
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, [cleanupAudio]);

  // When audio URL becomes available, switch to it
  useEffect(() => {
    if (audioUrl && isPlaying && !useOssUrl) {
      // Audio was streaming, now complete URL is available
      // Continue playback from URL
      cleanupAudio();
      playFromUrl();
    }
  }, [audioUrl, isPlaying, useOssUrl, cleanupAudio, playFromUrl]);

  // Auto-play when enabled and audio is available
  // Track previous autoPlay value to detect changes
  const prevAutoPlayRef = useRef(autoPlay);
  const hasAutoPlayedForCurrentContentRef = useRef(false);

  useEffect(() => {
    // Debug logging
    console.log('[AudioPlayer] autoPlay effect:', {
      autoPlay,
      prevAutoPlay: prevAutoPlayRef.current,
      isPlaying,
      isLoading,
      disabled,
      hasAutoPlayed: hasAutoPlayedForCurrentContentRef.current,
      segmentsLength: streamingSegments.length,
      isStreaming,
      audioUrl: !!audioUrl,
    });

    // Reset auto-played flag when autoPlay changes from false to true
    // This allows queue-based playback to trigger
    if (autoPlay && !prevAutoPlayRef.current) {
      console.log('[AudioPlayer] Resetting hasAutoPlayed flag');
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
        console.log('[AudioPlayer] Starting playFromSegments');
        hasAutoPlayedForCurrentContentRef.current = true;
        playFromSegments();
      } else if (audioUrl) {
        console.log('[AudioPlayer] Starting playFromUrl');
        hasAutoPlayedForCurrentContentRef.current = true;
        playFromUrl();
      } else {
        console.log('[AudioPlayer] No audio content to play');
      }
    }
  }, [
    autoPlay,
    isPlaying,
    isLoading,
    disabled,
    streamingSegments.length,
    isStreaming,
    audioUrl,
    playFromSegments,
    playFromUrl,
  ]);

  // Don't render if no audio available and not streaming
  if (!hasAudio && !isStreaming) {
    return null;
  }

  const isButtonDisabled = disabled || (!hasAudio && !isStreaming);

  const ariaLabel = isLoading
    ? t('module.chat.audioLoading')
    : isPlaying
      ? t('module.chat.pauseAudio')
      : t('module.chat.playAudio');

  return (
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
}

export default AudioPlayer;

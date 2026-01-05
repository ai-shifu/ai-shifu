'use client';

import { useState, useCallback, useRef, useEffect } from 'react';

export interface AudioSegment {
  segmentIndex: number;
  audioData: string; // Base64 encoded
  durationMs: number;
  isFinal: boolean;
}

export interface UseAudioPlayerOptions {
  /** Callback when playback starts */
  onPlay?: () => void;
  /** Callback when playback pauses */
  onPause?: () => void;
  /** Callback when playback ends */
  onEnd?: () => void;
  /** Callback when an error occurs */
  onError?: (error: Error) => void;
}

export interface UseAudioPlayerReturn {
  /** Whether audio is currently playing */
  isPlaying: boolean;
  /** Whether audio is loading */
  isLoading: boolean;
  /** Current playback progress (0-1) */
  progress: number;
  /** Total duration in milliseconds */
  duration: number;
  /** Add a segment to the playback queue */
  addSegment: (segment: AudioSegment) => void;
  /** Set the final audio URL */
  setFinalUrl: (url: string) => void;
  /** Start playback */
  play: () => Promise<void>;
  /** Pause playback */
  pause: () => void;
  /** Stop and reset playback */
  stop: () => void;
  /** Clear all segments */
  clear: () => void;
  /** Get current audio URL (if available) */
  audioUrl: string | null;
  /** Get all segments */
  segments: AudioSegment[];
  /** Whether we're in streaming mode */
  isStreaming: boolean;
}

/**
 * Hook for managing TTS audio playback.
 *
 * Supports two modes:
 * 1. Streaming mode: Queues and plays base64-encoded audio segments
 * 2. Complete mode: Switches to OSS URL after upload completes
 */
export function useAudioPlayer(
  options: UseAudioPlayerOptions = {},
): UseAudioPlayerReturn {
  const { onPlay, onPause, onEnd, onError } = options;

  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [segments, setSegments] = useState<AudioSegment[]>([]);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(true);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  const currentSegmentRef = useRef(0);
  const playbackStartTimeRef = useRef(0);

  // Calculate total duration from segments
  useEffect(() => {
    const totalDuration = segments.reduce(
      (acc, seg) => acc + seg.durationMs,
      0,
    );
    setDuration(totalDuration);
  }, [segments]);

  // Add a new segment
  const addSegment = useCallback((segment: AudioSegment) => {
    setSegments(prev => {
      // Check if segment already exists
      const exists = prev.some(s => s.segmentIndex === segment.segmentIndex);
      if (exists) return prev;

      // Add and sort by index
      const newSegments = [...prev, segment].sort(
        (a, b) => a.segmentIndex - b.segmentIndex,
      );
      return newSegments;
    });

    if (segment.isFinal) {
      setIsStreaming(false);
    }
  }, []);

  // Set final audio URL
  const setFinalUrl = useCallback((url: string) => {
    setAudioUrl(url);
    setIsStreaming(false);
  }, []);

  // Cleanup audio resources
  const cleanupAudio = useCallback(() => {
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.stop();
        sourceNodeRef.current.disconnect();
      } catch (e) {
        // Ignore
      }
      sourceNodeRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
  }, []);

  // Play from URL
  const playFromUrl = useCallback(async () => {
    if (!audioUrl) return;

    if (!audioRef.current) {
      audioRef.current = new Audio();
    }

    const audio = audioRef.current;
    audio.src = audioUrl;

    audio.onended = () => {
      setIsPlaying(false);
      setProgress(1);
      onEnd?.();
    };

    audio.onerror = () => {
      const error = new Error('Failed to play audio from URL');
      setIsPlaying(false);
      setIsLoading(false);
      onError?.(error);
    };

    audio.ontimeupdate = () => {
      if (audio.duration) {
        setProgress(audio.currentTime / audio.duration);
      }
    };

    audio.onloadedmetadata = () => {
      setDuration(audio.duration * 1000);
    };

    audio.oncanplay = () => {
      setIsLoading(false);
    };

    setIsLoading(true);
    try {
      await audio.play();
      setIsPlaying(true);
      onPlay?.();
    } catch (error) {
      setIsPlaying(false);
      setIsLoading(false);
      onError?.(error as Error);
    }
  }, [audioUrl, onPlay, onEnd, onError]);

  // Play from segments
  const playFromSegments = useCallback(async () => {
    if (segments.length === 0) return;

    // Initialize AudioContext
    if (!audioContextRef.current) {
      audioContextRef.current = new (
        window.AudioContext || (window as any).webkitAudioContext
      )();
    }

    const audioContext = audioContextRef.current;

    if (audioContext.state === 'suspended') {
      await audioContext.resume();
    }

    setIsLoading(true);
    playbackStartTimeRef.current = Date.now();

    const playSegment = async (index: number): Promise<void> => {
      if (index >= segments.length) {
        setIsPlaying(false);
        setProgress(1);
        setIsLoading(false);
        onEnd?.();
        return;
      }

      currentSegmentRef.current = index;
      const segment = segments[index];

      // Calculate progress
      const playedDuration = segments
        .slice(0, index)
        .reduce((acc, s) => acc + s.durationMs, 0);
      const totalDuration = segments.reduce((acc, s) => acc + s.durationMs, 0);
      setProgress(playedDuration / totalDuration);

      try {
        // Decode base64
        const binaryString = atob(segment.audioData);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }

        const audioBuffer = await audioContext.decodeAudioData(
          bytes.buffer.slice(0),
        );

        const sourceNode = audioContext.createBufferSource();
        sourceNode.buffer = audioBuffer;
        sourceNode.connect(audioContext.destination);
        sourceNodeRef.current = sourceNode;

        return new Promise(resolve => {
          sourceNode.onended = () => {
            resolve();
            playSegment(index + 1);
          };

          sourceNode.start();
          setIsLoading(false);
          setIsPlaying(true);
          if (index === 0) {
            onPlay?.();
          }
        });
      } catch (error) {
        console.error('Failed to decode segment:', error);
        // Skip to next segment
        return playSegment(index + 1);
      }
    };

    await playSegment(0);
  }, [segments, onPlay, onEnd]);

  // Play
  const play = useCallback(async () => {
    if (audioUrl && !isStreaming) {
      await playFromUrl();
    } else if (segments.length > 0) {
      await playFromSegments();
    }
  }, [audioUrl, isStreaming, segments.length, playFromUrl, playFromSegments]);

  // Pause
  const pause = useCallback(() => {
    cleanupAudio();
    setIsPlaying(false);
    onPause?.();
  }, [cleanupAudio, onPause]);

  // Stop
  const stop = useCallback(() => {
    cleanupAudio();
    setIsPlaying(false);
    setProgress(0);
    currentSegmentRef.current = 0;
  }, [cleanupAudio]);

  // Clear
  const clear = useCallback(() => {
    stop();
    setSegments([]);
    setAudioUrl(null);
    setIsStreaming(true);
    setDuration(0);
  }, [stop]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupAudio();
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, [cleanupAudio]);

  return {
    isPlaying,
    isLoading,
    progress,
    duration,
    addSegment,
    setFinalUrl,
    play,
    pause,
    stop,
    clear,
    audioUrl,
    segments,
    isStreaming,
  };
}

export default useAudioPlayer;

'use client';

import React, {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { AudioItem, AudioSegment } from '@/c-utils/audio-utils';
import {
  getNextIndex,
  normalizeAudioItemList,
  sortAudioSegments,
} from '@/c-utils/audio-playlist';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import type { AudioPlayerHandle } from './AudioPlayer';

export interface AudioPlayerListProps {
  audioList: AudioItem[];
  className?: string;
  autoPlay?: boolean;
  disabled?: boolean;
  onPlayStateChange?: (isPlaying: boolean) => void;
  onEnded?: () => void;
  onRequestAudio?: () => Promise<any>;
  isSequenceActive?: boolean;
  sequenceBlockBid?: string | null;
}

const AudioPlayerListBase = (
  {
    audioList,
    className,
    autoPlay = false,
    disabled = false,
    onPlayStateChange,
    onEnded,
    onRequestAudio,
    isSequenceActive = false,
    sequenceBlockBid = null,
  }: AudioPlayerListProps,
  ref: React.ForwardedRef<AudioPlayerHandle>,
) => {
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const currentSrcRef = useRef<string | null>(null);
  const currentTrackRef = useRef<AudioItem | null>(null);
  const currentTrackBidRef = useRef<string | null>(null);
  const currentIndexRef = useRef(0);
  const segmentsRef = useRef<AudioSegment[]>([]);
  const onPlayStateChangeRef = useRef(onPlayStateChange);
  const onEndedRef = useRef(onEnded);
  const isPlayingRef = useRef(false);
  const isPausedRef = useRef(false);
  const isUsingSegmentsRef = useRef(false);
  const isSegmentsPlaybackRef = useRef(false);
  const isWaitingForSegmentRef = useRef(false);
  const shouldResumeRef = useRef(false);
  const pendingSeekRef = useRef<number | null>(null);
  const autoPlayedTrackRef = useRef<string | null>(null);
  const localAudioUrlMapRef = useRef<Map<string, string>>(new Map());
  const pendingRequestRef = useRef<Set<string>>(new Set());
  const currentSegmentIndexRef = useRef(0);
  const segmentOffsetRef = useRef(0);
  const playedSecondsRef = useRef(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const playlist = useMemo(
    () => normalizeAudioItemList(audioList),
    [audioList],
  );
  const currentTrack = useMemo(
    () => playlist[currentIndex] ?? null,
    [playlist, currentIndex],
  );
  const currentSegments = useMemo(
    () => sortAudioSegments(currentTrack?.audioSegments ?? []),
    [currentTrack?.audioSegments],
  );

  useEffect(() => {
    onPlayStateChangeRef.current = onPlayStateChange;
  }, [onPlayStateChange]);

  useEffect(() => {
    onEndedRef.current = onEnded;
  }, [onEnded]);

  useEffect(() => {
    currentTrackRef.current = currentTrack;
  }, [currentTrack]);

  useEffect(() => {
    segmentsRef.current = currentSegments;
  }, [currentSegments]);

  useEffect(() => {
    currentIndexRef.current = currentIndex;
  }, [currentIndex]);

  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  const setPlayingState = useCallback((next: boolean) => {
    setIsPlaying(next);
    isPlayingRef.current = next;
    onPlayStateChangeRef.current?.(next);
  }, []);

  const resetSegmentState = useCallback(() => {
    playedSecondsRef.current = 0;
    segmentOffsetRef.current = 0;
    currentSegmentIndexRef.current = 0;
  }, []);

  const resolveTrackUrl = useCallback((track: AudioItem | null) => {
    if (!track) {
      return undefined;
    }
    if (track.audioUrl) {
      return track.audioUrl;
    }
    const bid = track.generated_block_bid;
    if (!bid) {
      return undefined;
    }
    return localAudioUrlMapRef.current.get(bid);
  }, []);

  const shouldUseUrl = useCallback(
    (track: AudioItem | null) => {
      if (!track) {
        return false;
      }
      const url = resolveTrackUrl(track);
      return Boolean(url) && !track.isAudioStreaming;
    },
    [resolveTrackUrl],
  );

  const shouldUseSegments = useCallback(
    (track: AudioItem | null) => {
      if (!track) {
        return false;
      }
      if (shouldUseUrl(track)) {
        return false;
      }
      return Boolean(
        track.isAudioStreaming ||
        (track.audioSegments && track.audioSegments.length > 0),
      );
    },
    [shouldUseUrl],
  );

  const getSegmentSrc = useCallback((segment: AudioSegment) => {
    if (!segment?.audioData) {
      return '';
    }
    if (segment.audioData.startsWith('data:')) {
      return segment.audioData;
    }
    return `data:audio/mpeg;base64,${segment.audioData}`;
  }, []);

  const applySeek = useCallback((seconds: number) => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    if (!Number.isFinite(seconds) || seconds <= 0) {
      pendingSeekRef.current = null;
      return;
    }
    const target = Math.max(0, seconds);
    try {
      audio.currentTime = target;
      pendingSeekRef.current = null;
    } catch {
      pendingSeekRef.current = target;
    }
  }, []);

  const startUrlPlayback = useCallback(
    (url: string, startAtSeconds: number = 0) => {
      const audio = audioRef.current;
      if (!audio || disabled) {
        return false;
      }
      isPausedRef.current = false;
      isUsingSegmentsRef.current = false;
      isSegmentsPlaybackRef.current = false;
      isWaitingForSegmentRef.current = false;
      if (currentSrcRef.current !== url) {
        currentSrcRef.current = url;
        audio.src = url;
        audio.load();
      }
      applySeek(startAtSeconds);
      requestExclusive(() => {
        audio.pause();
      });
      const playPromise = audio.play();
      if (playPromise && typeof playPromise.then === 'function') {
        playPromise
          .then(() => {
            setPlayingState(true);
          })
          .catch(() => {
            setPlayingState(false);
            releaseExclusive();
          });
      }
      return true;
    },
    [applySeek, disabled, releaseExclusive, requestExclusive, setPlayingState],
  );

  const startSegmentPlayback = useCallback(
    (index: number, startOffsetSeconds: number = 0) => {
      const audio = audioRef.current;
      const track = currentTrackRef.current;
      if (!audio || !track || disabled) {
        return false;
      }
      isPausedRef.current = false;
      const segments = segmentsRef.current;
      const segment = segments[index];
      if (!segment) {
        if (track.isAudioStreaming) {
          isUsingSegmentsRef.current = true;
          isSegmentsPlaybackRef.current = true;
          isWaitingForSegmentRef.current = true;
          currentSegmentIndexRef.current = index;
          segmentOffsetRef.current = Math.max(0, startOffsetSeconds);
          requestExclusive(() => {
            audio.pause();
          });
          if (!isPlayingRef.current) {
            setPlayingState(true);
          }
          return true;
        }
        return false;
      }

      const src = getSegmentSrc(segment);
      isUsingSegmentsRef.current = true;
      isSegmentsPlaybackRef.current = true;
      isWaitingForSegmentRef.current = false;
      currentSegmentIndexRef.current = index;
      segmentOffsetRef.current = Math.max(0, startOffsetSeconds);
      if (currentSrcRef.current !== src) {
        currentSrcRef.current = src;
        audio.src = src;
        audio.load();
      }
      applySeek(segmentOffsetRef.current);
      requestExclusive(() => {
        audio.pause();
      });
      const playPromise = audio.play();
      if (playPromise && typeof playPromise.then === 'function') {
        playPromise
          .then(() => {
            setPlayingState(true);
          })
          .catch(() => {
            setPlayingState(false);
            releaseExclusive();
          });
      }
      return true;
    },
    [
      applySeek,
      disabled,
      getSegmentSrc,
      releaseExclusive,
      requestExclusive,
      setPlayingState,
    ],
  );

  const startPlaybackForTrack = useCallback(
    (options?: { resume?: boolean }) => {
      const track = currentTrackRef.current;
      if (!track || disabled) {
        return false;
      }
      const url = resolveTrackUrl(track);
      if (shouldUseUrl(track) && url) {
        const startAtSeconds =
          options?.resume && audioRef.current
            ? audioRef.current.currentTime
            : 0;
        return startUrlPlayback(url, startAtSeconds);
      }
      if (shouldUseSegments(track)) {
        const index = options?.resume ? currentSegmentIndexRef.current : 0;
        const offset = options?.resume ? segmentOffsetRef.current : 0;
        return startSegmentPlayback(index, offset);
      }
      return false;
    },
    [
      disabled,
      resolveTrackUrl,
      shouldUseSegments,
      shouldUseUrl,
      startSegmentPlayback,
      startUrlPlayback,
    ],
  );

  const playCurrentTrack = useCallback(
    (options?: { resume?: boolean }) => {
      if (disabled) {
        return;
      }
      isPausedRef.current = false;
      const track = currentTrackRef.current;
      if (!track) {
        return;
      }
      if (startPlaybackForTrack(options)) {
        return;
      }
      if (!onRequestAudio || !track.generated_block_bid) {
        return;
      }
      const requestBid = track.generated_block_bid;
      if (pendingRequestRef.current.has(requestBid)) {
        return;
      }
      pendingRequestRef.current.add(requestBid);
      isUsingSegmentsRef.current = true;
      isSegmentsPlaybackRef.current = true;
      isWaitingForSegmentRef.current = true;
      setPlayingState(true);
      requestExclusive(() => {
        audioRef.current?.pause();
      });
      onRequestAudio()
        .then(result => {
          if (currentTrackRef.current?.generated_block_bid !== requestBid) {
            return;
          }
          const url = result?.audio_url || result?.audioUrl;
          if (url) {
            localAudioUrlMapRef.current.set(requestBid, url);
            if (!currentTrackRef.current?.isAudioStreaming) {
              startUrlPlayback(url, 0);
            }
          }
        })
        .catch(() => {
          if (currentTrackRef.current?.generated_block_bid !== requestBid) {
            return;
          }
          setPlayingState(false);
          isWaitingForSegmentRef.current = false;
          isSegmentsPlaybackRef.current = false;
          releaseExclusive();
        })
        .finally(() => {
          pendingRequestRef.current.delete(requestBid);
        });
    },
    [
      disabled,
      onRequestAudio,
      releaseExclusive,
      requestExclusive,
      setPlayingState,
      startPlaybackForTrack,
      startUrlPlayback,
    ],
  );

  const pausePlayback = useCallback(
    (options?: { traceId?: string; keepAutoPlay?: boolean }) => {
      const audio = audioRef.current;
      if (!audio) {
        return;
      }
      isPausedRef.current = !options?.keepAutoPlay;
      shouldResumeRef.current = false;
      if (isUsingSegmentsRef.current) {
        segmentOffsetRef.current = Math.max(0, audio.currentTime || 0);
        isSegmentsPlaybackRef.current = false;
        isWaitingForSegmentRef.current = false;
      }
      audio.pause();
    },
    [],
  );

  const finishTrack = useCallback(() => {
    resetSegmentState();
    isUsingSegmentsRef.current = false;
    isSegmentsPlaybackRef.current = false;
    isWaitingForSegmentRef.current = false;
    setPlayingState(false);
    onEndedRef.current?.();
    if (isSequenceActive) {
      return;
    }
    const listLength = playlist.length;
    if (!listLength) {
      releaseExclusive();
      return;
    }
    const nextIndex = getNextIndex(currentIndexRef.current, listLength);
    if (nextIndex === currentIndexRef.current) {
      releaseExclusive();
      return;
    }
    shouldResumeRef.current = true;
    setCurrentIndex(nextIndex);
  }, [
    isSequenceActive,
    playlist.length,
    releaseExclusive,
    resetSegmentState,
    setPlayingState,
  ]);

  const handleSegmentEnded = useCallback(() => {
    const segments = segmentsRef.current;
    const track = currentTrackRef.current;
    const audio = audioRef.current;
    const index = currentSegmentIndexRef.current;
    const segment = segments[index];
    const duration = segment?.durationMs
      ? segment.durationMs / 1000
      : (audio?.duration ?? 0);
    if (Number.isFinite(duration) && duration > 0) {
      playedSecondsRef.current += duration;
    }
    segmentOffsetRef.current = 0;
    const nextIndex = index + 1;
    if (nextIndex < segments.length) {
      currentSegmentIndexRef.current = nextIndex;
      startSegmentPlayback(nextIndex, 0);
      return;
    }
    if (track?.isAudioStreaming) {
      currentSegmentIndexRef.current = nextIndex;
      isSegmentsPlaybackRef.current = true;
      isWaitingForSegmentRef.current = true;
      if (!isPlayingRef.current) {
        setPlayingState(true);
      }
      return;
    }
    const url = resolveTrackUrl(track ?? null);
    if (url) {
      const startAtSeconds = playedSecondsRef.current;
      resetSegmentState();
      startUrlPlayback(url, startAtSeconds);
      return;
    }
    finishTrack();
  }, [
    finishTrack,
    resolveTrackUrl,
    resetSegmentState,
    startSegmentPlayback,
    startUrlPlayback,
  ]);

  const handleAudioPlay = useCallback(() => {
    if (disabled) {
      return;
    }
    setPlayingState(true);
    requestExclusive(() => {
      audioRef.current?.pause();
    });
  }, [disabled, requestExclusive, setPlayingState]);

  const handleAudioPause = useCallback(() => {
    if (isUsingSegmentsRef.current && isWaitingForSegmentRef.current) {
      return;
    }
    if (isUsingSegmentsRef.current) {
      const audio = audioRef.current;
      segmentOffsetRef.current = Math.max(0, audio?.currentTime ?? 0);
      isSegmentsPlaybackRef.current = false;
    }
    setPlayingState(false);
    releaseExclusive();
  }, [releaseExclusive, setPlayingState]);

  const handleAudioEnded = useCallback(() => {
    if (isUsingSegmentsRef.current) {
      handleSegmentEnded();
      return;
    }
    finishTrack();
  }, [finishTrack, handleSegmentEnded]);

  const handleAudioError = useCallback(() => {
    isWaitingForSegmentRef.current = false;
    isSegmentsPlaybackRef.current = false;
    setPlayingState(false);
    releaseExclusive();
  }, [releaseExclusive, setPlayingState]);

  const handleLoadedMetadata = useCallback(() => {
    const audio = audioRef.current;
    const pendingSeek = pendingSeekRef.current;
    if (!audio || pendingSeek === null) {
      return;
    }
    try {
      audio.currentTime = Math.max(0, pendingSeek);
    } catch {}
    pendingSeekRef.current = null;
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      togglePlay: () => {
        if (isPlayingRef.current) {
          pausePlayback();
          return;
        }
        const canResume = Boolean(
          audioRef.current?.src && audioRef.current?.paused,
        );
        playCurrentTrack({ resume: canResume });
      },
      play: () => {
        if (!isPlayingRef.current) {
          const canResume = Boolean(
            audioRef.current?.src && audioRef.current?.paused,
          );
          playCurrentTrack({ resume: canResume });
        }
      },
      pause: (options?: { traceId?: string; keepAutoPlay?: boolean }) => {
        pausePlayback(options);
      },
    }),
    [pausePlayback, playCurrentTrack],
  );

  useEffect(() => {
    if (!playlist.length) {
      setCurrentIndex(0);
      return;
    }
    if (currentIndexRef.current >= playlist.length) {
      setCurrentIndex(Math.max(playlist.length - 1, 0));
    }
  }, [playlist.length]);

  useEffect(() => {
    if (playlist.length) {
      return;
    }
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    currentSrcRef.current = null;
    isUsingSegmentsRef.current = false;
    isSegmentsPlaybackRef.current = false;
    isWaitingForSegmentRef.current = false;
    resetSegmentState();
    setPlayingState(false);
    releaseExclusive();
  }, [playlist.length, releaseExclusive, resetSegmentState, setPlayingState]);

  useEffect(() => {
    const nextBid = currentTrack?.generated_block_bid ?? null;
    const isTrackChanged = currentTrackBidRef.current !== nextBid;
    if (!isTrackChanged) {
      return;
    }
    currentTrackBidRef.current = nextBid;
    isUsingSegmentsRef.current = false;
    isSegmentsPlaybackRef.current = false;
    isWaitingForSegmentRef.current = false;
    resetSegmentState();
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    currentSrcRef.current = null;
  }, [currentTrack, resetSegmentState]);

  useEffect(() => {
    if (!currentTrack || disabled) {
      return;
    }
    if (shouldResumeRef.current) {
      shouldResumeRef.current = false;
      startPlaybackForTrack();
      return;
    }
    if (!autoPlay || isPausedRef.current) {
      return;
    }
    const bid = currentTrack.generated_block_bid ?? null;
    if (bid && autoPlayedTrackRef.current === bid) {
      return;
    }
    const started = startPlaybackForTrack();
    if (started && bid) {
      autoPlayedTrackRef.current = bid;
    }
  }, [
    autoPlay,
    currentSegments.length,
    currentTrack,
    currentTrack?.audioUrl,
    currentTrack?.isAudioStreaming,
    disabled,
    startPlaybackForTrack,
  ]);

  useEffect(() => {
    if (!sequenceBlockBid || !playlist.length) {
      return;
    }
    const nextIndex = playlist.findIndex(
      item => item.generated_block_bid === sequenceBlockBid,
    );
    if (nextIndex < 0 || nextIndex === currentIndexRef.current) {
      return;
    }
    shouldResumeRef.current = isSequenceActive && !isPausedRef.current;
    setCurrentIndex(nextIndex);
  }, [isSequenceActive, playlist, sequenceBlockBid]);

  useEffect(() => {
    if (sequenceBlockBid !== null) {
      return;
    }
    if (!isSequenceActive) {
      return;
    }
    shouldResumeRef.current = false;
    if (isPlayingRef.current || isWaitingForSegmentRef.current) {
      pausePlayback();
    }
  }, [isSequenceActive, pausePlayback, sequenceBlockBid]);

  useEffect(() => {
    if (!isSegmentsPlaybackRef.current || !isWaitingForSegmentRef.current) {
      return;
    }
    const track = currentTrackRef.current;
    const segments = segmentsRef.current;
    const nextIndex = currentSegmentIndexRef.current;
    if (nextIndex < segments.length) {
      startSegmentPlayback(nextIndex, segmentOffsetRef.current);
      return;
    }
    if (track && !track.isAudioStreaming) {
      const url = resolveTrackUrl(track);
      if (url) {
        const startAtSeconds =
          playedSecondsRef.current + segmentOffsetRef.current;
        resetSegmentState();
        startUrlPlayback(url, startAtSeconds);
        return;
      }
      finishTrack();
    }
  }, [
    currentSegments.length,
    currentTrack?.isAudioStreaming,
    finishTrack,
    resolveTrackUrl,
    resetSegmentState,
    startSegmentPlayback,
    startUrlPlayback,
  ]);

  useEffect(() => {
    return () => {
      releaseExclusive();
    };
  }, [releaseExclusive]);

  // console.log('playlist', playlist);
  // console.log('currentTrack', currentTrack);

  return (
    <audio
      ref={audioRef}
      preload='metadata'
      playsInline
      onPlay={handleAudioPlay}
      onPause={handleAudioPause}
      onEnded={handleAudioEnded}
      onError={handleAudioError}
      onLoadedMetadata={handleLoadedMetadata}
      className={className}
    />
  );
};

export const AudioPlayerList = memo(forwardRef(AudioPlayerListBase));

AudioPlayerList.displayName = 'AudioPlayerList';

export default AudioPlayerList;

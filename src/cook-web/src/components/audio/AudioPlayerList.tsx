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

const logAudioDebug = (event: string, payload?: Record<string, any>) => {
  if (process.env.NODE_ENV === 'production') {
    return;
  }
  console.log(`[listen-audio-debug] ${event}`, payload ?? {});
};

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
  const playerDebugIdRef = useRef(`list-${Math.random().toString(36).slice(2, 8)}`);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const logAudioInterrupt = useCallback(
    (event: string, payload?: Record<string, unknown>) => {
      if (process.env.NODE_ENV === 'production') {
        return;
      }
      console.log(`[音频中断排查][AudioPlayerList] ${event}`, {
        playerId: playerDebugIdRef.current,
        currentTrackBid: currentTrackRef.current?.generated_block_bid ?? null,
        sequenceBlockBid,
        isSequenceActive,
        isPlaying: isPlayingRef.current,
        ...payload,
      });
    },
    [isSequenceActive, sequenceBlockBid],
  );
  const logAudioInterruptRef = useRef(logAudioInterrupt);

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

  useEffect(() => {
    logAudioInterruptRef.current = logAudioInterrupt;
  }, [logAudioInterrupt]);

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

  const stopByExclusivePreempt = useCallback(
    (payload?: Record<string, unknown>) => {
      const audio = audioRef.current;
      logAudioInterrupt('被其他音频实例抢占，执行强制停止当前播放', {
        reason: 'exclusive-preempt',
        ...payload,
      });
      shouldResumeRef.current = false;
      // Keep auto-play enabled for upcoming sequence items.
      // Only stop current playback state and clear resumable flags.
      isPausedRef.current = false;
      if (isUsingSegmentsRef.current && audio) {
        segmentOffsetRef.current = Math.max(0, audio.currentTime || 0);
      }
      isSegmentsPlaybackRef.current = false;
      isWaitingForSegmentRef.current = false;
      setPlayingState(false);
      audio?.pause();
      releaseExclusive();
    },
    [logAudioInterrupt, releaseExclusive, setPlayingState],
  );

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
        stopByExclusivePreempt({
          from: 'startUrlPlayback',
          url,
        });
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
      releaseExclusive,
      requestExclusive,
      setPlayingState,
      stopByExclusivePreempt,
    ],
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
            stopByExclusivePreempt({
              from: 'startSegmentPlayback-waiting',
              segmentIndex: index,
            });
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
        stopByExclusivePreempt({
          from: 'startSegmentPlayback-playing',
          segmentIndex: index,
        });
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
      stopByExclusivePreempt,
    ],
  );

  const startPlaybackForTrack = useCallback(
    (options?: { resume?: boolean }) => {
      const track = currentTrackRef.current;
      if (!track || disabled) {
        logAudioDebug('audio-player-start-skip', {
          reason: track ? 'disabled' : 'no-track',
          disabled,
        });
        return false;
      }
      const url = resolveTrackUrl(track);
      if (shouldUseUrl(track) && url) {
        const startAtSeconds =
          options?.resume && audioRef.current
            ? audioRef.current.currentTime
            : 0;
        logAudioDebug('audio-player-start-url', {
          bid: track.generated_block_bid,
          resume: Boolean(options?.resume),
          startAtSeconds,
          hasUrl: Boolean(url),
        });
        return startUrlPlayback(url, startAtSeconds);
      }
      if (shouldUseSegments(track)) {
        const index = options?.resume ? currentSegmentIndexRef.current : 0;
        const offset = options?.resume ? segmentOffsetRef.current : 0;
        logAudioDebug('audio-player-start-segment', {
          bid: track.generated_block_bid,
          resume: Boolean(options?.resume),
          segmentIndex: index,
          segmentOffset: offset,
          segments: segmentsRef.current.length,
          isAudioStreaming: Boolean(track.isAudioStreaming),
        });
        return startSegmentPlayback(index, offset);
      }
      logAudioDebug('audio-player-start-miss-source', {
        bid: track.generated_block_bid,
        hasTrackUrl: Boolean(track.audioUrl),
        localUrl: Boolean(url),
        segments: segmentsRef.current.length,
        isAudioStreaming: Boolean(track.isAudioStreaming),
      });
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
      logAudioDebug('audio-player-play-current', {
        bid: track.generated_block_bid,
        resume: Boolean(options?.resume),
      });
      if (startPlaybackForTrack(options)) {
        return;
      }
      if (!onRequestAudio || !track.generated_block_bid) {
        logAudioDebug('audio-player-request-skip', {
          bid: track.generated_block_bid ?? null,
          hasOnRequestAudio: Boolean(onRequestAudio),
        });
        return;
      }
      const requestBid = track.generated_block_bid;
      if (pendingRequestRef.current.has(requestBid)) {
        logAudioDebug('audio-player-request-skip-pending', {
          bid: requestBid,
        });
        return;
      }
      pendingRequestRef.current.add(requestBid);
      logAudioDebug('audio-player-request-start', {
        bid: requestBid,
      });
      isUsingSegmentsRef.current = true;
      isSegmentsPlaybackRef.current = true;
      isWaitingForSegmentRef.current = true;
      setPlayingState(true);
      requestExclusive(() => {
        stopByExclusivePreempt({
          from: 'playCurrentTrack-requestAudio',
          requestBid,
        });
      });
      onRequestAudio()
        .then(result => {
          if (currentTrackRef.current?.generated_block_bid !== requestBid) {
            logAudioDebug('audio-player-request-stale-result', {
              bid: requestBid,
              currentBid: currentTrackRef.current?.generated_block_bid ?? null,
            });
            return;
          }
          const url = result?.audio_url || result?.audioUrl;
          logAudioDebug('audio-player-request-success', {
            bid: requestBid,
            hasUrl: Boolean(url),
            isAudioStreaming: Boolean(currentTrackRef.current?.isAudioStreaming),
          });
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
          logAudioDebug('audio-player-request-error', {
            bid: requestBid,
          });
          setPlayingState(false);
          isWaitingForSegmentRef.current = false;
          isSegmentsPlaybackRef.current = false;
          releaseExclusive();
        })
        .finally(() => {
          pendingRequestRef.current.delete(requestBid);
          logAudioDebug('audio-player-request-finished', {
            bid: requestBid,
          });
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
      stopByExclusivePreempt,
    ],
  );

  const pausePlayback = useCallback(
    (options?: { traceId?: string; keepAutoPlay?: boolean }) => {
      const audio = audioRef.current;
      if (!audio) {
        return;
      }
      logAudioInterrupt('调用 pausePlayback，准备暂停当前音频', {
        traceId: options?.traceId ?? null,
        keepAutoPlay: Boolean(options?.keepAutoPlay),
        isUsingSegments: isUsingSegmentsRef.current,
        isWaitingForSegment: isWaitingForSegmentRef.current,
      });
      isPausedRef.current = !options?.keepAutoPlay;
      shouldResumeRef.current = false;
      if (isUsingSegmentsRef.current) {
        segmentOffsetRef.current = Math.max(0, audio.currentTime || 0);
        isSegmentsPlaybackRef.current = false;
        isWaitingForSegmentRef.current = false;
      }
      audio.pause();
    },
    [logAudioInterrupt],
  );

  const finishTrack = useCallback(() => {
    logAudioInterrupt('finish-track-enter', {
      currentIndex: currentIndexRef.current,
      playlistLength: playlist.length,
      isSequenceActive,
      trackBid: currentTrackRef.current?.generated_block_bid ?? null,
    });
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
    logAudioInterrupt,
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
      logAudioInterrupt('segment-ended-enter-waiting-mode', {
        segmentIndex: index,
        nextSegmentIndex: nextIndex,
        loadedSegments: segments.length,
        trackBid: track.generated_block_bid ?? null,
      });
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
    logAudioInterrupt,
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
      stopByExclusivePreempt({
        from: 'handleAudioPlay',
      });
    });
  }, [disabled, requestExclusive, setPlayingState, stopByExclusivePreempt]);

  const handleAudioPause = useCallback(() => {
    if (isUsingSegmentsRef.current && isWaitingForSegmentRef.current) {
      return;
    }
    logAudioInterrupt('收到 audio onPause 事件', {
      isUsingSegments: isUsingSegmentsRef.current,
      isWaitingForSegment: isWaitingForSegmentRef.current,
      currentTime: audioRef.current?.currentTime ?? 0,
    });
    if (isUsingSegmentsRef.current) {
      const audio = audioRef.current;
      segmentOffsetRef.current = Math.max(0, audio?.currentTime ?? 0);
      isSegmentsPlaybackRef.current = false;
    }
    setPlayingState(false);
    releaseExclusive();
  }, [logAudioInterrupt, releaseExclusive, setPlayingState]);

  const handleAudioEnded = useCallback(() => {
    logAudioDebug('audio-player-ended', {
      bid: currentTrackRef.current?.generated_block_bid ?? null,
      usingSegments: isUsingSegmentsRef.current,
      waitingForSegment: isWaitingForSegmentRef.current,
      sequenceBlockBid,
      isSequenceActive,
    });
    if (isUsingSegmentsRef.current) {
      handleSegmentEnded();
      return;
    }
    finishTrack();
  }, [finishTrack, handleSegmentEnded, isSequenceActive, sequenceBlockBid]);

  const handleAudioError = useCallback(() => {
    logAudioInterrupt('收到 audio onError 事件，停止当前播放', {
      currentSrc: currentSrcRef.current,
    });
    isWaitingForSegmentRef.current = false;
    isSegmentsPlaybackRef.current = false;
    setPlayingState(false);
    releaseExclusive();
  }, [logAudioInterrupt, releaseExclusive, setPlayingState]);

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
        logAudioInterrupt('收到外部 togglePlay 调用', {
          isPlaying: isPlayingRef.current,
        });
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
        logAudioInterrupt('收到外部 play 调用', {
          isPlaying: isPlayingRef.current,
        });
        if (!isPlayingRef.current) {
          const canResume = Boolean(
            audioRef.current?.src && audioRef.current?.paused,
          );
          playCurrentTrack({ resume: canResume });
        }
      },
      pause: (options?: { traceId?: string; keepAutoPlay?: boolean }) => {
        logAudioInterrupt('收到外部 pause 调用', {
          traceId: options?.traceId ?? null,
          keepAutoPlay: Boolean(options?.keepAutoPlay),
        });
        pausePlayback(options);
      },
    }),
    [logAudioInterrupt, pausePlayback, playCurrentTrack],
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
    logAudioInterrupt('播放列表变为空，执行强制 pause + 清理 src', {
      playlistLength: playlist.length,
    });
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
  }, [
    logAudioInterrupt,
    playlist.length,
    releaseExclusive,
    resetSegmentState,
    setPlayingState,
  ]);

  useEffect(() => {
    const nextBid = currentTrack?.generated_block_bid ?? null;
    const isTrackChanged = currentTrackBidRef.current !== nextBid;
    if (!isTrackChanged) {
      return;
    }
    logAudioDebug('audio-player-track-changed', {
      fromBid: currentTrackBidRef.current,
      toBid: nextBid,
      sequenceBlockBid,
      currentIndex: currentIndexRef.current,
    });
    logAudioInterrupt('当前轨道发生切换，执行 pause 并重置 src', {
      fromBid: currentTrackBidRef.current,
      toBid: nextBid,
      fromIndex: currentIndexRef.current,
    });
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
  }, [currentTrack, logAudioInterrupt, resetSegmentState, sequenceBlockBid]);

  useEffect(() => {
    if (!currentTrack || disabled) {
      return;
    }
    const bid = currentTrack.generated_block_bid ?? null;
    if (sequenceBlockBid === null) {
      // High-frequency skip branch; keep silent to reduce noisy debug output.
      return;
    }
    if (isSequenceActive && bid !== sequenceBlockBid) {
      // Wait until sequence index switches to the exact target track.
      return;
    }
    if (shouldResumeRef.current) {
      shouldResumeRef.current = false;
      // Resume from the paused progress instead of restarting from zero.
      const resumed = startPlaybackForTrack({ resume: true });
      if (resumed && bid) {
        // Mark as auto-played to prevent duplicate autoplay restart at 0s.
        autoPlayedTrackRef.current = bid;
      }
      return;
    }
    if (!autoPlay || isPausedRef.current) {
      return;
    }
    if (bid && autoPlayedTrackRef.current === bid) {
      // High-frequency skip branch; keep silent to reduce noisy debug output.
      return;
    }
    logAudioDebug('audio-player-autoplay-attempt', {
      bid,
      sequenceBlockBid,
      isSequenceActive,
      isPaused: isPausedRef.current,
      isStreaming: Boolean(currentTrack.isAudioStreaming),
      segments: currentSegments.length,
      hasUrl: Boolean(currentTrack.audioUrl),
    });
    const started = startPlaybackForTrack();
    if (started && bid) {
      autoPlayedTrackRef.current = bid;
      logAudioDebug('audio-player-autoplay-started', {
        bid,
      });
    }
  }, [
    autoPlay,
    currentSegments.length,
    currentTrack,
    currentTrack?.audioUrl,
    currentTrack?.isAudioStreaming,
    disabled,
    isSequenceActive,
    sequenceBlockBid,
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
    logAudioDebug('audio-player-sequence-switch-track', {
      sequenceBlockBid,
      fromIndex: currentIndexRef.current,
      toIndex: nextIndex,
      isSequenceActive,
    });
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
    logAudioDebug('audio-player-sequence-stop-with-null-bid', {
      isPlaying: isPlayingRef.current,
      isWaitingForSegment: isWaitingForSegmentRef.current,
    });
    logAudioInterrupt('sequenceBlockBid 变为 null，序列要求暂停当前音频', {
      isWaitingForSegment: isWaitingForSegmentRef.current,
    });
    shouldResumeRef.current = false;
    if (isPlayingRef.current || isWaitingForSegmentRef.current) {
      // This pause is sequence-driven, not user-driven. Keep auto-play available
      // so the next sequence item can start automatically.
      pausePlayback({
        traceId: 'sequence-null-bid',
        keepAutoPlay: true,
      });
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
      const hasFinalSegment = segments.some(segment => Boolean(segment?.isFinal));
      if (isSequenceActive && hasFinalSegment) {
        logAudioInterrupt('序列模式检测到 final segment，跳过 URL 补播兜底，直接结束当前轨道', {
          segmentCount: segments.length,
          hasUrl: Boolean(url),
          startAtSeconds:
            playedSecondsRef.current + segmentOffsetRef.current,
          trackDurationMs: track.audioDurationMs ?? 0,
        });
        finishTrack();
        return;
      }
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
    isSequenceActive,
    logAudioInterrupt,
    finishTrack,
    resolveTrackUrl,
    resetSegmentState,
    startSegmentPlayback,
    startUrlPlayback,
  ]);

  useEffect(() => {
    return () => {
      logAudioInterruptRef.current('AudioPlayerList 组件卸载，释放排他权限', {
        currentSrc: currentSrcRef.current,
      });
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

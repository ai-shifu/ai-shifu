import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AudioSegment } from '@/c-utils/audio-utils';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import {
  createAudioContext,
  decodeAudioBufferFromBase64,
  playAudioBuffer,
  resumeAudioContext,
} from '@/lib/audio-playback';
import {
  getNextIndex,
  getPrevIndex,
  normalizeAudioItemList,
  sortAudioSegments,
} from '@/c-utils/audio-playlist';
import ListenPlayer from './ListenPlayer';
import type { ChatContentItem } from './useChatLogicHook';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';

interface ListenModeAudioUrlItem {
  generated_block_bid: string;
  audioUrl?: string;
  audioSegments?: AudioSegment[];
  isAudioStreaming?: boolean;
}

interface ListenModeTestAudioPlayerProps {
  audioUrls: ListenModeAudioUrlItem[];
  className?: string;
  mobileStyle?: boolean;
  interaction?: ChatContentItem | null;
  interactionReadonly?: boolean;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
  isSequenceActive?: boolean;
  onSequencePlay?: () => void;
  onSequencePause?: (traceId?: string) => void;
  onSequenceAdvance?: () => void;
  onSequenceJump?: (blockBid: string | null) => void;
  sequenceBlockBid?: string | null;
}

const ListenModeTestAudioPlayer = ({
  audioUrls,
  className,
  mobileStyle = false,
  interaction,
  interactionReadonly,
  onSend,
  isSequenceActive = false,
  onSequencePlay,
  onSequencePause,
  onSequenceAdvance,
  onSequenceJump,
  sequenceBlockBid = null,
}: ListenModeTestAudioPlayerProps) => {
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef(false);
  const currentUrlRef = useRef<string | null>(null);
  const shouldResumeRef = useRef(false);
  const pendingSequenceBlockRef = useRef<string | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  const streamSessionRef = useRef(0);
  const isStreamingPlaybackRef = useRef(false);
  const isStreamPausedRef = useRef(false);
  const isWaitingForSegmentRef = useRef(false);
  const isPlayingSegmentRef = useRef(false);
  const currentSegmentIndexRef = useRef(0);
  const playedSecondsRef = useRef(0);
  const segmentOffsetRef = useRef(0);
  const segmentStartTimeRef = useRef(0);
  const segmentDurationRef = useRef(0);
  const streamingSegmentsRef = useRef<AudioSegment[]>([]);
  const isTrackStreamingRef = useRef(false);
  const currentTrackRef = useRef<ListenModeAudioUrlItem | null>(null);
  const currentTrackBidRef = useRef<string | null>(null);
  const isUsingStreamRef = useRef(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const playlist = useMemo(
    () => normalizeAudioItemList(audioUrls),
    [audioUrls],
  );
  const currentTrack = useMemo(
    () => playlist[currentIndex] ?? null,
    [playlist, currentIndex],
  );
  const currentSegments = useMemo(() => {
    if (!currentTrack?.audioSegments?.length) {
      return [];
    }
    return sortAudioSegments(currentTrack.audioSegments);
  }, [currentTrack?.audioSegments]);

  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    if (!playlist.length) {
      currentUrlRef.current = null;
      return;
    }
    if (currentIndex >= playlist.length) {
      setCurrentIndex(Math.max(playlist.length - 1, 0));
    }
  }, [playlist.length, currentIndex]);

  useEffect(() => {
    streamingSegmentsRef.current = currentSegments;
  }, [currentSegments]);

  useEffect(() => {
    isTrackStreamingRef.current = Boolean(currentTrack?.isAudioStreaming);
  }, [currentTrack?.isAudioStreaming]);

  useEffect(() => {
    currentTrackRef.current = currentTrack;
  }, [currentTrack]);

  useEffect(() => {
    if (!sequenceBlockBid || !playlist.length) {
      return;
    }
    const nextIndex = playlist.findIndex(
      item => item.generated_block_bid === sequenceBlockBid,
    );
    if (nextIndex < 0 || nextIndex === currentIndex) {
      return;
    }
    shouldResumeRef.current = isSequenceActive;
    setCurrentIndex(nextIndex);
  }, [sequenceBlockBid, playlist, currentIndex, isSequenceActive]);

  const startPlayback = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    isUsingStreamRef.current = false;
    requestExclusive(() => {
      audio.pause();
    });
    const playPromise = audio.play();
    if (playPromise && typeof playPromise.catch === 'function') {
      playPromise.catch(() => {});
    }
  }, [requestExclusive]);

  const shouldUseUrl = useCallback(
    (track: ListenModeAudioUrlItem | null) =>
      Boolean(track?.audioUrl) && !track?.isAudioStreaming,
    [],
  );

  const shouldUseStream = useCallback(
    (track: ListenModeAudioUrlItem | null) =>
      Boolean(
        track &&
        !shouldUseUrl(track) &&
        (track.isAudioStreaming ||
          (track.audioSegments && track.audioSegments.length > 0)),
      ),
    [shouldUseUrl],
  );

  const handleEnded = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    pendingSequenceBlockRef.current = null;
    if (isSequenceActive) {
      onSequenceAdvance?.();
      return;
    }
    onSequenceAdvance?.();
    const nextIndex = getNextIndex(currentIndex, playlist.length);
    if (nextIndex === currentIndex) {
      shouldResumeRef.current = false;
      setIsPlaying(false);
      return;
    }
    shouldResumeRef.current = true;
    setCurrentIndex(nextIndex);
  }, [playlist.length, currentIndex, onSequenceAdvance, isSequenceActive]);

  const stopStreamPlayback = useCallback(
    (options?: { keepPosition?: boolean; release?: boolean }) => {
      streamSessionRef.current += 1;
      isStreamingPlaybackRef.current = false;
      isUsingStreamRef.current = false;
      isStreamPausedRef.current = false;
      isWaitingForSegmentRef.current = false;
      isPlayingSegmentRef.current = false;
      if (!options?.keepPosition) {
        playedSecondsRef.current = 0;
        segmentOffsetRef.current = 0;
        currentSegmentIndexRef.current = 0;
      }
      segmentStartTimeRef.current = 0;
      segmentDurationRef.current = 0;
      if (sourceNodeRef.current) {
        try {
          sourceNodeRef.current.stop();
          sourceNodeRef.current.disconnect();
        } catch {}
        sourceNodeRef.current = null;
      }
      if (audioContextRef.current) {
        audioContextRef.current.suspend().catch(() => {});
        audioContextRef.current.close().catch(() => {});
        audioContextRef.current = null;
      }
      if (options?.release !== false) {
        releaseExclusive();
      }
    },
    [releaseExclusive],
  );

  const startUrlPlayback = useCallback(
    (url: string, startAtSeconds: number = 0) => {
      const audio = audioRef.current;
      if (!audio) {
        return;
      }
      isUsingStreamRef.current = false;
      if (currentUrlRef.current !== url) {
        currentUrlRef.current = url;
        audio.src = url;
        audio.load();
      }
      if (Number.isFinite(startAtSeconds) && startAtSeconds > 0) {
        try {
          audio.currentTime = Math.max(0, startAtSeconds);
        } catch {}
      }
      startPlayback();
    },
    [startPlayback],
  );

  const playStreamSegment = useCallback(
    async (
      index: number,
      sessionId: number,
      startOffsetSeconds: number = 0,
    ) => {
      if (streamSessionRef.current !== sessionId) {
        isPlayingSegmentRef.current = false;
        return;
      }
      if (isPlayingSegmentRef.current) {
        return;
      }

      const segments = streamingSegmentsRef.current;
      const track = currentTrackRef.current;
      if (!track) {
        stopStreamPlayback();
        return;
      }

      if (index >= segments.length) {
        if (isTrackStreamingRef.current) {
          isWaitingForSegmentRef.current = true;
          return;
        }
        if (track.audioUrl) {
          const startAt = playedSecondsRef.current;
          stopStreamPlayback({ keepPosition: true, release: false });
          startUrlPlayback(track.audioUrl, startAt);
          return;
        }
        isStreamingPlaybackRef.current = false;
        isUsingStreamRef.current = false;
        setIsPlaying(false);
        isPlayingRef.current = false;
        releaseExclusive();
        handleEnded();
        return;
      }

      isWaitingForSegmentRef.current = false;
      isPlayingSegmentRef.current = true;

      try {
        if (!audioContextRef.current) {
          audioContextRef.current = createAudioContext();
        }
        const audioContext = audioContextRef.current;
        await resumeAudioContext(audioContext);
        if (streamSessionRef.current !== sessionId) {
          isPlayingSegmentRef.current = false;
          return;
        }
        const segment = segments[index];
        currentSegmentIndexRef.current = index;

        const audioBuffer = await decodeAudioBufferFromBase64(
          audioContext,
          segment.audioData,
        );
        if (streamSessionRef.current !== sessionId) {
          isPlayingSegmentRef.current = false;
          return;
        }

        const initialOffset = Number.isFinite(startOffsetSeconds)
          ? Math.max(0, startOffsetSeconds)
          : 0;
        segmentOffsetRef.current = initialOffset;
        segmentStartTimeRef.current = audioContext.currentTime;
        segmentDurationRef.current = audioBuffer.duration || 0;

        const sourceNode = playAudioBuffer(
          audioContext,
          audioBuffer,
          () => {
            if (streamSessionRef.current !== sessionId) return;
            isPlayingSegmentRef.current = false;
            const remainingSeconds = Math.max(
              0,
              (audioBuffer.duration || 0) - initialOffset,
            );
            playedSecondsRef.current += remainingSeconds;
            segmentOffsetRef.current = 0;
            segmentDurationRef.current = 0;
            if (isStreamingPlaybackRef.current) {
              playStreamSegment(index + 1, sessionId);
            }
          },
          initialOffset,
        );
        sourceNodeRef.current = sourceNode;
        setIsPlaying(true);
        isPlayingRef.current = true;
      } catch {
        isPlayingSegmentRef.current = false;
        isStreamingPlaybackRef.current = false;
        setIsPlaying(false);
        isPlayingRef.current = false;
        releaseExclusive();
      }
    },
    [handleEnded, releaseExclusive, startUrlPlayback, stopStreamPlayback],
  );

  const startStreamPlayback = useCallback(
    (options?: { resume?: boolean }) => {
      const track = currentTrackRef.current;
      if (!track || !shouldUseStream(track)) {
        return;
      }

      if (!options?.resume) {
        playedSecondsRef.current = 0;
        segmentOffsetRef.current = 0;
        currentSegmentIndexRef.current = 0;
      }

      const sessionId = streamSessionRef.current + 1;
      streamSessionRef.current = sessionId;
      isStreamingPlaybackRef.current = true;
      isStreamPausedRef.current = false;
      isUsingStreamRef.current = true;
      isWaitingForSegmentRef.current = false;
      requestExclusive(() => {
        stopStreamPlayback();
      });
      setIsPlaying(true);
      isPlayingRef.current = true;
      playStreamSegment(
        currentSegmentIndexRef.current,
        sessionId,
        options?.resume ? segmentOffsetRef.current : 0,
      );
    },
    [playStreamSegment, requestExclusive, shouldUseStream, stopStreamPlayback],
  );

  const updateStreamPlaybackPosition = useCallback(() => {
    const audioContext = audioContextRef.current;
    if (!audioContext || !sourceNodeRef.current) {
      return;
    }
    const elapsed = Math.max(
      0,
      audioContext.currentTime - segmentStartTimeRef.current,
    );
    const duration = segmentDurationRef.current;
    const nextOffset = Math.min(
      segmentOffsetRef.current + elapsed,
      duration > 0 ? duration : segmentOffsetRef.current + elapsed,
    );
    playedSecondsRef.current += Math.max(
      0,
      nextOffset - segmentOffsetRef.current,
    );
    segmentOffsetRef.current = nextOffset;
  }, []);

  const pauseStreamPlayback = useCallback(
    (_traceId?: string) => {
      if (!isStreamingPlaybackRef.current) {
        return;
      }
      isStreamPausedRef.current = true;
      updateStreamPlaybackPosition();
      stopStreamPlayback({ keepPosition: true });
      setIsPlaying(false);
      isPlayingRef.current = false;
    },
    [stopStreamPlayback, updateStreamPlaybackPosition],
  );

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    const track = currentTrack;
    const nextBid = track?.generated_block_bid ?? null;
    const isTrackChanged = currentTrackBidRef.current !== nextBid;
    if (isTrackChanged) {
      currentTrackBidRef.current = nextBid;
      isUsingStreamRef.current = false;
      stopStreamPlayback({ release: false });
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      currentUrlRef.current = null;
      playedSecondsRef.current = 0;
      segmentOffsetRef.current = 0;
      currentSegmentIndexRef.current = 0;
    }

    if (track && shouldUseUrl(track) && track.audioUrl) {
      if (isUsingStreamRef.current) {
        updateStreamPlaybackPosition();
        stopStreamPlayback({ keepPosition: true, release: false });
        startUrlPlayback(track.audioUrl, playedSecondsRef.current);
        return;
      }
      if (!isUsingStreamRef.current) {
        if (currentUrlRef.current !== track.audioUrl) {
          currentUrlRef.current = track.audioUrl;
          audio.src = track.audioUrl;
          audio.load();
        }
        if (isPlayingRef.current || shouldResumeRef.current) {
          shouldResumeRef.current = false;
          startPlayback();
        }
      }
      return;
    }

    if (track && shouldUseStream(track)) {
      if (isPlayingRef.current || shouldResumeRef.current) {
        const resume = !isTrackChanged && isStreamPausedRef.current;
        shouldResumeRef.current = false;
        startStreamPlayback({ resume });
      }
    }
  }, [
    currentTrack,
    shouldUseStream,
    shouldUseUrl,
    startPlayback,
    startStreamPlayback,
    startUrlPlayback,
    stopStreamPlayback,
    updateStreamPlaybackPosition,
  ]);

  useEffect(() => {
    if (!isUsingStreamRef.current) {
      return;
    }
    if (!isStreamingPlaybackRef.current || isStreamPausedRef.current) {
      return;
    }
    if (!isWaitingForSegmentRef.current) {
      return;
    }
    playStreamSegment(
      currentSegmentIndexRef.current,
      streamSessionRef.current,
      segmentOffsetRef.current,
    );
  }, [
    currentSegments.length,
    currentTrack?.isAudioStreaming,
    playStreamSegment,
  ]);

  useEffect(() => {
    return () => {
      releaseExclusive();
    };
  }, [releaseExclusive]);

  const syncSequenceByBlock = useCallback(
    (blockBid: string | null) => {
      if (!blockBid) {
        return;
      }
      onSequenceJump?.(blockBid);
    },
    [onSequenceJump],
  );

  const handlePlay = useCallback(() => {
    if (!playlist.length || !currentTrack) {
      return;
    }
    const pendingBlock = pendingSequenceBlockRef.current;
    if (pendingBlock) {
      syncSequenceByBlock(pendingBlock);
      pendingSequenceBlockRef.current = null;
    } else if (!isSequenceActive) {
      syncSequenceByBlock(currentTrack.generated_block_bid ?? null);
    }
    onSequencePlay?.();
    if (shouldUseUrl(currentTrack) && currentTrack.audioUrl) {
      if (!audioRef.current?.src) {
        currentUrlRef.current = currentTrack.audioUrl;
        audioRef.current!.src = currentTrack.audioUrl;
        audioRef.current!.load();
      }
      startPlayback();
      return;
    }
    if (shouldUseStream(currentTrack)) {
      startStreamPlayback({ resume: isStreamPausedRef.current });
    }
  }, [
    currentTrack,
    playlist.length,
    startPlayback,
    startStreamPlayback,
    isSequenceActive,
    onSequencePlay,
    shouldUseStream,
    shouldUseUrl,
    syncSequenceByBlock,
  ]);

  const handlePause = useCallback(
    (_traceId?: string) => {
      onSequencePause?.(_traceId);
      if (isUsingStreamRef.current || shouldUseStream(currentTrack)) {
        pauseStreamPlayback(_traceId);
        return;
      }
      audioRef.current?.pause();
    },
    [currentTrack, onSequencePause, pauseStreamPlayback, shouldUseStream],
  );

  const handleNext = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    const nextIndex = getNextIndex(currentIndex, playlist.length);
    if (nextIndex === currentIndex) {
      return;
    }
    if (isPlayingRef.current) {
      shouldResumeRef.current = true;
      syncSequenceByBlock(playlist[nextIndex]?.generated_block_bid ?? null);
    } else {
      pendingSequenceBlockRef.current =
        playlist[nextIndex]?.generated_block_bid ?? null;
    }
    setCurrentIndex(nextIndex);
  }, [playlist.length, currentIndex, playlist, syncSequenceByBlock]);

  const handlePrev = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    const prevIndex = getPrevIndex(currentIndex, playlist.length);
    if (prevIndex === currentIndex) {
      return;
    }
    if (isPlayingRef.current) {
      shouldResumeRef.current = true;
      syncSequenceByBlock(playlist[prevIndex]?.generated_block_bid ?? null);
    } else {
      pendingSequenceBlockRef.current =
        playlist[prevIndex]?.generated_block_bid ?? null;
    }
    setCurrentIndex(prevIndex);
  }, [playlist.length, currentIndex, playlist, syncSequenceByBlock]);

  const prevDisabled = !playlist.length || currentIndex <= 0;
  const nextDisabled = !playlist.length || currentIndex >= playlist.length - 1;

  return (
    <>
      <ListenPlayer
        className={className}
        mobileStyle={mobileStyle}
        onPrev={handlePrev}
        onPlay={handlePlay}
        onPause={handlePause}
        onNext={handleNext}
        prevDisabled={prevDisabled}
        nextDisabled={nextDisabled}
        isAudioPlaying={isPlaying}
        interaction={interaction}
        interactionReadonly={interactionReadonly}
        onSend={onSend}
      />
      <audio
        ref={audioRef}
        preload='metadata'
        playsInline
        autoPlay
        onPlay={() => {
          console.log('onPlay');
          if (isUsingStreamRef.current) {
            return;
          }
          setIsPlaying(true);
          requestExclusive(() => {
            audioRef.current?.pause();
          });
        }}
        onPause={() => {
          console.log('onPause');
          if (isUsingStreamRef.current) {
            return;
          }
          setIsPlaying(false);
          releaseExclusive();
        }}
        onEnded={() => {
          if (isUsingStreamRef.current) {
            return;
          }
          handleEnded();
        }}
        onError={() => {
          console.log('onError');
          if (isUsingStreamRef.current) {
            return;
          }
          setIsPlaying(false);
        }}
        className='hidden'
      />
    </>
  );
};

export default memo(ListenModeTestAudioPlayer);

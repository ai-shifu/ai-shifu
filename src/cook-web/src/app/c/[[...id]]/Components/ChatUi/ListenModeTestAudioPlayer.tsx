import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import ListenPlayer from './ListenPlayer';
import type { ChatContentItem } from './useChatLogicHook';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';

const normalizeUrlList = (audioUrls: string[]) => {
  const normalized = audioUrls
    .map(url => url.trim())
    .filter((url): url is string => Boolean(url));
  return Array.from(new Set(normalized));
};

const getNextIndex = (currentIndex: number, listLength: number) => {
  if (listLength <= 0) {
    return 0;
  }
  return currentIndex + 1 < listLength ? currentIndex + 1 : currentIndex;
};

const getPrevIndex = (currentIndex: number, listLength: number) => {
  if (listLength <= 0) {
    return 0;
  }
  return currentIndex > 0 ? currentIndex - 1 : currentIndex;
};

interface ListenModeTestAudioPlayerProps {
  audioUrls: string[];
  className?: string;
  mobileStyle?: boolean;
  interaction?: ChatContentItem | null;
  interactionReadonly?: boolean;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
  isSequenceActive?: boolean;
  onSequencePlay?: () => void;
  onSequencePause?: (traceId?: string) => void;
  onSequenceAdvance?: () => void;
  onSequenceJump?: (audioUrl: string | null) => void;
  sequenceAudioUrl?: string | null;
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
  sequenceAudioUrl = null,
}: ListenModeTestAudioPlayerProps) => {
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef(false);
  const currentUrlRef = useRef<string | null>(null);
  const shouldResumeRef = useRef(false);
  const pendingSequenceUrlRef = useRef<string | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const playlist = useMemo(() => normalizeUrlList(audioUrls), [audioUrls]);

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
    if (!sequenceAudioUrl || !playlist.length) {
      return;
    }
    const normalizedUrl = sequenceAudioUrl.trim();
    if (!normalizedUrl) {
      return;
    }
    const nextIndex = playlist.findIndex(url => url === normalizedUrl);
    if (nextIndex < 0 || nextIndex === currentIndex) {
      return;
    }
    shouldResumeRef.current = isSequenceActive;
    setCurrentIndex(nextIndex);
  }, [sequenceAudioUrl, playlist, currentIndex, isSequenceActive]);

  const startPlayback = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    requestExclusive(() => {
      audio.pause();
    });
    const playPromise = audio.play();
    if (playPromise && typeof playPromise.catch === 'function') {
      playPromise.catch(() => {});
    }
  }, [requestExclusive]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !playlist.length) {
      return;
    }
    const nextUrl = playlist[currentIndex];
    if (!nextUrl) {
      return;
    }
    if (currentUrlRef.current === nextUrl) {
      return;
    }
    currentUrlRef.current = nextUrl;
    audio.src = nextUrl;
    audio.load();
    if (isPlayingRef.current || shouldResumeRef.current) {
      shouldResumeRef.current = false;
      startPlayback();
    }
  }, [currentIndex, playlist, startPlayback]);

  useEffect(() => {
    return () => {
      releaseExclusive();
    };
  }, [releaseExclusive]);

  const syncSequenceByUrl = useCallback(
    (url: string | null) => {
      if (!url) {
        return;
      }
      onSequenceJump?.(url);
    },
    [onSequenceJump],
  );

  const handlePlay = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    const pendingUrl = pendingSequenceUrlRef.current;
    if (pendingUrl) {
      syncSequenceByUrl(pendingUrl);
      pendingSequenceUrlRef.current = null;
    } else if (!isSequenceActive) {
      syncSequenceByUrl(playlist[currentIndex] ?? null);
    }
    onSequencePlay?.();
    if (!audioRef.current?.src && playlist[0]) {
      currentUrlRef.current = playlist[currentIndex] ?? playlist[0];
      audioRef.current!.src = currentUrlRef.current!;
      audioRef.current!.load();
    }
    startPlayback();
  }, [
    playlist,
    currentIndex,
    startPlayback,
    isSequenceActive,
    onSequencePlay,
    syncSequenceByUrl,
  ]);

  const handlePause = useCallback((_traceId?: string) => {
    onSequencePause?.(_traceId);
    audioRef.current?.pause();
  }, [onSequencePause]);

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
      syncSequenceByUrl(playlist[nextIndex] ?? null);
    } else {
      pendingSequenceUrlRef.current = playlist[nextIndex] ?? null;
    }
    setCurrentIndex(nextIndex);
  }, [playlist.length, currentIndex, playlist, syncSequenceByUrl]);

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
      syncSequenceByUrl(playlist[prevIndex] ?? null);
    } else {
      pendingSequenceUrlRef.current = playlist[prevIndex] ?? null;
    }
    setCurrentIndex(prevIndex);
  }, [playlist.length, currentIndex, playlist, syncSequenceByUrl]);

  const handleEnded = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    pendingSequenceUrlRef.current = null;
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

  const prevDisabled = !playlist.length || currentIndex <= 0;
  const nextDisabled =
    !playlist.length || currentIndex >= playlist.length - 1;
  const shouldRenderPlayer = Boolean(playlist.length || interaction);

  if (!shouldRenderPlayer) {
    return null;
  }

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
          setIsPlaying(true);
          requestExclusive(() => {
            audioRef.current?.pause();
          });
        }}
        onPause={() => {
          console.log('onPause');
          setIsPlaying(false);
          releaseExclusive();
        }}
        onEnded={handleEnded}
        onError={() => {
          console.log('onError');
          setIsPlaying(false);
        }}
        className='hidden'
      />
    </>
  );
};

export default memo(ListenModeTestAudioPlayer);

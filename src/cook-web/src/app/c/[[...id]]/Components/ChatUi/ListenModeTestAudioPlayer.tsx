import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';

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
}

const ListenModeTestAudioPlayer = ({
  audioUrls,
  className,
}: ListenModeTestAudioPlayerProps) => {
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef(false);
  const currentUrlRef = useRef<string | null>(null);
  const shouldResumeRef = useRef(false);
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

  const currentLabel = useMemo(() => {
    const url = playlist[currentIndex];
    if (!url) {
      return 'No audio';
    }
    try {
      const parsed = new URL(url);
      const name = parsed.pathname.split('/').pop() || url;
      return decodeURIComponent(name);
    } catch {
      return url;
    }
  }, [playlist, currentIndex]);

  const handlePlay = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    if (!audioRef.current?.src && playlist[0]) {
      currentUrlRef.current = playlist[currentIndex] ?? playlist[0];
      audioRef.current.src = currentUrlRef.current;
      audioRef.current.load();
    }
    startPlayback();
  }, [playlist, currentIndex, startPlayback]);

  const handlePause = useCallback(() => {
    audioRef.current?.pause();
  }, []);

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
    }
    setCurrentIndex(nextIndex);
  }, [playlist.length, currentIndex]);

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
    }
    setCurrentIndex(prevIndex);
  }, [playlist.length, currentIndex]);

  const handleEnded = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    const nextIndex = getNextIndex(currentIndex, playlist.length);
    if (nextIndex === currentIndex) {
      shouldResumeRef.current = false;
      setIsPlaying(false);
      return;
    }
    shouldResumeRef.current = true;
    setCurrentIndex(nextIndex);
  }, [playlist.length, currentIndex]);

  if (!playlist.length) {
    return null;
  }

  return (
    <div className={cn('w-full', className)}>
      <div className='rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 shadow-sm'>
        <div className='flex items-center justify-between gap-3'>
          <div className='min-w-0'>
            <p className='text-xs font-semibold uppercase tracking-wide text-foreground/60'>
              Listen Mode Test Player
            </p>
            <p className='truncate text-sm font-medium text-[var(--card-foreground)]'>
              {currentLabel}
            </p>
          </div>
          <div className='flex items-center gap-2'>
            <button
              type='button'
              onClick={handlePrev}
              className='rounded-full border border-[var(--border)] px-3 py-1 text-xs font-semibold text-[var(--card-foreground)]'
            >
              Prev
            </button>
            <button
              type='button'
              onClick={isPlaying ? handlePause : handlePlay}
              className='rounded-full bg-[var(--primary)] px-4 py-1 text-xs font-semibold text-[var(--primary-foreground)]'
            >
              {isPlaying ? 'Pause' : 'Play'}
            </button>
            <button
              type='button'
              onClick={handleNext}
              className='rounded-full border border-[var(--border)] px-3 py-1 text-xs font-semibold text-[var(--card-foreground)]'
            >
              Next
            </button>
          </div>
        </div>
        <div className='mt-2 flex items-center text-xs text-foreground/60'>
          <span>
            {currentIndex + 1}/{playlist.length}
          </span>
        </div>
      </div>
      <audio
        ref={audioRef}
        preload='metadata'
        playsInline
        onPlay={() => {
          setIsPlaying(true);
          requestExclusive(() => {
            audioRef.current?.pause();
          });
        }}
        onPause={() => {
          setIsPlaying(false);
          releaseExclusive();
        }}
        onEnded={handleEnded}
        onError={() => {
          setIsPlaying(false);
        }}
        className='hidden'
      />
    </div>
  );
};

export default memo(ListenModeTestAudioPlayer);

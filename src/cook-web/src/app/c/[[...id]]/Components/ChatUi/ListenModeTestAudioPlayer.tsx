import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';

const PLAY_MODE_ORDER = ['list', 'random', 'single'] as const;

type PlayMode = (typeof PLAY_MODE_ORDER)[number];

const PLAY_MODE_LABEL: Record<PlayMode, string> = {
  list: 'List',
  random: 'Random',
  single: 'Single',
};

const normalizeUrlList = (audioUrls: string[]) => {
  const normalized = audioUrls
    .map(url => url.trim())
    .filter((url): url is string => Boolean(url));
  return Array.from(new Set(normalized));
};

const getNextIndex = (
  currentIndex: number,
  listLength: number,
  mode: PlayMode,
) => {
  if (listLength <= 0) {
    return 0;
  }
  if (mode === 'random') {
    return Math.floor(Math.random() * listLength);
  }
  if (mode === 'list') {
    return (currentIndex + 1) % listLength;
  }
  return currentIndex;
};

const getPrevIndex = (
  currentIndex: number,
  listLength: number,
  mode: PlayMode,
) => {
  if (listLength <= 0) {
    return 0;
  }
  if (mode === 'random') {
    return Math.floor(Math.random() * listLength);
  }
  if (mode === 'list') {
    return (currentIndex - 1 + listLength) % listLength;
  }
  return currentIndex;
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
  const [playMode, setPlayMode] = useState<PlayMode>('list');
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
      setCurrentIndex(0);
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
      audioRef.current!.src = currentUrlRef.current ?? '';
      audioRef.current!.load();
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
    if (isPlayingRef.current) {
      shouldResumeRef.current = true;
    }
    const nextIndex = getNextIndex(currentIndex, playlist.length, playMode);
    setCurrentIndex(nextIndex);
  }, [playlist.length, currentIndex, playMode]);

  const handlePrev = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    if (isPlayingRef.current) {
      shouldResumeRef.current = true;
    }
    const prevIndex = getPrevIndex(currentIndex, playlist.length, playMode);
    setCurrentIndex(prevIndex);
  }, [playlist.length, currentIndex, playMode]);

  const handleEnded = useCallback(() => {
    if (!playlist.length) {
      return;
    }
    if (playMode === 'single') {
      const audio = audioRef.current;
      if (audio) {
        audio.currentTime = 0;
        startPlayback();
      }
      return;
    }
    const nextIndex = getNextIndex(currentIndex, playlist.length, playMode);
    if (nextIndex === currentIndex) {
      const audio = audioRef.current;
      if (audio) {
        audio.currentTime = 0;
        startPlayback();
      }
      return;
    }
    shouldResumeRef.current = true;
    setCurrentIndex(nextIndex);
  }, [playlist.length, currentIndex, playMode, startPlayback]);

  const handleToggleMode = useCallback(() => {
    const currentIdx = PLAY_MODE_ORDER.indexOf(playMode);
    const nextIdx = (currentIdx + 1) % PLAY_MODE_ORDER.length;
    setPlayMode(PLAY_MODE_ORDER[nextIdx]);
  }, [playMode]);

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
        <div className='mt-2 flex items-center justify-between text-xs text-foreground/60'>
          <span>
            {currentIndex + 1}/{playlist.length}
          </span>
          <button
            type='button'
            onClick={handleToggleMode}
            className='rounded-full border border-[var(--border)] px-3 py-1 font-semibold text-[var(--card-foreground)]'
          >
            Mode: {PLAY_MODE_LABEL[playMode]}
          </button>
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

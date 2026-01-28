import React, { memo } from 'react';
import {
  MoreVertical,
  Volume2,
  RotateCcw,
  RotateCw,
  SquarePen,
  Scan,
  Sparkles,
} from 'lucide-react';
import styles from './ListenPlayer.module.scss';
import { cn } from '@/lib/utils';

interface ListenPlayerProps {
  className?: string;
  onMore?: () => void;
  onVolume?: () => void;
  onPrev?: () => void;
  onPlay?: () => void;
  onNext?: () => void;
  onFullscreen?: () => void;
  onSubtitles?: () => void;
  onNotes?: () => void;
}

const ListenPlayer = ({
  className,
  onMore,
  onVolume,
  onPrev,
  onPlay,
  onNext,
  onFullscreen,
  onSubtitles,
  onNotes
}: ListenPlayerProps) => {
  return (
    <div className={cn(styles.playerContainer, className)}>
      <div className={styles.controlGroup}>
        <button type="button" aria-label="More options" onClick={onMore}>
          <MoreVertical size={32} />
        </button>
        <button type="button" aria-label="Volume" onClick={onVolume}>
          <Volume2 size={32} />
        </button>
      </div>

      <div className={styles.controlGroup}>
        <button type="button" aria-label="Rewind" onClick={onPrev}>
          <RotateCcw size={32} />
        </button>
        <button
          type='button'
          aria-label='Play'
          className={styles.playButton}
          onClick={onPlay}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="34" height="34" viewBox="0 0 34 34" fill="none">
            <path d="M16.6667 33.3333C25.8714 33.3333 33.3333 25.8714 33.3333 16.6667C33.3333 7.46192 25.8714 0 16.6667 0C7.46192 0 0 7.46192 0 16.6667C0 25.8714 7.46192 33.3333 16.6667 33.3333Z" fill="#0A0A0A"/>
            <path d="M13.3333 10L23.3333 16.6667L13.3333 23.3333V10Z" fill="white"/>
          </svg>
        </button>
        <button type="button" aria-label="Forward" onClick={onNext}>
          <RotateCw size={32} />
        </button>
        <button type="button" aria-label="Fullscreen" onClick={onFullscreen}>
          <Scan size={32} />
        </button>
      </div>

      <div className={styles.separator} />

      <div className={styles.controlGroup}>
        <button type="button" aria-label="Subtitles" onClick={onSubtitles}>
          <Sparkles size={32} />
        </button>
        <button type="button" aria-label="Notes" onClick={onNotes}>
          <SquarePen size={32} />
        </button>
      </div>
    </div>
  );
};

ListenPlayer.displayName = 'ListenPlayer';

export default memo(ListenPlayer);
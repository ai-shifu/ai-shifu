import React, { memo } from 'react';
import {
  MoreVertical,
  Volume2,
  RotateCcw,
  Play,
  RotateCw,
  SquarePen,
  Scan,
  Sparkles,
} from 'lucide-react';
import styles from './ListenPlayer.module.scss';
import { cn } from '@/lib/utils';

interface ListenPlayerProps {
  className?: string;
}

const ListenPlayer = ({ className }: ListenPlayerProps) => {
  return (
    <div className={cn(styles.playerContainer, className)}>
      <div className={styles.controlGroup}>
        <button
          type='button'
          aria-label='More options'
        >
          <MoreVertical size={32} />
        </button>
        <button
          type='button'
          aria-label='Volume'
        >
          <Volume2 size={32} />
        </button>
      </div>

      <div className={styles.controlGroup}>
        <button
          type='button'
          aria-label='Rewind'
        >
          <RotateCcw size={32} />
        </button>
        <button
          type='button'
          aria-label='Play'
          className={styles.playButton}
        >
          <div className={styles.playIconWrapper}>
            <Play
              size={20}
              fill='#fff'
              strokeWidth={0}
            />
          </div>
        </button>
        <button
          type='button'
          aria-label='Forward'
        >
          <RotateCw size={32} />
        </button>
        <button
          type='button'
          aria-label='Fullscreen'
        >
          <Scan size={32} />
        </button>
      </div>

      <div className={styles.separator} />

      <div className={styles.controlGroup}>
        <button
          type='button'
          aria-label='Subtitles'
        >
          <Sparkles size={32} />
        </button>
        <button
          type='button'
          aria-label='Notes'
        >
          <SquarePen size={32} />
        </button>
      </div>
    </div>
  );
};

ListenPlayer.displayName = 'ListenPlayer';

export default memo(ListenPlayer);

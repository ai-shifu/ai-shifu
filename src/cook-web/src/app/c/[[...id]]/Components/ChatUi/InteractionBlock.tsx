import React, { useState, useMemo } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { LikeStatus } from '@/c-api/studyV2';
import { postGeneratedContentAction, LIKE_STATUS } from '@/c-api/studyV2';
import { RefreshCcw } from 'lucide-react';

type Size = 'sm' | 'md' | 'lg';

export interface InteractionBlockProps {
  shifu_bid: string;
  generated_block_bid: string;
  like_status?: LikeStatus | null; // initial status
  readonly?: boolean;
  disabled?: boolean;
  size?: Size;
  className?: string;
  onRefresh?: (generated_block_bid: string) => void;
}

const sizeMap: Record<Size, number> = {
  sm: 16,
  md: 20,
  lg: 24,
};

/**
 * InteractionBlock
 * Self-contained like/dislike icon buttons with internal state.
 */
export default function InteractionBlock({
  shifu_bid,
  generated_block_bid,
  like_status = LIKE_STATUS.NONE,
  readonly = false,
  disabled = false,
  className,
  onRefresh,
}: InteractionBlockProps) {
  const [status, setStatus] = useState<LikeStatus>(
    (like_status as LikeStatus) ?? LIKE_STATUS.NONE,
  );

  const isLike = status === LIKE_STATUS.LIKE;
  const isDislike = status === LIKE_STATUS.DISLIKE;

  const likeBtnStyle = useMemo(
    () => ({
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 28,
      height: 14,
      cursor: disabled ? 'not-allowed' : 'pointer',
    }),
    [disabled],
  );

  const dislikeBtnStyle = useMemo(
    () => ({
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 28,
      height: 14,
      cursor: disabled ? 'not-allowed' : 'pointer',
    }),
    [disabled],
  );

  const refreshBtnStyle = useMemo(
    () => ({
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 28,
      height: 14,
      cursor: disabled ? 'not-allowed' : 'pointer',
    }),
    [disabled],
  );

  const send = (action: LikeStatus) => {
    try {
      postGeneratedContentAction({
        shifu_bid,
        generated_block_bid,
        action,
      });
    } catch (e) {
      // errors handled by request layer toast; ignore here
    }
  };

  const onLike = () => {
    if (disabled || readonly) return;
    setStatus(prev => {
      const next: LikeStatus =
        prev === LIKE_STATUS.LIKE ? LIKE_STATUS.NONE : LIKE_STATUS.LIKE;
      send(next);
      return next;
    });
  };
  const onDislike = () => {
    if (disabled || readonly) return;
    setStatus(prev => {
      const next: LikeStatus =
        prev === LIKE_STATUS.DISLIKE ? LIKE_STATUS.NONE : LIKE_STATUS.DISLIKE;
      send(next);
      return next;
    });
  };

  return (
    <div
      className={cn(['interaction-block'], className)}
      style={{ display: 'flex', alignItems: 'center', paddingLeft: 20 }}
    >
      <button
        type='button'
        aria-label='Like'
        aria-pressed={isLike}
        disabled={disabled || readonly}
        onClick={onLike}
        title='Like'
        style={likeBtnStyle}
      >
        <ThumbsUp
          size={14}
          className={cn(
            isLike ? 'text-blue-500' : 'text-gray-400',
            'w-5',
            'h-5',
          )}
        />
      </button>

      <button
        type='button'
        aria-label='Dislike'
        aria-pressed={isDislike}
        disabled={disabled || readonly}
        onClick={onDislike}
        title='Dislike'
        style={dislikeBtnStyle}
      >
        <ThumbsDown
          size={14}
          className={cn(
            isDislike ? 'text-blue-500' : 'text-gray-400',
            'w-5',
            'h-5',
          )}
        />
      </button>
      <button
        type='button'
        aria-label='Refresh'
        aria-pressed={false}
        style={refreshBtnStyle}
        disabled={disabled || readonly}
        onClick={() => onRefresh?.(generated_block_bid)}
      >
        <RefreshCcw
          size={14}
          className={cn('text-gray-400', 'w-5', 'h-5')}
        />
      </button>
    </div>
  );
}

import React, { useState, useMemo } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { LikeStatus } from '@/c-api/studyV2';
import { postGeneratedContentAction } from '@/c-api/studyV2';

type Size = 'sm' | 'md' | 'lg';

export interface InteractionBlockProps {
  shifu_bid: string;
  generated_block_bid: string;
  like_status?: LikeStatus | null; // initial status
  readonly?: boolean;
  disabled?: boolean;
  size?: Size;
  className?: string;
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
  like_status = 'none',
  readonly = false,
  disabled = false,
  size = 'md',
  className,
}: InteractionBlockProps) {
  const [status, setStatus] = useState<LikeStatus>(
    (like_status as LikeStatus) ?? 'none',
  );

  const iconSize = sizeMap[size];
  const isLike = status === 'like';
  const isDislike = status === 'dislike';

  const likeBtnStyle = useMemo(
    () => ({
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: iconSize + 12,
      height: iconSize + 12,
      borderRadius: 6,
      background: isLike ? 'rgba(22,163,74,0.12)' : 'transparent',
      border: '1px solid',
      borderColor: isLike ? 'rgba(22,163,74,0.35)' : 'rgba(107,114,128,0.25)',
      cursor: disabled ? 'not-allowed' : 'pointer',
    }),
    [iconSize, isLike, disabled],
  );

  const dislikeBtnStyle = useMemo(
    () => ({
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: iconSize + 12,
      height: iconSize + 12,
      borderRadius: 6,
      background: isDislike ? 'rgba(239,68,68,0.12)' : 'transparent',
      border: '1px solid',
      borderColor: isDislike
        ? 'rgba(239,68,68,0.35)'
        : 'rgba(107,114,128,0.25)',
      cursor: disabled ? 'not-allowed' : 'pointer',
    }),
    [iconSize, isDislike, disabled],
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
      const next: LikeStatus = prev === 'like' ? 'none' : 'like';
      send(next);
      return next;
    });
  };
  const onDislike = () => {
    if (disabled || readonly) return;
    setStatus(prev => {
      const next: LikeStatus = prev === 'dislike' ? 'none' : 'dislike';
      send(next);
      return next;
    });
  };

  return (
    <div
      className={cn('interaction-block', className)}
      style={{ display: 'flex', alignItems: 'center', gap: 8 }}
    >
      <button
        type="button"
        aria-label="Like"
        aria-pressed={isLike}
        disabled={disabled || readonly}
        onClick={onLike}
        title="Like"
        style={likeBtnStyle}
      >
        <ThumbsUp
          size={iconSize}
          color={isLike ? '#16a34a' : '#6b7280'}
          strokeWidth={2}
        />
      </button>

      <button
        type="button"
        aria-label="Dislike"
        aria-pressed={isDislike}
        disabled={disabled || readonly}
        onClick={onDislike}
        title="Dislike"
        style={dislikeBtnStyle}
      >
        <ThumbsDown
          size={iconSize}
          color={isDislike ? '#ef4444' : '#6b7280'}
          strokeWidth={2}
        />
      </button>
    </div>
  );
}

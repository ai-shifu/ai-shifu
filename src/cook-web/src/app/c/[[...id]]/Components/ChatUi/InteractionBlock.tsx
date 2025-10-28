import React, { useState, useMemo, useRef } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { LikeStatus } from '@/c-api/studyV2';
import { postGeneratedContentAction, LIKE_STATUS } from '@/c-api/studyV2';
import { RefreshCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Image from 'next/image';
import AskIcon from '@/c-assets/newchat/light/icon_ask.svg';
import './InteractionBlock.scss';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog';
type Size = 'sm' | 'md' | 'lg';

export interface InteractionBlockProps {
  shifu_bid: string;
  generated_block_bid: string;
  like_status?: LikeStatus | null; // initial status
  readonly?: boolean;
  disabled?: boolean;
  size?: Size;
  className?: string;
  onToggleAskExpanded?: (generated_block_bid: string) => void;
  onRefresh?: (generated_block_bid: string) => void;
}

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
  onToggleAskExpanded,
}: InteractionBlockProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<LikeStatus>(
    (like_status as LikeStatus) ?? LIKE_STATUS.NONE,
  );
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false);

  const isLike = status === LIKE_STATUS.LIKE;
  const isDislike = status === LIKE_STATUS.DISLIKE;

  const likeBtnStyle = useMemo(
    () => ({
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 14,
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
      width: 14,
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
      width: 14,
      height: 14,
      cursor: disabled ? 'not-allowed' : 'pointer',
    }),
    [disabled],
  );

  const send = (action: LikeStatus) => {
    postGeneratedContentAction({
      shifu_bid,
      generated_block_bid,
      action,
    }).catch(e => {
      // errors handled by request layer toast; ignore here
    });
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

  const handleChangeAskPanel = () => {
    onToggleAskExpanded?.(generated_block_bid);
  };

  const handleRefreshClick = () => {
    if (disabled || readonly) return;
    setShowRegenerateDialog(true);
  };

  const handleConfirmRegenerate = () => {
    setShowRegenerateDialog(false);
    onRefresh?.(generated_block_bid);
  };

  return (
    <div className={cn(['interaction-block'], className)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <button
          onClick={handleChangeAskPanel}
          type='button'
          className={cn(
            'ask-button',
            'inline-flex items-center justify-center',
            'text-white font-medium',
            'transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          )}
          disabled={disabled || readonly}
        >
          <Image
            src={AskIcon.src}
            alt='ask'
            width={14}
            height={14}
          />
          <span>{t('module.chat.ask')}</span>
        </button>
        <button
          type='button'
          aria-label='Refresh'
          aria-pressed={false}
          style={refreshBtnStyle}
          disabled={disabled || readonly}
          onClick={handleRefreshClick}
        >
          <RefreshCcw
            size={14}
            className={cn('text-gray-400', 'w-5', 'h-5')}
          />
        </button>
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
      </div>

      <Dialog
        open={showRegenerateDialog}
        onOpenChange={setShowRegenerateDialog}
      >
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>{t('module.chat.regenerateConfirmTitle')}</DialogTitle>
            <DialogDescription>
              {t('module.chat.regenerateConfirmDescription')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className='flex gap-2 sm:gap-2'>
            <button
              type='button'
              onClick={() => setShowRegenerateDialog(false)}
              className='px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50'
            >
              {t('common.core.cancel')}
            </button>
            <button
              type='button'
              onClick={handleConfirmRegenerate}
              className='px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-lighter'
            >
              {t('common.core.ok')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

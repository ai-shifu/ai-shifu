import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCcw, ThumbsUp, ThumbsDown } from 'lucide-react';
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/Popover';
import type { LikeStatus } from '@/c-api/studyV2';
import { postGeneratedContentAction, LIKE_STATUS } from '@/c-api/studyV2';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog';

export interface InteractionBlockMProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  position: { x: number; y: number };
  shifu_bid: string;
  generated_block_bid: string;
  like_status?: LikeStatus | null;
  readonly?: boolean;
  disabled?: boolean;
  onRefresh?: (generatedBlockBid: string) => void;
}

/**
 * InteractionBlockM
 * Mobile interaction menu (Popover) for content blocks
 */
export default function InteractionBlockM({
  open,
  onOpenChange,
  position,
  shifu_bid,
  generated_block_bid,
  like_status = LIKE_STATUS.NONE,
  readonly = false,
  disabled = false,
  onRefresh,
}: InteractionBlockMProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<LikeStatus>(() => {
    return (like_status as LikeStatus) ?? LIKE_STATUS.NONE;
  });
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false);

  const isLike = status === LIKE_STATUS.LIKE;
  const isDislike = status === LIKE_STATUS.DISLIKE;

  useEffect(() => {
    setStatus((like_status as LikeStatus) ?? LIKE_STATUS.NONE);
  }, [like_status, generated_block_bid]);

  const send = (action: LikeStatus) => {
    postGeneratedContentAction({
      shifu_bid,
      generated_block_bid,
      action,
    }).catch(e => {
      // errors handled by request layer toast; ignore here
    });
  };

  const handleRefresh = () => {
    if (disabled || readonly) return;
    onOpenChange(false);
    setShowRegenerateDialog(true);
  };

  const handleConfirmRegenerate = () => {
    setShowRegenerateDialog(false);
    onRefresh?.(generated_block_bid);
  };

  const handleLike = () => {
    if (disabled || readonly) return;
    setStatus(prev => {
      const next: LikeStatus =
        prev === LIKE_STATUS.LIKE ? LIKE_STATUS.NONE : LIKE_STATUS.LIKE;
      send(next);
      return next;
    });
    onOpenChange(false);
  };

  const handleDislike = () => {
    if (disabled || readonly) return;
    setStatus(prev => {
      const next: LikeStatus =
        prev === LIKE_STATUS.DISLIKE ? LIKE_STATUS.NONE : LIKE_STATUS.DISLIKE;
      send(next);
      return next;
    });
    onOpenChange(false);
  };

  return (
    <>
      <Popover
        open={open}
        onOpenChange={onOpenChange}
      >
        <PopoverTrigger asChild>
          <div
            style={{
              position: 'fixed',
              left: position.x,
              top: position.y,
              width: 1,
              height: 1,
              pointerEvents: 'none',
            }}
          />
        </PopoverTrigger>
        <PopoverContent
          className='w-auto p-2 bg-white shadow-lg rounded-lg border border-gray-200'
          align='start'
        >
          <div className='flex flex-col'>
            <button
              onClick={handleRefresh}
              disabled={disabled || readonly}
              className='flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors rounded-md disabled:opacity-50 disabled:cursor-not-allowed'
            >
              <RefreshCcw
                size={16}
                className='text-gray-500'
              />
              <span>{t('module.chat.regenerate')}</span>
            </button>
            <button
              onClick={handleLike}
              disabled={disabled || readonly}
              className='flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors rounded-md disabled:opacity-50 disabled:cursor-not-allowed'
            >
              <ThumbsUp
                size={16}
                className={cn(isLike ? 'text-blue-500' : 'text-gray-500')}
              />
              <span>{t('module.chat.like')}</span>
            </button>
            <button
              onClick={handleDislike}
              disabled={disabled || readonly}
              className='flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors rounded-md disabled:opacity-50 disabled:cursor-not-allowed'
            >
              <ThumbsDown
                size={16}
                className={cn(isDislike ? 'text-blue-500' : 'text-gray-500')}
              />
              <span>{t('module.chat.dislike')}</span>
            </button>
          </div>
        </PopoverContent>
      </Popover>

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
    </>
  );
}

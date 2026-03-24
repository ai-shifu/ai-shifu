import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCcw } from 'lucide-react';
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/Popover';
import type { AudioSegment } from '@/c-utils/audio-utils';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
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
  element_bid: string;
  readonly?: boolean;
  disabled?: boolean;
  onRefresh?: (elementBid: string) => void;
  audioUrl?: string;
  streamingSegments?: AudioSegment[];
  isStreaming?: boolean;
  onRequestAudio?: () => Promise<any>;
  showAudioAction?: boolean;
  showGenerateBtn?: boolean;
}

/**
 * InteractionBlockM
 * Mobile interaction menu (Popover) for content blocks.
 */
export default function InteractionBlockM({
  open,
  onOpenChange,
  position,
  shifu_bid,
  element_bid,
  readonly = false,
  disabled = false,
  onRefresh,
  audioUrl,
  streamingSegments,
  isStreaming,
  onRequestAudio,
  showAudioAction = true,
  showGenerateBtn = false,
}: InteractionBlockMProps) {
  const { t } = useTranslation();
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false);

  const hasAudioAction =
    Boolean(audioUrl) ||
    Boolean(isStreaming) ||
    Boolean(onRequestAudio) ||
    Boolean(streamingSegments && streamingSegments.length > 0);
  const shouldShowAudioAction = Boolean(showAudioAction) && hasAudioAction;
  const shouldShowGenerateAction = Boolean(showGenerateBtn);

  const handleRefresh = () => {
    if (disabled || readonly) return;
    onOpenChange(false);
    setShowRegenerateDialog(true);
  };

  const handleConfirmRegenerate = () => {
    setShowRegenerateDialog(false);
    onRefresh?.(element_bid);
  };

  void shifu_bid;

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
          forceMount
          data-mobile-interaction-popover='true'
        >
          <div className='flex flex-col'>
            {shouldShowGenerateAction ? (
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
            ) : null}
            {shouldShowAudioAction ? (
              <div className='flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700'>
                <AudioPlayer
                  audioUrl={audioUrl}
                  streamingSegments={streamingSegments}
                  isStreaming={isStreaming}
                  alwaysVisible={true}
                  onRequestAudio={onRequestAudio}
                  size={16}
                />
                <span>{t('module.chat.playAudio')}</span>
              </div>
            ) : null}
          </div>
        </PopoverContent>
      </Popover>

      {shouldShowGenerateAction ? (
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
      ) : null}
    </>
  );
}

import React, { useMemo, useState } from 'react';
import { RefreshCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

type Size = 'sm' | 'md' | 'lg';
type AskButtonVariant = 'default' | 'content';

export interface InteractionBlockProps {
  shifu_bid: string;
  element_bid: string;
  readonly?: boolean;
  disabled?: boolean;
  size?: Size;
  className?: string;
  onToggleAskExpanded?: (element_bid: string) => void;
  onRefresh?: (element_bid: string) => void;
  disableAskButton?: boolean;
  disableInteractionButtons?: boolean;
  showGenerateBtn?: boolean;
  extraActions?: React.ReactNode;
  askButtonVariant?: AskButtonVariant;
}

export default function InteractionBlock({
  shifu_bid,
  element_bid,
  readonly = false,
  disabled = false,
  disableAskButton = false,
  disableInteractionButtons = false,
  showGenerateBtn = false,
  className,
  onRefresh,
  onToggleAskExpanded,
  extraActions,
  askButtonVariant = 'default',
}: InteractionBlockProps) {
  const { t } = useTranslation();
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false);
  const shouldShowAskButton = !disableAskButton;
  const hasVisibleActions = Boolean(
    shouldShowAskButton || showGenerateBtn || extraActions,
  );

  const refreshBtnStyle = useMemo(
    () => ({
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 22,
      height: 22,
      padding: 3,
      borderRadius: 4,
      transition: 'background-color 0.2s ease',
      cursor: disabled ? 'not-allowed' : 'pointer',
    }),
    [disabled],
  );

  const handleChangeAskPanel = () => {
    onToggleAskExpanded?.(element_bid);
  };

  const handleRefreshClick = () => {
    if (disabled || readonly) return;
    setShowRegenerateDialog(true);
  };

  const handleConfirmRegenerate = () => {
    setShowRegenerateDialog(false);
    onRefresh?.(element_bid);
  };

  const canHover = !(disabled || readonly);
  void shifu_bid;
  void disableInteractionButtons;

  if (!hasVisibleActions) {
    return null;
  }

  return (
    <div className={cn(['interaction-block'], className)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        {shouldShowAskButton ? (
          <button
            onClick={handleChangeAskPanel}
            type='button'
            className={cn(
              'ask-button',
              askButtonVariant === 'content' && 'ask-button--content',
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
        ) : null}
        {showGenerateBtn ? (
          <button
            type='button'
            aria-label='Refresh'
            aria-pressed={false}
            style={refreshBtnStyle}
            disabled={disabled || readonly}
            onClick={handleRefreshClick}
            className={cn('interaction-icon-btn', canHover && 'group')}
          >
            <TooltipProvider delayDuration={150}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <RefreshCcw
                    size={16}
                    className={cn(
                      'text-[#55575E]',
                      'w-4',
                      'h-4',
                      'transition-colors',
                      'duration-200',
                    )}
                  />
                </TooltipTrigger>
                <TooltipContent
                  side='top'
                  className='bg-black text-white border-none'
                >
                  {t('module.chat.regenerate')}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </button>
        ) : null}
        {extraActions}
      </div>

      {showGenerateBtn ? (
        <Dialog
          open={showRegenerateDialog}
          onOpenChange={setShowRegenerateDialog}
        >
          <DialogContent className='sm:max-w-md'>
            <DialogHeader>
              <DialogTitle>
                {t('module.chat.regenerateConfirmTitle')}
              </DialogTitle>
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
    </div>
  );
}

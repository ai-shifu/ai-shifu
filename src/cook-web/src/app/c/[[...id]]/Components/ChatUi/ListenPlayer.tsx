import React, { memo, useCallback, useEffect, useRef, useState } from 'react';
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
import type { ChatContentItem } from './useChatLogicHook';
import {
  ContentRender,
  type OnSendContentParams,
} from 'markdown-flow-ui/renderer';
import { useTranslation } from 'react-i18next';

interface ListenPlayerProps {
  className?: string;
  mobileStyle?: boolean;
  onMore?: () => void;
  onVolume?: () => void;
  onPrev?: () => void;
  onPlay?: () => void;
  onPause?: (traceId: string) => void;
  onNext?: () => void;
  onFullscreen?: () => void;
  onSubtitles?: () => void;
  onNotes?: () => void;
  prevDisabled?: boolean;
  nextDisabled?: boolean;
  isAudioPlaying?: boolean;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
  interaction?: ChatContentItem | null;
  interactionReadonly?: boolean;
}

const ListenPlayer = ({
  className,
  mobileStyle = false,
  onMore,
  onVolume,
  onPrev,
  onPlay,
  onPause,
  onNext,
  onFullscreen,
  onSubtitles,
  onNotes,
  prevDisabled = false,
  nextDisabled = false,
  isAudioPlaying = false,
  interaction,
  interactionReadonly,
  onSend,
}: ListenPlayerProps) => {
  const { t } = useTranslation();
  const [isInteractionOpen, setIsInteractionOpen] = useState(false);
  const lastInteractionBidRef = useRef<string | null>(null);
  const disabledClassName = '!cursor-not-allowed !opacity-20';
  const shouldHideUtilityControls = true;
  const shouldHideFullscreen = true;
  const shouldHideSubtitles = true;
  const resolvedReadonly =
    typeof interactionReadonly === 'boolean'
      ? interactionReadonly
      : Boolean(interaction?.readonly);

  useEffect(() => {
    const nextBid = interaction?.generated_block_bid ?? null;
    if (!nextBid) {
      lastInteractionBidRef.current = null;
      setIsInteractionOpen(false);
      return;
    }
    if (lastInteractionBidRef.current !== nextBid) {
      lastInteractionBidRef.current = nextBid;
      setIsInteractionOpen(true);
    }
  }, [interaction]);

  const handleNotesClick = useCallback(() => {
    if (!interaction) {
      return;
    }
    setIsInteractionOpen(prev => !prev);
    onNotes?.();
  }, [interaction, onNotes]);

  const _onSend = useCallback(
    (content: OnSendContentParams) => {
      if (!interaction?.generated_block_bid) {
        return;
      }
      setIsInteractionOpen(false);
      onSend?.(content, interaction.generated_block_bid);
    },
    [onSend, interaction?.generated_block_bid],
  );

  return (
    <div
      className={cn(
        styles.playerContainer,
        'relative',
        mobileStyle ? styles.mobile : '',
        className,
      )}
    >
      {interaction && isInteractionOpen ? (
        <div
          className={cn(
            'absolute left-1/2 top-0 w-full -translate-x-1/2 -translate-y-full pb-4',
            styles.interactionContainer,
          )}
        >
          <div className='rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-lg'>
            <div className='px-4 pt-3'>
              <p className='text-[16px] leading-[20px] text-foreground/65'>
                {t('module.chat.listenInteractionHint')}
              </p>
            </div>
            <div className='content-render-theme max-h-60 overflow-y-auto px-4 pb-3 text-[var(--card-foreground)]'>
              <ContentRender
                enableTypewriter={false}
                content={interaction.content || ''}
                customRenderBar={interaction.customRenderBar}
                defaultButtonText={interaction.defaultButtonText}
                defaultInputText={interaction.defaultInputText}
                defaultSelectedValues={interaction.defaultSelectedValues}
                confirmButtonText={t('module.renderUi.core.confirm')}
                copyButtonText={t('module.renderUi.core.copyCode')}
                copiedButtonText={t('module.renderUi.core.copied')}
                readonly={resolvedReadonly}
                sandboxMode='content'
                onSend={_onSend}
              />
            </div>
          </div>
        </div>
      ) : null}
      {!shouldHideUtilityControls ? (
        <div className={styles.controlGroup}>
          <button
            type='button'
            aria-label='More options'
            onClick={onMore}
          >
            <MoreVertical size={32} />
          </button>
          <button
            type='button'
            aria-label='Volume'
            onClick={onVolume}
          >
            <Volume2 size={32} />
          </button>
        </div>
      ) : null}

      <div className={styles.controlGroup}>
        <button
          type='button'
          aria-label='Rewind'
          onClick={onPrev}
          disabled={prevDisabled}
          className={cn(prevDisabled ? disabledClassName : '')}
        >
          <RotateCcw size={32} />
        </button>
        {isAudioPlaying ? (
          <button
            type='button'
            aria-label='Pause'
            className={styles.playButton}
            onClick={() => {
              const traceId = `pause-${Date.now()}-${Math.random()
                .toString(36)
                .slice(2, 8)}`;
              onPause?.(traceId);
            }}
          >
            <svg
              xmlns='http://www.w3.org/2000/svg'
              width='34'
              height='34'
              viewBox='0 0 34 34'
              fill='none'
            >
              <path
                d='M16.6667 33.3333C25.8714 33.3333 33.3333 25.8714 33.3333 16.6667C33.3333 7.46192 25.8714 0 16.6667 0C7.46192 0 0 7.46192 0 16.6667C0 25.8714 7.46192 33.3333 16.6667 33.3333Z'
                fill='#0A0A0A'
              />
              <path
                d='M12 10H16V24H12V10ZM18 10H22V24H18V10Z'
                fill='white'
              />
            </svg>
          </button>
        ) : (
          <button
            type='button'
            aria-label='Play'
            className={styles.playButton}
            onClick={onPlay}
          >
            <svg
              xmlns='http://www.w3.org/2000/svg'
              width='34'
              height='34'
              viewBox='0 0 34 34'
              fill='none'
            >
              <path
                d='M16.6667 33.3333C25.8714 33.3333 33.3333 25.8714 33.3333 16.6667C33.3333 7.46192 25.8714 0 16.6667 0C7.46192 0 0 7.46192 0 16.6667C0 25.8714 7.46192 33.3333 16.6667 33.3333Z'
                fill='#0A0A0A'
              />
              <path
                d='M13.3333 10L23.3333 16.6667L13.3333 23.3333V10Z'
                fill='white'
              />
            </svg>
          </button>
        )}
        <button
          type='button'
          aria-label='Forward'
          onClick={onNext}
          disabled={nextDisabled}
          className={cn(nextDisabled ? disabledClassName : '')}
        >
          <RotateCw size={32} />
        </button>
        {!shouldHideFullscreen ? (
          <button
            type='button'
            aria-label='Fullscreen'
            onClick={onFullscreen}
          >
            <Scan size={32} />
          </button>
        ) : null}
      </div>

      <div className={styles.separator} />

      <div className={styles.controlGroup}>
        {!shouldHideSubtitles ? (
          <button
            type='button'
            aria-label='Subtitles'
            onClick={onSubtitles}
          >
            <Sparkles size={32} />
          </button>
        ) : null}
        <button
          type='button'
          aria-label='Notes'
          onClick={handleNotesClick}
          disabled={!interaction}
          className={cn(interaction ? '!text-primary' : disabledClassName)}
        >
          <SquarePen size={32} />
        </button>
      </div>
    </div>
  );
};

ListenPlayer.displayName = 'ListenPlayer';

export default memo(ListenPlayer);

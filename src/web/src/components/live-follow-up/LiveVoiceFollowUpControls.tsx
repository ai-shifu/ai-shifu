'use client';

import { Loader2, Mic, MicOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';
import type {
  LiveVoiceFollowUpController,
  LiveVoiceFollowUpTarget,
} from './useLiveVoiceFollowUp';

type LiveVoiceControlsProps = {
  controller: LiveVoiceFollowUpController;
  target: LiveVoiceFollowUpTarget;
};

/** Manual capture action, positioned beside Send by the original input. */
export const LiveVoiceFollowUpMicrophoneButton = ({
  controller,
  target,
  className,
}: LiveVoiceControlsProps & { className?: string }) => {
  const { t } = useTranslation();
  const ownsTarget = controller.anchorElementBid === target.anchorElementBid;
  const muted = !ownsTarget || controller.muted;
  const pending = ownsTarget && controller.microphonePending;
  return (
    <Button
      type='button'
      variant='ghost'
      size='icon'
      className={cn('h-8 w-8 shrink-0 rounded-full', className)}
      aria-label={
        muted
          ? t('module.chat.liveVoiceStartMicrophone')
          : t('module.chat.liveVoiceStopMicrophone')
      }
      aria-pressed={!muted}
      disabled={
        pending ||
        (ownsTarget &&
          (controller.textPending ||
            controller.retryAvailableAt !== null ||
            controller.state === 'reconnecting'))
      }
      onClick={() =>
        muted
          ? controller.startMicrophone(target)
          : controller.stopMicrophone(true)
      }
    >
      {pending ? (
        <Loader2 className='h-4 w-4 animate-spin' />
      ) : muted ? (
        <MicOff className='h-4 w-4' />
      ) : (
        <Mic className='h-4 w-4 text-primary' />
      )}
    </Button>
  );
};

/** Status only: AskBlock owns the layout, messages, and keyboard. */
export const LiveVoiceFollowUpControls = ({
  controller,
  target,
}: LiveVoiceControlsProps) => {
  const { t } = useTranslation();
  const ownsTarget = controller.anchorElementBid === target.anchorElementBid;
  const state = ownsTarget ? controller.state : 'ended';
  const muted = !ownsTarget || controller.muted;
  const error = ownsTarget && controller.errorCode;
  const retryAt = ownsTarget ? controller.retryAvailableAt : null;
  const status =
    ownsTarget && controller.paused
      ? t('module.chat.liveVoicePaused')
      : state === 'listening' && muted
        ? t('module.chat.liveVoiceReady')
        : state === 'ended'
          ? t('module.chat.liveVoiceInputHint')
          : t(`module.chat.liveVoiceState.${state}`);
  return (
    <div className='mt-2 space-y-1 text-xs text-muted-foreground'>
      <div className='flex min-w-0 items-center gap-2'>
        <span
          className='min-w-0 flex-1'
          role='status'
          aria-live='polite'
        >
          {status}
        </span>
        {state !== 'ended' ? (
          <Button
            type='button'
            variant='ghost'
            size='sm'
            onClick={controller.end}
          >
            {t('module.chat.liveVoiceEnd')}
          </Button>
        ) : ownsTarget && (controller.retryable || retryAt !== null) ? (
          <Button
            type='button'
            variant='ghost'
            size='sm'
            disabled={!controller.retryable}
            onClick={controller.retry}
          >
            {t('module.chat.liveVoiceRetry')}
          </Button>
        ) : null}
      </div>
      {error ? (
        <p
          role='alert'
          className='text-destructive'
        >
          {error === 'capacity_exceeded'
            ? t('module.chat.liveVoiceCapacityExceeded')
            : t('module.chat.liveVoiceConnectionFailed')}
        </p>
      ) : null}
      {ownsTarget && controller.microphoneError ? (
        <p role='alert'>{t('module.chat.liveVoiceMicrophoneOptional')}</p>
      ) : null}
      <p>{t('module.chat.liveVoicePrivacyNotice')}</p>
    </div>
  );
};

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
      className={cn(
        'h-8 w-8 shrink-0 rounded-full',
        !muted &&
          controller.inputActive &&
          'motion-safe:animate-pulse bg-primary/15 ring-2 ring-primary/40',
        className,
      )}
      aria-label={
        muted
          ? t('module.chat.liveVoiceStartMicrophone')
          : t('module.chat.liveVoiceStopMicrophone')
      }
      aria-pressed={!muted}
      disabled={
        muted &&
        ((controller.readiness !== 'ready' &&
          !(ownsTarget && controller.state !== 'ended')) ||
          pending ||
          (ownsTarget &&
            (controller.textPending ||
              controller.retryAvailableAt !== null ||
              controller.state === 'reconnecting')))
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

/** Failures only: normal connection and pause states need no extra UI. */
export const LiveVoiceFollowUpControls = ({
  controller,
  target,
}: LiveVoiceControlsProps) => {
  const { t } = useTranslation();
  const ownsTarget = controller.anchorElementBid === target.anchorElementBid;
  const error = ownsTarget && controller.errorCode;
  const unavailable =
    controller.readiness === 'unavailable' &&
    !(ownsTarget && controller.state !== 'ended');
  if (!error && !unavailable && !(ownsTarget && controller.microphoneError))
    return null;
  return (
    <div className='mt-2 space-y-1 text-xs text-muted-foreground'>
      {error || unavailable ? (
        <p
          role='alert'
          className='text-destructive'
        >
          {unavailable
            ? t('module.chat.liveVoiceServiceUnavailable')
            : error === 'capacity_exceeded'
              ? t('module.chat.liveVoiceCapacityExceeded')
              : error === 'server_error'
                ? t('module.chat.liveVoiceServiceUnavailable')
                : t('module.chat.liveVoiceConnectionFailed')}
        </p>
      ) : null}
      {ownsTarget && controller.microphoneError ? (
        <p role='alert'>{t('module.chat.liveVoiceMicrophoneOptional')}</p>
      ) : null}
    </div>
  );
};

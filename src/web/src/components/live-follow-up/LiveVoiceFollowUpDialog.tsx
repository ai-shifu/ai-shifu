'use client';

import { useEffect, useRef } from 'react';
import {
  Loader2,
  Mic,
  MicOff,
  PhoneOff,
  RotateCw,
  Volume2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { cn } from '@/lib/utils';

import type { LiveVoiceFollowUpController } from './useLiveVoiceFollowUp';

type LiveVoiceFollowUpDialogProps = {
  controller: LiveVoiceFollowUpController;
};

export const LiveVoiceFollowUpDialog = ({
  controller,
}: LiveVoiceFollowUpDialogProps) => {
  const { t } = useTranslation();
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ block: 'end' });
  }, [controller.transcripts]);

  const stateLabel = t(`module.chat.liveVoiceState.${controller.state}`);
  const isConnecting =
    controller.state === 'connecting' || controller.state === 'reconnecting';

  return (
    <Dialog
      open={controller.open}
      onOpenChange={open => {
        if (!open) {
          controller.close();
        }
      }}
    >
      <DialogContent
        showClose={false}
        className='left-0 top-0 flex h-[100dvh] w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none border-0 bg-background p-0 sm:w-screen sm:rounded-none'
      >
        <DialogHeader className='shrink-0 border-b border-border px-5 py-4 text-start sm:px-8'>
          <div className='mx-auto flex w-full max-w-4xl items-center justify-between gap-4'>
            <div className='min-w-0'>
              <DialogTitle>{t('module.chat.liveVoiceTitle')}</DialogTitle>
              <DialogDescription className='mt-1'>
                {t('module.chat.liveVoicePrivacyNotice')}
              </DialogDescription>
            </div>
            <div
              className='flex shrink-0 items-center gap-2 text-sm text-muted-foreground'
              role='status'
              aria-live='polite'
            >
              {isConnecting ? (
                <Loader2 className='h-4 w-4 animate-spin' />
              ) : controller.state === 'speaking' ? (
                <Volume2 className='h-4 w-4 text-primary' />
              ) : (
                <Mic className='h-4 w-4 text-primary' />
              )}
              <span>{stateLabel}</span>
            </div>
          </div>
        </DialogHeader>

        <main className='min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-8'>
          <div
            className='mx-auto flex w-full max-w-4xl flex-col gap-4'
            aria-live='polite'
          >
            {controller.warning ? (
              <div className='rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900'>
                {t('module.chat.liveVoiceTimeWarning')}
              </div>
            ) : null}

            {controller.errorCode ? (
              <div
                className='rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive'
                role='alert'
              >
                {controller.errorCode === 'microphone_denied'
                  ? t('module.chat.liveVoiceMicrophoneDenied')
                  : controller.errorCode === 'capacity_exceeded'
                    ? t('module.chat.liveVoiceCapacityExceeded')
                    : t('module.chat.liveVoiceConnectionFailed')}
              </div>
            ) : controller.endReason === 'timeout' ? (
              <div className='rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-foreground'>
                {t('module.chat.liveVoiceTimedOut')}
              </div>
            ) : null}

            {controller.transcripts.length === 0 ? (
              <div className='flex min-h-[45vh] flex-col items-center justify-center gap-3 text-center text-muted-foreground'>
                <div className='flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary'>
                  {controller.state === 'speaking' ? (
                    <Volume2 className='h-8 w-8' />
                  ) : (
                    <Mic className='h-8 w-8' />
                  )}
                </div>
                <p>{t('module.chat.liveVoiceEmpty')}</p>
              </div>
            ) : (
              controller.transcripts.map(transcript => (
                <div
                  key={`${transcript.turnIndex}:${transcript.role}`}
                  className={cn(
                    'flex flex-col gap-1',
                    transcript.role === 'user' ? 'items-end' : 'items-start',
                  )}
                >
                  <span className='text-xs text-muted-foreground'>
                    {transcript.role === 'user'
                      ? t('module.chat.liveVoiceYou')
                      : t('module.chat.liveVoiceAI')}
                  </span>
                  <div
                    className={cn(
                      'max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 sm:max-w-[70%]',
                      transcript.role === 'user'
                        ? 'rounded-br-sm bg-primary text-primary-foreground'
                        : 'rounded-bl-sm bg-muted text-foreground',
                      !transcript.final && 'opacity-70',
                    )}
                  >
                    {transcript.text}
                  </div>
                </div>
              ))
            )}
            <div ref={transcriptEndRef} />
          </div>
        </main>

        <footer className='shrink-0 border-t border-border bg-background px-5 py-4 sm:px-8'>
          <div className='mx-auto flex w-full max-w-4xl items-center justify-center gap-3'>
            {controller.state === 'ended' && controller.retryable ? (
              <Button
                type='button'
                onClick={controller.retry}
                className='min-w-32'
              >
                <RotateCw className='h-4 w-4' />
                {t('module.chat.liveVoiceRetry')}
              </Button>
            ) : (
              <Button
                type='button'
                variant='outline'
                size='icon'
                onClick={controller.toggleMuted}
                aria-label={
                  controller.muted
                    ? t('module.chat.liveVoiceUnmute')
                    : t('module.chat.liveVoiceMute')
                }
                aria-pressed={controller.muted}
                disabled={controller.state === 'ended'}
                className='h-11 w-11 rounded-full'
              >
                {controller.muted ? (
                  <MicOff className='h-5 w-5' />
                ) : (
                  <Mic className='h-5 w-5' />
                )}
              </Button>
            )}
            <Button
              type='button'
              variant='destructive'
              onClick={controller.end}
              className='min-w-32 rounded-full'
            >
              <PhoneOff className='h-4 w-4' />
              {controller.state === 'ended'
                ? t('module.chat.liveVoiceClose')
                : t('module.chat.liveVoiceEnd')}
            </Button>
          </div>
        </footer>
      </DialogContent>
    </Dialog>
  );
};

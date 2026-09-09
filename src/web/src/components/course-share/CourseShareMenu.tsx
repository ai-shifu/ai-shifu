'use client';

import { useEffect, useRef, useState } from 'react';
import { Copy, Share2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useTracking } from '@/hooks/useTracking';
import { Button } from '@/components/ui/Button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { showDefaultToast, useToast } from '@/hooks/useToast';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  buildCourseShareContent,
  copyCourseShareText,
  normalizeCourseShareUrl,
} from '@/lib/courseShare';
import {
  CourseShareButton,
  type CourseShareButtonProps,
} from './CourseShareButton';

export function CourseShareMenu(props: CourseShareButtonProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [status, setStatus] = useState<'idle' | 'copying' | 'failed'>('idle');
  const copying = useRef(false);
  const opened = useRef(false);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const events =
    props.surface === 'teacher_header'
      ? {
          open: 'teacher_course_share_open',
          copy: 'teacher_poster_prompt_copy',
          result: 'teacher_poster_prompt_result',
        }
      : {
          open: 'learner_course_share_open',
          copy: 'learner_poster_prompt_copy',
          result: 'learner_poster_prompt_result',
        };
  const clearDismiss = () => {
    if (dismissTimer.current) clearTimeout(dismissTimer.current);
    dismissTimer.current = null;
  };
  useEffect(() => () => clearDismiss(), []);

  const track = (name: string, outcome?: 'success' | 'failed') => {
    try {
      const payload = outcome
        ? { shifu_bid: props.shifuBid, surface: props.surface, outcome }
        : { shifu_bid: props.shifuBid, surface: props.surface };
      void Promise.resolve(trackEvent(name, payload)).catch(() => {});
    } catch {
      // Analytics must never prevent a clipboard or menu action.
    }
  };

  const changeOpen = (nextOpen: boolean) => {
    clearDismiss();
    if (nextOpen === opened.current) return;
    if (nextOpen && copying.current) return;
    if (nextOpen) {
      try {
        const url = normalizeCourseShareUrl(props.resolveShareUrl());
        if (!url) throw new Error('Invalid course URL');
        const content = buildCourseShareContent({
          courseTitle: props.courseTitle,
          courseDescription: props.courseDescription,
          recommendation: t('common.core.shareCourseMessage', {
            courseName: props.courseTitle,
          }),
          url,
        });
        setPrompt(
          t('common.core.posterPrompt', {
            courseContent: content.clipboardText,
          }),
        );
        setStatus('idle');
        track(events.open);
      } catch {
        toast({ title: t('common.core.shareFailed'), variant: 'destructive' });
        return;
      }
    }
    opened.current = nextOpen;
    setOpen(nextOpen);
  };

  const leave = (event: React.PointerEvent) => {
    if (event.pointerType !== 'mouse' || status !== 'idle' || copying.current)
      return;
    clearDismiss();
    dismissTimer.current = setTimeout(() => changeOpen(false), 300);
  };

  const copyPrompt = async () => {
    if (copying.current) return;
    clearDismiss();
    copying.current = true;
    setStatus('copying');
    track(events.copy);
    let success = false;
    try {
      success = await copyCourseShareText(prompt);
    } catch {
      // Preserve a selectable fallback when clipboard access fails.
    }
    copying.current = false;
    track(events.result, success ? 'success' : 'failed');
    if (success) {
      setStatus('idle');
      changeOpen(false);
      showDefaultToast(t('common.core.posterNextStep'));
    } else {
      setStatus('failed');
      toast({
        title: t('common.core.posterCopyFailed'),
        variant: 'destructive',
      });
    }
  };

  const trigger = (
    <PopoverTrigger asChild>
      <Button
        type='button'
        variant={props.variant ?? 'ghost'}
        size={props.size ?? 'icon'}
        className={props.className}
        aria-label={t('common.core.shareCourse')}
        data-lesson-print-exclude='true'
        onPointerEnter={clearDismiss}
        onPointerLeave={leave}
      >
        <Share2 aria-hidden='true' />
        {props.showLabel ? t('common.core.share') : null}
      </Button>
    </PopoverTrigger>
  );

  return (
    <Popover
      open={open}
      onOpenChange={changeOpen}
      modal={false}
    >
      {props.showLabel ? (
        trigger
      ) : (
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>{trigger}</TooltipTrigger>
            <TooltipContent side={props.tooltipSide ?? 'top'}>
              {t('common.core.shareCourse')}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
      <PopoverContent
        align='end'
        sideOffset={4}
        collisionPadding={8}
        aria-label={t('common.core.shareCourse')}
        className='w-max max-w-[calc(100vw-16px)] rounded-lg p-1'
        onPointerEnter={clearDismiss}
        onPointerLeave={leave}
      >
        <CourseShareButton
          {...props}
          showLabel
          variant='ghost'
          size='default'
          className='w-full justify-start gap-2'
          disabled={status === 'copying'}
          onShareStart={() => {
            clearDismiss();
            copying.current = true;
            setStatus('copying');
          }}
          onShareComplete={() => {
            copying.current = false;
            setStatus('idle');
            changeOpen(false);
          }}
        />
        <Button
          variant='ghost'
          className='flex w-full justify-start gap-2'
          disabled={status === 'copying'}
          aria-busy={status === 'copying'}
          onClick={() => void copyPrompt()}
        >
          <Copy
            className='h-4 w-4'
            aria-hidden='true'
          />
          {t('common.core.posterCopy')}
        </Button>
        {status === 'failed' && (
          <textarea
            readOnly
            aria-label={t('common.core.posterPromptLabel')}
            value={prompt}
            onFocus={event => event.currentTarget.select()}
            className='m-1 block h-32 w-60 max-w-full resize-none rounded border p-2 text-xs'
          />
        )}
      </PopoverContent>
    </Popover>
  );
}

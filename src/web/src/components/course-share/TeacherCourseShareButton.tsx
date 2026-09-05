'use client';

import { useId, useRef, useState } from 'react';
import { Check, ChevronDown, Copy, Share2, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useTracking } from '@/c-common/hooks/useTracking';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/Dialog';
import { useToast } from '@/hooks/useToast';
import {
  buildCourseShareContent,
  copyCourseShareText,
  normalizeCourseShareUrl,
} from '@/lib/courseShare';
import {
  CourseShareButton,
  type CourseShareButtonProps,
} from './CourseShareButton';

export function TeacherCourseShareButton(props: CourseShareButtonProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [shareUrl, setShareUrl] = useState('');
  const [guideOpen, setGuideOpen] = useState(false);
  const guideId = useId();
  const [status, setStatus] = useState<
    'idle' | 'copying' | 'success' | 'failed'
  >('idle');
  const copying = useRef(false);
  const opened = useRef(false);
  const trigger = useRef<HTMLButtonElement>(null);

  const track = (name: string, outcome?: 'success' | 'failed') => {
    try {
      const payload = outcome
        ? { shifu_bid: props.shifuBid, surface: 'teacher_header', outcome }
        : { shifu_bid: props.shifuBid, surface: 'teacher_header' };
      void Promise.resolve(trackEvent(name, payload)).catch(() => {});
    } catch {
      // Analytics must never prevent a clipboard or dialog action.
    }
  };

  const changeOpen = (nextOpen: boolean) => {
    if (copying.current || nextOpen === opened.current) return;
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
        setShareUrl(url);
        setGuideOpen(false);
        track('teacher_course_share_open');
      } catch {
        toast({ title: t('common.core.shareFailed'), variant: 'destructive' });
        return;
      }
    }
    opened.current = nextOpen;
    setOpen(nextOpen);
  };

  const copyPrompt = async () => {
    if (copying.current) return;
    copying.current = true;
    setStatus('copying');
    track('teacher_poster_prompt_copy');
    try {
      const success = await copyCourseShareText(prompt);
      const outcome = success ? 'success' : 'failed';
      if (!success) setGuideOpen(true);
      track('teacher_poster_prompt_result', outcome);
      setStatus(outcome);
    } catch {
      setGuideOpen(true);
      track('teacher_poster_prompt_result', 'failed');
      setStatus('failed');
    } finally {
      copying.current = false;
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={changeOpen}
    >
      <DialogTrigger asChild>
        <Button
          ref={trigger}
          type='button'
          variant={props.variant}
          size={props.size}
          className={props.className}
          aria-label={t('common.core.shareCourse')}
          data-lesson-print-exclude='true'
        >
          <Share2 aria-hidden='true' />
          {props.showLabel ? t('common.core.share') : null}
        </Button>
      </DialogTrigger>
      <DialogContent
        className='flex max-h-[90dvh] max-w-xl flex-col gap-0 overflow-hidden rounded-2xl p-0'
        overlayClassName='bg-black/40 backdrop-blur-sm'
        onCloseAutoFocus={() => trigger.current?.focus()}
      >
        <DialogHeader className='px-6 pb-5 pt-6 text-start'>
          <DialogTitle>{t('common.core.shareCourse')}</DialogTitle>
          <DialogDescription>
            {t('common.core.posterShareIntro')}
          </DialogDescription>
        </DialogHeader>
        <div className='min-h-0 overflow-y-auto px-6 pb-6'>
          <div className='rounded-xl border bg-background p-5 shadow-sm'>
            <p className='break-words text-base font-semibold leading-6'>
              {props.courseTitle}
            </p>
            <p className='mt-2 line-clamp-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground'>
              {props.courseDescription}
            </p>
            <p
              className='mt-3 truncate rounded-lg border bg-background px-3 py-2 text-xs leading-5 text-muted-foreground'
              title={shareUrl}
              dir='ltr'
            >
              {shareUrl}
            </p>
            <div className='mt-4'>
              <CourseShareButton
                {...props}
                surface='teacher_header'
                showLabel
                label={t('common.core.shareIntroductionAndLink')}
                variant='default'
                size='default'
                className='w-full gap-2'
              />
            </div>
            <p className='mt-2 text-sm leading-6 text-muted-foreground'>
              {t('common.core.shareForwardHint')}
            </p>
          </div>
          <section className='mt-4 rounded-xl border border-primary/15 bg-gradient-to-br from-primary/5 to-background p-5'>
            <div className='flex items-start gap-3'>
              <div className='flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/10'>
                <Sparkles
                  className='h-5 w-5'
                  aria-hidden='true'
                />
              </div>
              <div>
                <h3 className='text-sm font-semibold leading-6'>
                  {t('common.core.posterHeading')}
                </h3>
                <p className='mt-1 text-sm leading-6 text-muted-foreground'>
                  {t('common.core.posterHint')}
                </p>
              </div>
            </div>
            <div className='mt-4 flex flex-wrap items-center gap-3'>
              <Button
                variant='outline'
                className='gap-2 border-primary/25 bg-background text-primary hover:bg-primary/10 hover:text-primary'
                disabled={status === 'copying'}
                aria-busy={status === 'copying'}
                onClick={() => void copyPrompt()}
              >
                {status === 'success' ? (
                  <Check
                    className='h-4 w-4'
                    aria-hidden='true'
                  />
                ) : (
                  <Copy
                    className='h-4 w-4'
                    aria-hidden='true'
                  />
                )}
                {status === 'success'
                  ? t('common.core.posterCopied')
                  : t('common.core.posterCopy')}
              </Button>
              <button
                type='button'
                aria-expanded={guideOpen}
                aria-controls={guideId}
                className='flex min-h-10 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:bg-primary/5 hover:text-foreground'
                onClick={() => {
                  if (!guideOpen) track('teacher_poster_guide_open');
                  setGuideOpen(!guideOpen);
                }}
              >
                {t('common.core.posterViewPrompt')}
                <ChevronDown
                  aria-hidden='true'
                  className={`h-4 w-4 text-muted-foreground transition-transform ${guideOpen ? 'rotate-180' : ''}`}
                />
              </button>
            </div>
            {status !== 'idle' && status !== 'copying' && (
              <p
                role='status'
                className='mt-3 text-xs leading-5 text-muted-foreground'
              >
                {status === 'failed'
                  ? t('common.core.posterCopyFailed')
                  : t('common.core.posterNextStep')}
              </p>
            )}
            <div
              id={guideId}
              hidden={!guideOpen}
            >
              <p className='mb-2 mt-4 text-xs font-medium text-muted-foreground'>
                {t('common.core.posterPromptLabel')}
              </p>
              <div
                tabIndex={0}
                role='region'
                aria-label={t('common.core.posterPromptLabel')}
                className='max-h-56 select-text overflow-y-auto whitespace-pre-wrap break-words rounded-xl border bg-muted/20 p-4 text-sm leading-7'
                dir='auto'
              >
                {prompt}
              </div>
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
